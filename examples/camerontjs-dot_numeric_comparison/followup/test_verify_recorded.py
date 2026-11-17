"""Deterministic tests only: copies of recorded evidence, never inference."""
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('verify_recorded', Path(__file__).with_name('verify_recorded.py'))
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
EXAMPLE = Path(__file__).resolve().parents[1]
ORIGINAL = EXAMPLE / 'recorded'


def fingerprint(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class SavedVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        shutil.copytree(ORIGINAL, self.run)

    def edit_json(self, name, change):
        path = self.run / name
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))

    def edit_lines(self, name, change):
        path = self.run / name
        values = [json.loads(s) for s in path.read_text().splitlines()]
        change(values)
        path.write_text(''.join(json.dumps(v) + '\n' for v in values))

    def reseal(self):
        """Remove superficial checksum failures to exercise semantic checks."""
        checksums = {name: hashlib.sha256((self.run / name).read_bytes()).hexdigest()
                     for name in verifier.EVIDENCE}
        (self.run / 'checksums.json').write_text(json.dumps(checksums))
        self.edit_json('audit.json', lambda a: a.update(evidence_sha256=checksums))

    def verify_copy(self):
        before = fingerprint(self.run)
        result = verifier.verify(self.run)
        self.assertEqual(before, fingerprint(self.run), 'audited input changed')
        self.assertEqual(result['checks']['total'], result['checks']['passed'] + result['checks']['failed'])
        return result

    def fails(self, expected_check):
        result = self.verify_copy()
        self.assertNotEqual('PASS', result['status'])
        self.assertTrue(any(expected_check in f['check'] for f in result['findings']), result['findings'])
        return result

    def test_original_saved_evidence_passes_without_mutation(self):
        before = fingerprint(ORIGINAL)
        result = verifier.verify(ORIGINAL)
        self.assertEqual('PASS', result['status'], result['findings'])
        self.assertEqual([], result['findings'])
        self.assertGreater(result['checks']['total'], 900)
        self.assertEqual(before, fingerprint(ORIGINAL))
        self.assertEqual(19, result['reconstructed_summary']['live_gemma']['check']['correct'])

    def test_raw_reply_tamper_after_resealing_fails(self):
        self.edit_lines('provider_calls.jsonl', lambda t: t[1].update(raw_reply='changed'))
        self.reseal()
        self.fails('raw reply')

    def test_base64_bytes_and_response_hash_tamper(self):
        for field, value in [('response_sha256', '0' * 64), ('response_base64', base64.b64encode(b'{}').decode())]:
            with self.subTest(field=field):
                self.edit_lines('provider_calls.jsonl', lambda t: t[0].update({field: value}))
                self.reseal()
                self.fails('HTTP bytes hash')

    def test_request_tamper(self):
        self.edit_lines('provider_calls.jsonl', lambda t: t[0].update(request_text='{}'))
        self.reseal()
        self.fails('request')

    def test_deleted_record_is_incomplete(self):
        self.edit_lines('records.jsonl', lambda r: r.pop())
        self.reseal()
        self.assertEqual('INCOMPLETE', self.fails('ordered record coverage')['status'])

    def test_duplicate_record_same_count(self):
        self.edit_lines('records.jsonl', lambda r: r.__setitem__(1, r[0]))
        self.reseal()
        self.fails('ordered record coverage')

    def test_duplicate_call_same_count(self):
        self.edit_lines('provider_calls.jsonl', lambda t: t.__setitem__(2, t[1]))
        self.reseal()
        self.fails('ordered provider coverage')

    def test_changed_grade_decision_rule_and_summary(self):
        mutations = [
            ('grade', lambda r: r[0]['grade'].update(label='wrong'), 'reference grade'),
            ('decision', lambda r: r[0]['arms']['check'].update(ok=False), 'replayed check'),
            ('rejection', lambda r: r[1]['arms']['validator'].update(status='ACCEPTED'), 'replayed validator'),
            ('rule', lambda r: r[0]['numeric_rule'].update(passed=False), 'requested-field decision'),
        ]
        original = (self.run / 'records.jsonl').read_bytes()
        for label, mutation, check in mutations:
            with self.subTest(label=label):
                (self.run / 'records.jsonl').write_bytes(original)
                self.edit_lines('records.jsonl', mutation)
                self.reseal()
                self.fails(check)
        (self.run / 'records.jsonl').write_bytes(original)
        self.edit_json('summary.json', lambda s: s['live_gemma']['check'].update(correct=20))
        self.reseal()
        self.fails('summary JSON')

    def test_status_failure_count_and_markdown_tamper(self):
        self.edit_json('summary.json', lambda s: s['live_gemma']['check'].update(call_failed=1))
        self.reseal()
        self.fails('summary JSON')
        path = self.run / 'summary.md'
        path.write_text(path.read_text().replace('| Call failures | 0', '| Call failures | 1'))
        self.reseal()
        self.fails('call_failed')

    def test_missing_evidence_partial_failed_and_unknown_schema(self):
        for name in ['manifest.json', 'records.jsonl', 'checksums.json', 'audit.json']:
            with self.subTest(missing=name):
                saved = (self.run / name).read_bytes()
                (self.run / name).unlink()
                self.assertEqual('INCOMPLETE', self.fails(name)['status'])
                (self.run / name).write_bytes(saved)
        self.edit_json('completion.json', lambda c: c.update(status='failed'))
        self.assertEqual('INCOMPLETE', self.fails('completed run')['status'])
        self.edit_json('manifest.json', lambda m: m.update(schema=2))
        self.assertEqual('INCOMPLETE', self.fails('evidence verification')['status'])

    def test_malformed_duplicate_keys_and_invalid_lines(self):
        path = self.run / 'records.jsonl'
        path.write_text(path.read_text() + '{broken\n[]\n{"a":1,"a":2}\n')
        self.assertEqual('INCOMPLETE', self.fails('records.jsonl line')['status'])
        (self.run / 'checksums.json').write_text('[]')
        self.assertEqual('INCOMPLETE', self.fails('checksum/audit structure')['status'])

    def test_frozen_source_missing_or_changed(self):
        example = self.root / 'example'
        example.mkdir()
        for name in verifier.FROZEN:
            shutil.copy2(EXAMPLE / name, example / name)
        (example / 'cases.json').unlink()
        result = verifier.verify(self.run, example)
        self.assertEqual('INCOMPLETE', result['status'])
        shutil.copy2(EXAMPLE / 'cases.json', example / 'cases.json')
        (example / 'PROTOCOL.md').write_text('changed')
        result = verifier.verify(self.run, example)
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any(f['check'] == 'frozen file PROTOCOL.md' for f in result['findings']))

    def test_network_and_subprocess_denied_even_checker_malfunctions(self):
        import booth.core as core
        attempted = []

        def broken(*args, **kwargs):
            attempted.append(True)
            socket.create_connection(('127.0.0.1', 1))

        with patch.object(core, 'check', broken):
            result = self.verify_copy()
        self.assertTrue(attempted)
        self.assertEqual('INCOMPLETE', result['status'])
        self.assertTrue(any('forbids network' in f.get('detail', '') for f in result['findings']))
        with verifier.offline():
            with self.assertRaisesRegex(RuntimeError, 'forbids network'):
                subprocess.Popen(['never-run'])
        # No provider adapter or runner is ever imported by this verifier.
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network attempted')):
            self.assertEqual('PASS', verifier.verify(ORIGINAL)['status'])

    def test_cli_create_only_receipt_outside_evidence(self):
        receipt = self.root / 'receipt.json'
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, verifier.main(['--run-dir', str(ORIGINAL), '--receipt', str(receipt)]))
        self.assertEqual('PASS', json.loads(receipt.read_text())['status'])
        self.assertNotIn('reconstructed_summary', json.loads(output.getvalue()))
        for target in [receipt, self.run / 'new.json', EXAMPLE / 'new.json']:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                verifier.main(['--run-dir', str(self.run), '--receipt', str(target)])
        self.assertFalse((self.run / 'new.json').exists())
        self.assertFalse((EXAMPLE / 'new.json').exists())
        (self.run / 'completion.json').unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, verifier.main(['--run-dir', str(self.run)]))

    def test_independent_grammar_and_rounding_boundaries(self):
        F = verifier.Fraction
        for text, expected in {'CAD 1,250.50': (F('1250.5'), 'CAD'), '(42.50 USD)': (F('-42.5'), 'USD'),
                               '.25 million USD': (F(250000), 'USD'), '7.5 percent': (F('0.075'), 'rate'),
                               '2 percentage point': (F(2), 'percentage_points'), '1,25 CAD': None,
                               '$12': None, '12': None, '(-2) CAD': None, '1 thousand days': None}.items():
            self.assertEqual(expected, verifier.quantity(text), text)
        self.assertEqual(F('-2.23'), verifier.round_half_up(F('-2.225'), 2))
        self.assertEqual(F('2.23'), verifier.round_half_up(F('2.225'), 2))


if __name__ == '__main__':
    unittest.main()
