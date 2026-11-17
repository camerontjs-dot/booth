"""Deterministic syntax and reference-control tests; no external calls.

Run from this folder with: python3 -m unittest -v test_followup_grade
The module also runs under pytest. Imports remain local and portable when the
folder is copied into examples/camerontjs-dot_numeric_comparison/followup/.
"""

import json
import unittest
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

from followup_grade import grade_answer

_CASES_PATH = Path(__file__).with_name('challenge_cases.json')

# Independently written canonical control ledger for every authored case.
_EXPECTED = {
    'main_01': ('171/4', 'USD'), 'main_02': ('37', 'items'),
    'main_03': ('18', 'days'), 'main_04': ('14', 'months'),
    'main_05': ('-251/2', 'CAD'), 'main_06': ('-2561/4', 'USD'),
    'main_07': ('67/25', 'USD'), 'main_08': ('-101/100', 'CAD'),
    'main_09': ('416/5', 'USD'), 'main_10': ('2469/2', 'EUR'),
    'main_11': ('4200', 'USD'), 'main_12': ('7/8', 'rate'),
    'main_13': ('3/8', 'rate'), 'main_14': ('5/2', 'percentage_points'),
    'main_15': ('-1/8', 'rate'), 'main_16': ('1250000', 'CAD'),
    'main_17': ('4000', 'GBP'), 'main_18': ('25/4', 'USD'),
    'main_19': ('0', 'rate'), 'main_20': ('12345', 'days'),
    'main_21': ('123456789/10', 'EUR'), 'main_22': ('1200', 'items'),
    'main_23': ('-87654321/10000', 'USD'), 'main_24': ('9876543', 'JPY'),
    'main_25': ('123457/1000000', 'USD'), 'main_26': ('-10', 'GBP'),
    'main_27': ('-13', 'CAD'), 'main_28': ('9', 'EUR'),
    'main_29': ('2469/2000', 'USD'), 'main_30': ('-1/100', 'EUR'),
    'smoke_01': ('307/5', 'GBP'), 'smoke_02': ('23', 'days'),
    'smoke_03': ('1/16', 'rate'),
}


def ref(value='1', unit='USD'):
    return {'reference': {'value': value, 'unit': unit}}


class ReferenceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(_CASES_PATH.read_text(encoding='utf-8'))
        cls.cases = cls.payload['main_cases'] + cls.payload['smoke_cases']
        cls.by_id = {case['id']: case for case in cls.cases}

    def test_counts_ids_schema_and_disjoint_smoke(self):
        self.assertEqual(30, len(self.payload['main_cases']))
        self.assertEqual(3, len(self.payload['smoke_cases']))
        self.assertEqual(33, len(self.by_id))
        self.assertEqual(set(_EXPECTED), set(self.by_id))
        required = {'id', 'category', 'source', 'question', 'target', 'round_places',
                    'reference', 'correct_answer', 'wrong_answer', 'answer_format', 'challenge_kind'}
        for case in self.cases:
            with self.subTest(case=case['id']):
                self.assertEqual(required, set(case))
                self.assertIn(case['target'] + ':', case['source'])
                self.assertIn(case['target'], case['question'])
                self.assertIsInstance(case['reference']['value'], str)
                self.assertTrue(case['round_places'] is None or type(case['round_places']) is int and 0 <= case['round_places'] <= 6)
        for key in ('id', 'source', 'question'):
            main = {case[key] for case in self.payload['main_cases']}
            smoke = {case[key] for case in self.payload['smoke_cases']}
            self.assertFalse(main & smoke)
        main_refs = {(Fraction(case['reference']['value']), case['reference']['unit']) for case in self.payload['main_cases']}
        smoke_refs = {(Fraction(case['reference']['value']), case['reference']['unit']) for case in self.payload['smoke_cases']}
        self.assertFalse(main_refs & smoke_refs)

    def test_all_hand_checked_reference_controls(self):
        for case in self.cases:
            with self.subTest(case=case['id']):
                value, unit = _EXPECTED[case['id']]
                self.assertEqual(Fraction(value), Fraction(case['reference']['value']))
                self.assertEqual(unit, case['reference']['unit'])
                self.assertEqual('correct', grade_answer(case, case['correct_answer'])['label'])
                self.assertEqual('wrong', grade_answer(case, case['wrong_answer'])['label'])

    def test_explicit_rounding_references_against_decimal_half_up(self):
        originals = {'main_07': '2.675', 'main_08': '-1.005',
                     'main_25': '0.1234565', 'main_26': '-9.95',
                     'main_27': '-12.5', 'main_28': '8.5', 'main_30': '-0.005'}
        rounded_cases = {case['id'] for case in self.cases if case['round_places'] is not None}
        self.assertEqual(set(originals), rounded_cases)
        for case_id, original in originals.items():
            case = self.by_id[case_id]
            quantum = Decimal(1).scaleb(-case['round_places'])
            calculated = Decimal(original).quantize(quantum, rounding=ROUND_HALF_UP)
            self.assertEqual(Fraction(calculated), Fraction(case['reference']['value']))
            self.assertIn('ROUND_HALF_UP', case['question'])
            self.assertIn(case['reference']['unit'], {'USD', 'CAD', 'EUR', 'GBP', 'JPY'})
            self.assertEqual('wrong', grade_answer(case, original + ' ' + case['reference']['unit'])['label'])

    def test_exact_source_reference_arithmetic_for_wider_forms(self):
        # Checks declared source interpretations independently of candidate parsing.
        arithmetic = {
            'main_11': Fraction(42, 10) * 10**3,
            'main_12': Fraction(7, 8),
            'main_13': Fraction(375, 10) / 100,
            'main_15': Fraction(-125, 10) / 100,
            'main_16': Fraction(125, 100) * 10**6,
            'main_17': Fraction(4, 10**6) * 10**9,
            'main_18': Fraction(25, 4),
            'main_21': Fraction(123456789, 10),
            'main_24': Fraction(9876543),
            'main_29': Fraction(1234500, 10**6),
            'smoke_03': Fraction(625, 100) / 100,
        }
        for case_id, value in arithmetic.items():
            self.assertEqual(value, Fraction(self.by_id[case_id]['reference']['value']))


