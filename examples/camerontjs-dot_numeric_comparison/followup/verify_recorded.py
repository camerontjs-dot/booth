#!/usr/bin/env python3
"""Offline consistency verifier for the original numeric study (run schema 1).

Adapted from the study's pre-publication saved-run auditor, whose SHA-256 is
45e16110eb1727c5c8e0f83a94435a73e9057f1ff2f4911510a0c4437b33837a.
This adaptation is not a fresh independent audit or scientific qualification.
The protocol and frozen original cases govern; runner/grader are hash-only
inputs. BOOTH replays saved strings; neither models nor providers are called.

Run from any directory with --run-dir PATH [--example PATH] [--receipt PATH].
Receipts are optional, create-only and must be outside the audited inputs.
PASS means complete saved-evidence consistency, not external authenticity.
"""
import argparse
import base64
import collections
from contextlib import contextmanager
import datetime
from fractions import Fraction
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import random
import re
import socket
import subprocess
import sys
from unittest.mock import patch

ARMS = ('check', 'validator', 'keyword_evidence', 'numeric_evidence')
SETTINGS = dict(temperature=0.0, seed=42, num_predict=1024, num_ctx=4096,
                timeout_s=300, max_retries=0, confidence_threshold=0.7,
                keyword_threshold=0.5)
NUMBER = r'-?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)'
UNIT = r'CAD|USD|EUR|percentage points?|percent|%|fraction|days?|months?|items?'
CURRENCIES = {'CAD', 'USD', 'EUR'}
FROZEN = {
    'run_example.py': 'dbdc6d82e79cc62714c60eab55fc2229f2ba89416c9c8e256162d8f9c1aaa2fb',
    'grade_answers.py': 'ecb1bf9941f9f35f32eeedd5ef244612b5df0ca20e2369f41dcbe527fc8ff0e1',
    'cases.json': 'd7943aff3311f50d887e14fa0f01d9170d7dd354516ab7f1c6ecddd9f9871232',
    'PROTOCOL.md': '0020ceb2d3f828c6eec1d725572e6768ff27d237261958c9a76127a856339189',
}
CORE_SHA256 = 'a9c17380287f36f3d67c736034652175023ce6ebf15ac904a87934d7b3ee7fb4'
MODEL_DIGEST = 'f4031aab637d1ffa37b42570452ae0e4fad0314754d17ded67322e4b95836f8a'
EVIDENCE = {'manifest.json', 'completion.json', 'model_after.json',
            'provider_calls.jsonl', 'records.jsonl', 'summary.json', 'summary.md'}

def sha(data):
    return hashlib.sha256(data).hexdigest()