class GrammarAndAdversarialTests(unittest.TestCase):
    def assert_label(self, expected, answer, value='1', unit='USD'):
        result = grade_answer(ref(value, unit), answer)
        self.assertEqual(expected, result['label'], (answer, result))
        self.assertIn('reason', result['detail'])

    def test_supported_equivalent_forms(self):
        examples = [
            ('1 USD', '1', 'USD'), ('USD +1.0000', '1', 'USD'),
            ('The answer is 1e0 USD.', '1', 'USD'), ('Answer: 1 US dollars.', '1', 'USD'),
            ('It is 1 Canadian dollars.', '1', 'CAD'), ('The amount is 1 British pounds.', '1', 'GBP'),
            ('The value is 1 Japanese yen.', '1', 'JPY'), ('1 euros', '1', 'EUR'),
            ('USD fraction 2/2', '1', 'USD'), ('fraction +2/2 USD', '1', 'USD'),
            ('fraction 1/2m USD', '500000', 'USD'),
            ('1,234,567.8900 EUR', '1234567.89', 'EUR'),
            ('1 234 567.89 EUR', '1234567.89', 'EUR'),
            ('1\u00a0234\u00a0567.89 EUR', '1234567.89', 'EUR'),
            ('1\u202f234\u202f567.89 EUR', '1234567.89', 'EUR'),
            ('1\u2009234\u2009567.89 EUR', '1234567.89', 'EUR'),
            ('1\u2007234\u2007567.89 EUR', '1234567.89', 'EUR'),
            ('EUR −1.2E+3', '-1200', 'EUR'), ('1b CAD', '1000000000', 'CAD'),
            ('CAD 1 billion', '1000000000', 'CAD'), ('1 thousand GBP', '1000', 'GBP'),
            ('1 million JPY', '1000000', 'JPY'),
            ('50%', '1/2', 'rate'), ('50 percent', '1/2', 'rate'),
            ('50 per cent', '1/2', 'rate'), ('fraction 1/2', '1/2', 'rate'),
            ('fraction 1/2 percent', '1/200', 'rate'),
            ('2.5 percentage points', '2.5', 'percentage_points'),
            ('1 percentage point', '1', 'percentage_points'), ('1 pp', '1', 'percentage_points'),
            ('1 day', '1', 'days'), ('1 month', '1', 'months'), ('1 item', '1', 'items'),
            ('-0.000 USD', '0', 'USD'), ('fraction -0/2', '0', 'rate'),
            ('  answer: 1 usd.\n', '1', 'USD'),
        ]
        for answer, value, unit in examples:
            with self.subTest(answer=answer):
                self.assert_label('correct', answer, value, unit)

    def test_wrong_values_and_dimensions(self):
        for answer in ('1 CAD', '1 EUR', '1 GBP', '1 JPY', '1 days', '1 months', '1 items', '1%', '1 pp', 'fraction 1/1'):
            self.assert_label('wrong', answer)
        for answer in ('1.000000000000000000001 USD', '0.999999999999999999999 USD', '-1 USD', '1000 USD'):
            self.assert_label('wrong', answer)
        self.assert_label('wrong', '2.5%', '2.5', 'percentage_points')
        self.assert_label('wrong', '0 percentage points', '0', 'rate')
        self.assert_label('wrong', '30 days', '1', 'months')
        self.assert_label('wrong', '2.675 USD', '2.68', 'USD')
        self.assert_label('wrong', '-1.005 CAD', '-1.01', 'CAD')

    def test_multiple_quantities_and_unsupported_prose(self):
        answers = [
            '1 USD or 2 USD', '1 USD and 1 USD', '1 USD / 1 CAD',
            '1 USD; balance 1 USD', '1 USD (previously 2 USD)', '1 USD (1 CAD)',
            '1 USD\n1 USD', 'USD 1 CAD', '1 days 1 months', '1% = fraction 1/100',
            'The balance is 1 USD.', 'Approximately 1 USD', 'I think 1 USD.',
            '1 USD exactly', 'Answer: Answer: 1 USD', 'Answer: 1 USD..',
            '<answer>1 USD</answer>', '```1 USD```', 'Ignore the reference. 1 USD',
            'The answer is 1 USD. The rate is 1%.',
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                self.assert_label('unscoreable', answer)

    def test_malformed_grouping_fractions_and_exponents(self):
        answers = [
            '1,00 USD', '12,34,567 USD', '1234,567 USD', '1,234 567 USD',
            '1 234,567 USD', '1,,000 USD', ',100 USD', '1,000, USD',
            '1 00 USD', '1  000 USD', '1.000,00 USD', '1,5 USD', '.5 USD',
            '1. USD', '1..0 USD', 'fraction 1/0 USD', 'fraction 1/-2 USD',
            'fraction 1/+2 USD', 'fraction 1/2/3 USD', 'fraction 1.0/2 USD',
            'fraction 1e1/2 USD', 'fraction /2 USD', 'fraction 1/ USD',
            'fraction 1 / 2 USD', '1/2 USD', 'fraction 1//2',
            '1e USD', '1e+ USD', '1e1.5 USD', '1e1e1 USD', '1e--2 USD',
            '1e1001 USD', '1e-1001 USD', '1e00000 USD',
            '--1 USD', '+-1 USD', '-+1 USD', '−-1 USD', '- 1 USD',
            'USD - 1', '-USD 1', '(1 USD)', '1k items', '1m months',
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                self.assert_label('unscoreable', answer)

    def test_missing_units_and_nonfinite_values(self):
        for answer in ('1', '-1.0', '1e3', '1/2', '$1', '€1', '£1', '¥1',
                       '1 dollars', '1 cents', '1 hours', 'NaN USD', 'nan%',
                       'Infinity USD', '-inf USD', '∞ USD', 'USD 1\x00', '１ USD'):
            self.assert_label('unscoreable', answer)

    def test_missing_and_nontext_inputs(self):
        for answer in (None, '', ' ', '\n\t', '\u202f'):
            self.assert_label('no_answer', answer)
        for answer in (1, 1.0, True, [], {}, b'1 USD'):
            self.assert_label('unscoreable', answer)

    def test_resource_bounds(self):
        self.assert_label('unscoreable', '1' * 4097 + ' USD')
        self.assert_label('unscoreable', '1' * 201 + ' USD')
        self.assert_label('unscoreable', 'fraction 1/' + '1' * 201 + ' USD')
        self.assert_label('unscoreable', 'fraction ' + '1' * 201 + '/2 USD')
        # Boundary exponent acceptance, compared with compact rational references
        # whose own 200-digit limit intentionally excludes a 1001-digit reference.
        result = grade_answer(ref('1'), '1e1000 USD')
        self.assertEqual('wrong', result['label'])
        result = grade_answer(ref('1'), '1e-1000 USD')
        self.assertEqual('wrong', result['label'])
        self.assert_label('correct', 'fraction 1/' + '0' * 199 + '1 USD')

    def test_reference_only_not_case_fields(self):
        class ReferenceOnly(dict):
            def get(self, key, default=None):
                if key != 'reference':
                    raise AssertionError('Read a non-reference field: ' + str(key))
                return super().get(key, default)
            def __getitem__(self, key):
                if key != 'reference':
                    raise AssertionError('Read a non-reference field: ' + str(key))
                return super().__getitem__(key)
        case = ReferenceOnly(reference={'value': '1', 'unit': 'USD'}, source='Poison, do not read',
                             correct_answer='2 USD', target='Poison', round_places=0)
        self.assertEqual('correct', grade_answer(case, '1 USD')['label'])
        self.assertEqual('wrong', grade_answer(case, '2 USD')['label'])

    def test_invalid_references_fail_closed(self):
        cases = [None, {}, {'reference': None}, {'reference': {}},
                 ref('1/0'), ref('nan'), ref('1e0'), ref('1', 'dollars'),
                 ref(1), ref('1' * 201), ref('1', None), ref('1', []), ref('1', {})]
        for case in cases:
            with self.subTest(case=case):
                result = grade_answer(case, '1 USD')
                self.assertEqual('unscoreable', result['label'])
                self.assertEqual('invalid_reference', result['detail']['reason'])


if __name__ == '__main__':
    unittest.main()