def quantity(text):
    """Whole-string bounded grammar, independently implemented using Fraction."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    outer_negative = text.startswith('(') and text.endswith(')')
    if outer_negative:
        text = text[1:-1].strip()
    prefix = re.fullmatch(r'(CAD|USD|EUR)\s+(.+)', text, re.I)
    if prefix:
        unit, value = prefix.group(1), prefix.group(2)
    else:
        suffix = re.fullmatch(r'(.+?)\s*(' + UNIT + r')', text, re.I)
        if not suffix:
            return None
        value, unit = suffix.groups()
    unit = unit.lower()
    dim = {'day':'days', 'month':'months', 'item':'items',
           'percentage point':'percentage_points',
           'percentage points':'percentage_points'}.get(unit, unit)
    if dim.upper() in CURRENCIES:
        dim = dim.upper()
    scale_match = re.fullmatch(r'(.+?)\s+(thousand|million)', value.strip(), re.I)
    scale = 1
    if scale_match:
        if dim not in CURRENCIES:
            return None
        value = scale_match.group(1)
        scale = {'thousand':1000, 'million':1000000}[scale_match.group(2).lower()]
    value = value.strip()
    number_negative = value.startswith('(') and value.endswith(')')
    if number_negative:
        value = value[1:-1].strip()
    if (outer_negative and number_negative) or not re.fullmatch(NUMBER, value):
        return None
    if (outer_negative or number_negative) and value.startswith('-'):
        return None
    number = Fraction(value.replace(',', '')) * scale
    if outer_negative or number_negative:
        number = -number
    if dim in ('percent', '%'):
        number /= 100
        dim = 'rate'
    elif dim == 'fraction':
        dim = 'rate'
    return number, dim


def round_half_up(value, places):
    factor = 10 ** places
    scaled = abs(value) * factor
    integral = scaled.numerator // scaled.denominator
    if scaled - integral >= Fraction(1, 2):
        integral += 1
    return Fraction(integral, factor) * (-1 if value < 0 else 1)


def requested(case):
    target = case['target']
    facts = [line.split(':', 1)[1].strip() for line in case['source'].splitlines()
             if ':' in line and line.split(':', 1)[0].strip() == target]
    if len(facts) != 1:
        return None
    parsed = quantity(facts[0])
    if parsed is None:
        return None
    places = case['round_places']
    if places is not None:
        if parsed[1] not in CURRENCIES or type(places) is not int or places < 0:
            return None
        if f'Round to {places} decimal places using half-up rounding.' not in case['question']:
            return None
        parsed = round_half_up(parsed[0], places), parsed[1]
    return parsed


def grade(answer, case):
    if answer is None or answer == '':
        return 'no_answer'
    if isinstance(answer, str) and not answer.strip():
        return 'no_answer'
    parsed = quantity(answer)
    if parsed is None:
        return 'unscoreable'
    reference = quantity(case['reference']['value'] + ' ' + case['reference']['unit'])
    return 'correct' if parsed == reference else 'wrong'


def strict(answer, case):
    parsed, expected = quantity(answer), requested(case)
    return parsed is not None and expected is not None and parsed == expected


def weak(answer, evidence):
    tokens = set(re.findall(r'[a-z0-9]+', answer.lower()))
    source = set(re.findall(r'[a-z0-9]+', '\n'.join(evidence).lower()))
    return len(tokens & source) / len(tokens) if tokens else 0.0


def comparable(value):
    """Validator prose is implementation-specific; all machine fields compare."""
    if isinstance(value, dict):
        return {k: comparable(v) for k, v in value.items() if k != 'validation_error'}
    if isinstance(value, list):
        return [comparable(v) for v in value]
    return value


@contextmanager
def offline():
    """Block network/process entry points even if a replay checker malfunctions."""
    from contextlib import ExitStack

    def denied(*args, **kwargs):
        raise RuntimeError('offline verifier forbids network and subprocess calls')

    with ExitStack() as stack:
        for module, name in ((socket, 'socket'), (socket, 'create_connection'),
                             (socket, 'getaddrinfo'), (subprocess, 'Popen'),
                             (os, 'system'), (os, 'posix_spawn'), (os, 'posix_spawnp')):
            if hasattr(module, name):
                stack.enter_context(patch.object(module, name, denied))
        import _socket
        stack.enter_context(patch.object(_socket, 'socket', denied))
        yield


def parse_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result

    def invalid(value):
        raise ValueError('non-finite JSON number: ' + value)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def verify(run_dir, example=None):
    """Return a compact receipt. Never write inputs, invoke providers or use Git.

    status is PASS, FAIL (inconsistent evidence), or INCOMPLETE (missing,
    malformed, unsupported, partial or failed run). Both non-PASS states fail.
    """
    run = Path(run_dir).resolve()
    example = Path(example).resolve() if example else Path(__file__).resolve().parents[1]
    findings, hashes = [], {}
    checked = 0
    incomplete = False

    def check(name, condition):
        nonlocal checked
        checked += 1
        if not condition:
            findings.append({'check': name})

    def unavailable(name, exc):
        nonlocal incomplete
        incomplete = True
        findings.append({'check': name, 'detail': f'{type(exc).__name__}: {exc}'})

    def load(name, root=run, lines=False):
        try:
            data = (root / name).read_bytes()
            hashes[('example/' if root == example else '') + name] = sha(data)
            if lines:
                result = []
                for number, line in enumerate(data.decode('utf-8').splitlines(), 1):
                    try:
                        item = parse_json(line)
                        if not isinstance(item, dict):
                            raise ValueError('record must be an object')
                        result.append(item)
                    except (ValueError, TypeError) as exc:
                        unavailable(f'{name} line {number}', exc)
                return result
            return parse_json(data)
        except (OSError, ValueError, UnicodeError) as exc:
            unavailable(name, exc)
            return None

    manifest = load('manifest.json')
    completion = load('completion.json')
    checksums = load('checksums.json')
    audit = load('audit.json')
    model_after = load('model_after.json')
    summary = load('summary.json')
    records = load('records.jsonl', lines=True)
    traces = load('provider_calls.jsonl', lines=True)
    dataset = load('cases.json', example)
    # Hash every surviving original member before semantic validation, even for
    # partial evidence. audit.json was added later and is NOT an original member.
    for name in sorted(EVIDENCE | {'summary.md'}):
        try:
            hashes[name] = sha((run / name).read_bytes())
        except OSError as exc:
            unavailable(name, exc)
    for name, expected in FROZEN.items():
        try:
            actual = sha((example / name).read_bytes())
            hashes['example/' + name] = actual
            check('frozen file ' + name, actual == expected)
        except OSError as exc:
            unavailable('frozen file ' + name, exc)
    try:
        check('original checksum membership (audit excluded)', set(checksums) == EVIDENCE)
        for name in sorted(EVIDENCE):
            check('saved hash ' + name, hashes.get(name) == checksums.get(name))
        check('prior compact audit lineage', audit['schema'] == 2 and
              audit['audit_kind'] == 'independent_saved_run_consistency' and
              audit['status'] == 'PASS' and audit['scientific_qualification'] is False and
              audit['checks'] == dict(total=1026, passed=1026, failed=0) and
              audit['failures'] == [] and audit['evidence_sha256'] == checksums and
              audit['audit_script'] == dict(included=False, sha256=
              '45e16110eb1727c5c8e0f83a94435a73e9057f1ff2f4911510a0c4437b33837a') and
              audit['full_receipt_sha256'] ==
              '2928bbda94f56c6a81198e7d82e5b5642b54815f9046f21403502e55e8b5835d')
    except (KeyError, TypeError, AttributeError) as exc:
        unavailable('checksum/audit structure', exc)
    reconstructed = {}
    try:
        if manifest['schema'] != 1:
            raise ValueError('only original run schema 1 is supported')
        if completion['status'] != 'completed':
            incomplete = True
            check('completed run', False)
        check('original main study', manifest['phase'] == 'main' and manifest['controls_only'] is False)
        check('manifest frozen files', manifest['file_hashes'] == FROZEN)
        check('original source identity', manifest['source_commit'] ==
              'ea28a68f62affd1b6f36001d181ca4730eea47fa' and manifest['source_tree'] ==
              '502b9b19971899bccd123441dac9d7744645a569')
        check('settings frozen', manifest['settings'] == SETTINGS)
        check('BOOTH version', manifest['booth_version'] == manifest['installed_distribution'] == '0.5.9')
        check('model digest before/after', manifest['model']['digest'] == model_after['digest'] == MODEL_DIGEST)
        check('model and quantization', manifest['model']['name'] == model_after['name'] == 'gemma3:12b' and
              manifest['model']['details']['quantization_level'] == model_after['details']['quantization_level'] == 'Q4_K_M')
        cases = list(dataset['cases'])
        random.Random(42).shuffle(cases)
        order = [case['id'] for case in cases]
        by_id = {case['id']: case for case in cases}
        check('case identity and order', len(cases) == len(by_id) == 20 and
              manifest['cases'] == cases and manifest['case_order'] == order)
        check('record and provider call counts', len(records) == completion['records'] == 60 and
              len(traces) == 21 and completion['live_case_calls'] == 20 and completion['warmup_calls'] == 1)
        if len(records) != 60 or len(traces) != 21:
            incomplete = True
        check('ordered provider coverage', [t['case_id'] for t in traces] == ['__warmup__'] + order)
        expected_records = [(i, 'authored_controls', c) for i in order for c in ('correct', 'wrong')]
        expected_records += [(i, 'live_gemma', None) for i in order]
        check('ordered record coverage', [(r['case_id'], r['layer'], r.get('control')) for r in records] == expected_records)
        # Verify imported bytes before executing BOOTH; installed path is not an
        # identity, and may legitimately differ from the original machine path.
        with offline():
            import booth.core as core
            core_matches = sha(Path(inspect.getfile(core)).read_bytes()) == CORE_SHA256
            check('actual BOOTH core hash', core_matches and manifest['booth_core_sha256'] == CORE_SHA256)
            distributions = importlib.metadata.packages_distributions().get('booth', [])
            check('installed BOOTH 0.5.9', bool(distributions) and all(
                importlib.metadata.version(name) == '0.5.9' for name in distributions))
            if not core_matches:
                raise ValueError('refusing replay with changed BOOTH core')
            for i, trace in enumerate(traces):
                try:
                    name = f'trace {i} '
                    request = parse_json(trace['request_text'])
                    check(name + 'request hash', sha(trace['request_text'].encode()) == trace['request_sha256'])
                    options = {k: SETTINGS[k] for k in ('temperature', 'seed', 'num_predict', 'num_ctx')}
                    if trace['case_id'] == '__warmup__':
                        prompt = 'Reply with ready.'
                        options['num_predict'] = 8
                    else:
                        prompt = core._build_prompt(prompt_for(by_id[trace['case_id']]))
                    check(name + 'request and default prompt', request == dict(model='gemma3:12b',
                          prompt=prompt, stream=False, keep_alive='5m', options=options))
                    raw = base64.b64decode(trace['response_base64'], validate=True)
                    check(name + 'HTTP bytes hash', sha(raw) == trace['response_sha256'])
                    check(name + 'HTTP bytes/text', raw.decode('utf-8') == trace['response_text'])
                    response = parse_json(raw)
                    check(name + 'raw reply', response['response'] == trace['raw_reply'])
                    done = (response['done'] is True and trace['done'] is True and
                            response['done_reason'] == trace['done_reason'] == 'stop' and trace['error'] is None)
                    check(name + 'generation complete', done)
                    incomplete |= not done
                    check(name + 'response model', response['model'] == 'gemma3:12b')
                    check(name + 'elapsed bounded', 0 < trace['elapsed_s'] <= 300)
                except (KeyError, TypeError, ValueError, UnicodeError) as exc:
                    unavailable(f'trace {i} structure', exc)
            for i, record in enumerate(records):
                try:
                    case = by_id[record['case_id']]
                    name = f'record {i} '
                    if record['layer'] == 'authored_controls':
                        raw = record['fixture_reply']
                        check(name + 'authored fixture', parse_json(raw) == dict(ambiguous=False,
                              interpretations=[], chosen_interpretation=None,
                              answer=case[record['control'] + '_answer'], confidence=0.99) and record['provider_calls'] == 0)
                    elif record['layer'] == 'live_gemma':
                        index = order.index(case['id']) + 1
                        check(name + 'one provider trace', record['provider_trace_index'] == index and record['provider_calls'] == 1)
                        raw = traces[index]['raw_reply']
                    else:
                        raise ValueError('unknown record layer')
                    sent = []

                    def replay(prompt):
                        sent.append(prompt)
                        return raw

                    prompt = prompt_for(case)
                    a = core.check(replay, prompt, threshold=0.7, max_retries=0)
                    b = core.check(replay, prompt, threshold=0.7, max_retries=0,
                                   validator=lambda answer: strict(answer, case))
                    c = core.check_with_evidence(a.answer, [case['source']], weak, evidence_threshold=0.5)
                    d = core.check_with_evidence(a.answer, [case['source']], lambda answer, evidence: strict(answer, case))
                    check(name + 'two replays/no retries', sent == [core._build_prompt(prompt)] * 2)
                    check(name + 'matched parsed answers', record['answer'] == a.answer and
                          set(record['arms']) == set(ARMS) and all(x['answer'] == a.answer for x in record['arms'].values()))
                    check(name + 'category', record['category'] == case['category'])
                    check(name + 'independent reference grade', record['grade']['label'] == grade(a.answer, case))
                    if record['layer'] == 'authored_controls':
                        check(name + 'declared control', grade(a.answer, case) == record['control'])
                    rule = record['numeric_rule']
                    check(name + 'requested-field decision', rule['passed'] is strict(a.answer, case))
                    for label, parsed in [('answer', quantity(a.answer)), ('source', requested(case))]:
                        if parsed is not None:
                            check(name + label + ' rule quantity', rule[label + '_dimension'] == parsed[1] and
                                  Fraction(rule[label + '_value']) == parsed[0])
                    for arm, result in zip(ARMS, (a, b, c, d)):
                        check(name + 'replayed ' + arm, comparable(record['arms'][arm]) == comparable(result.to_dict()))
                except Exception as exc:
                    unavailable(f'record {i} replay', exc)
        reconstructed = summaries(records, by_id)
        check('summary JSON reconstruction', summary == reconstructed)
        markdown = (run / 'summary.md').read_text()
        rows = {'All answer-checks': 'attempted', 'Correct answers': 'correct', 'Wrong answers': 'wrong',
                'Unscoreable answers': 'unscoreable', 'Missing answers': 'no_answer', 'Wrong accepted': 'wrong_accepted',
                'Wrong withheld': 'wrong_withheld', 'Correct accepted': 'correct_accepted', 'Correct withheld': 'correct_withheld',
                'Unscoreable accepted': 'unscoreable_accepted', 'Unscoreable withheld': 'unscoreable_withheld',
                'Call failures': 'call_failed', 'All-parse-failed': 'all_parse_failed', 'Checker failures': 'checker_failed'}
        for layer in reconstructed:
            section = markdown.split('## ' + layer + '\n', 1)[1].split('\n## ', 1)[0]
            for label, key in rows.items():
                check('report ' + layer + ' ' + key, '| ' + label + ' | ' + ' | '.join(
                    str(reconstructed[layer][a][key]) for a in ARMS) + ' |' in section)
            for status in ('ACCEPTED', 'REPAIRED', 'BLOCKED', 'UNCERTAIN', 'AMBIGUOUS'):
                check('report ' + layer + ' ' + status, '| Status ' + status + ' | ' + ' | '.join(
                    str(reconstructed[layer][a]['statuses'].get(status, 0)) for a in ARMS) + ' |' in section)
        check('report source/model identity', MODEL_DIGEST in markdown and manifest['source_commit'] in markdown)
    except Exception as exc:
        unavailable('evidence verification', exc)
    return dict(schema=1, verifier_kind='adapted_original_saved_run_consistency',
                scientific_qualification=False, status='INCOMPLETE' if incomplete else ('FAIL' if findings else 'PASS'),
                checks=dict(total=checked + sum('detail' in f for f in findings),
                            passed=checked - sum('detail' not in f for f in findings), failed=len(findings)),
                findings=findings, evidence_sha256=hashes, reconstructed_summary=reconstructed,
                network_or_inference_calls=0, verifier_sha256=sha(Path(__file__).read_bytes()),
                verified_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())


def prompt_for(case):
    return ('Use only the synthetic source below to answer the question.\nSource:\n' +
            case['source'] + '\n\nQuestion: ' + case['question'])


def summaries(records, by_id):
    metrics = ['attempted', 'correct', 'wrong', 'unscoreable', 'no_answer', 'correct_accepted',
               'correct_withheld', 'wrong_accepted', 'wrong_withheld', 'unscoreable_accepted',
               'unscoreable_withheld', 'no_answer_accepted', 'no_answer_withheld',
               'call_failed', 'all_parse_failed', 'checker_failed']
    result = {}
    for layer in ('authored_controls', 'live_gemma'):
        result[layer] = {}
        for arm in ARMS:
            count, statuses = dict.fromkeys(metrics, 0), collections.Counter()
            for record in records:
                if record['layer'] != layer:
                    continue
                outcome = record['arms'][arm]
                label = grade(record['answer'], by_id[record['case_id']])
                count['attempted'] += 1
                count[label] += 1
                count[label + ('_accepted' if outcome['ok'] else '_withheld')] += 1
                for flag in ('call_failed', 'all_parse_failed', 'checker_failed'):
                    count[flag] += int(outcome[flag])
                statuses[outcome['status']] += 1
            count['statuses'] = dict(statuses)
            result[layer][arm] = count
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--example', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args(argv)
    if args.receipt:
        receipt = args.receipt.resolve()
        if any(receipt.is_relative_to(p.resolve()) for p in (args.run_dir, args.example)):
            parser.error('receipt must be outside audited evidence and example')
        if receipt.exists():
            parser.error('receipt must be a new file')
    result = verify(args.run_dir, args.example)
    if args.receipt:
        try:
            with args.receipt.open('x') as stream:
                stream.write(json.dumps(result, indent=2) + '\n')
        except OSError as exc:
            print(json.dumps(dict(status='FAIL', findings=[dict(check='receipt write', detail=str(exc))])))
            return 1
    print(json.dumps({k: v for k, v in result.items() if k != 'reconstructed_summary'}, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
