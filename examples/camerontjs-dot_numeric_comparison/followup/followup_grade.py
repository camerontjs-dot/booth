"""Bounded independent exact-rational reference grader, Python 3.9+.

This is a declared syntax grader, not an unrestricted semantic judge. It reads
only case['reference']; it never reads the source, target, round_places, or any
production checker. References already contain the final quantity, including
any explicitly requested monetary half-up rounding. Candidate answers are NEVER
rounded or compared with a tolerance.

Grammar (case-insensitive words and currency codes):
  answer   := quantity | wrapper(quantity)
  wrappers := 'Answer: Q' | 'The answer is Q' | 'It is Q'
              | 'The amount is Q' | 'The value is Q'
  One optional final period is permitted, with or without a wrapper.
  quantity := CURRENCY SPACE number [scale]
              | number [scale] SPACE CURRENCY
              | number ('%' | SPACE 'percent' | SPACE 'per cent')
              | number SPACE ('percentage point[s]' | 'pp')
              | number SPACE ('day[s]' | 'month[s]' | 'item[s]')
              | 'fraction' SPACE signed_integer '/' positive_integer
  number   := signed_decimal [exponent] | 'fraction' SPACE signed_integer
              '/' positive_integer
  decimal  := digits with optional '.' and following digits; at least one digit
              before the decimal point. Integer grouping may use comma OR space,
              with first group 1..3 digits and all later groups exactly 3 digits.
  exponent := ('e' | 'E') ['+' | '-'] digits, magnitude at most 1000.
  scale    := [' '] ('k' | 'm' | 'b' | 'thousand' | 'million' | 'billion')
              (scales are accepted ONLY with explicit currency).

CURRENCY: USD/CAD/EUR/GBP/JPY; aliases US dollars, Canadian dollars, euros,
British pounds, Japanese yen. No bare currency symbols. Percent is a rate with
base unit 'rate' (divided by 100); bare explicit 'fraction n/d' is a base rate.
Percentage points are a separate dimension. Days, months, items and each currency
are separate dimensions. Fraction numerators may have one sign; denominators
must be unsigned and strictly positive. No implicit bare fractions.

Unicode minus U+2212 is an ASCII minus alias. NBSP U+00A0, narrow NBSP U+202F,
thin space U+2009, and figure space U+2007 are ordinary space aliases. Leading
and trailing whitespace is ignored; internal whitespace must match the grammar.
Accounting parentheses, decimal commas, locale inference, free prose, multiple
quantities, sign conflicts, NaN/infinity and missing units are unsupported.
Input length is bounded at 4096 characters; each numeric component at 200 digits.
"""

import re
from collections.abc import Mapping
from fractions import Fraction

VERSION = 'booth-followup-reference-v1'
_MAX_LENGTH = 4096
_MAX_DIGITS = 200
_TRANSLATE = str.maketrans({'\u2212': '-', '\u00a0': ' ', '\u202f': ' ', '\u2009': ' ', '\u2007': ' '})
_INTEGER = r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,3}(?: [0-9]{3})+)'
_DECIMAL = r'[+-]?' + _INTEGER + r'(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,4})?'
_FRACTION = r'fraction [+-]?[0-9]+/[0-9]+'
_NUMBER = r'(?:' + _FRACTION + '|' + _DECIMAL + ')'
_SCALE = r'(?: ?(?:thousand|million|billion|k|m|b))?'
_CURRENCY = r'(?:USD|CAD|EUR|GBP|JPY|US dollars|Canadian dollars|euros|British pounds|Japanese yen)'
_CURRENCIES = {
    'usd': 'USD', 'us dollars': 'USD',
    'cad': 'CAD', 'canadian dollars': 'CAD',
    'eur': 'EUR', 'euros': 'EUR',
    'gbp': 'GBP', 'british pounds': 'GBP',
    'jpy': 'JPY', 'japanese yen': 'JPY',
}
_SCALES = {'k': 1000, 'thousand': 1000, 'm': 10**6, 'million': 10**6,
           'b': 10**9, 'billion': 10**9}
_BASE_UNITS = {'USD', 'CAD', 'EUR', 'GBP', 'JPY', 'rate',
               'percentage_points', 'days', 'months', 'items'}
_WRAPPERS = re.compile(r'(?:Answer: |The answer is |It is |The amount is |The value is )(.+)', re.I)
_PREFIX_CURRENCY = re.compile(r'(?P<unit>' + _CURRENCY + r') (?P<number>' + _NUMBER + r')(?P<scale>' + _SCALE + r')', re.I)
_SUFFIX_CURRENCY = re.compile(r'(?P<number>' + _NUMBER + r')(?P<scale>' + _SCALE + r') (?P<unit>' + _CURRENCY + ')', re.I)
_SUFFIX_UNIT = re.compile(r'(?P<number>' + _NUMBER + r')(?P<unit>%| percent| per cent| percentage points?| pp| days?| months?| items?)', re.I)
_REFERENCE_NUMBER = re.compile(r'[+-]?[0-9]+(?:\.[0-9]+|/[0-9]+)?')


class _SyntaxError(ValueError):
    pass


def _number(text):
    """Parse a full grammar-matched number without any binary float."""
    if text.lower().startswith('fraction '):
        numerator, denominator = text[9:].split('/')
        if len(numerator.lstrip('+-')) > _MAX_DIGITS or len(denominator) > _MAX_DIGITS:
            raise _SyntaxError('numeric_component_too_long')
        if int(denominator) == 0:
            raise _SyntaxError('zero_denominator')
        return Fraction(int(numerator), int(denominator))
    compact = text.replace(',', '').replace(' ', '')
    pieces = re.split('[eE]', compact)
    mantissa = pieces[0]
    exponent = int(pieces[1]) if len(pieces) == 2 else 0
    if abs(exponent) > 1000:
        raise _SyntaxError('exponent_out_of_range')
    sign = -1 if mantissa.startswith('-') else 1
    mantissa = mantissa.lstrip('+-')
    integer, dot, decimal = mantissa.partition('.')
    if len(integer + decimal) > _MAX_DIGITS:
        raise _SyntaxError('numeric_component_too_long')
    value = Fraction(sign * int(integer + decimal), 10 ** len(decimal))
    return value * (Fraction(10 ** exponent) if exponent >= 0 else Fraction(1, 10 ** -exponent))


def _quantity(answer):
    text = answer.translate(_TRANSLATE).strip()
    if text.endswith('.'):
        text = text[:-1]
    wrapper = _WRAPPERS.fullmatch(text)
    if wrapper:
        text = wrapper.group(1)
    for pattern in (_PREFIX_CURRENCY, _SUFFIX_CURRENCY):
        match = pattern.fullmatch(text)
        if match:
            value = _number(match.group('number'))
            scale = match.group('scale').strip().lower()
            return value * _SCALES.get(scale, 1), _CURRENCIES[match.group('unit').lower()]
    match = _SUFFIX_UNIT.fullmatch(text)
    if match:
        value = _number(match.group('number'))
        unit = match.group('unit').strip().lower()
        if unit in ('%', 'percent', 'per cent'):
            return value / 100, 'rate'
        if unit in ('percentage point', 'percentage points', 'pp'):
            return value, 'percentage_points'
        for singular, plural in (('day', 'days'), ('month', 'months'), ('item', 'items')):
            if unit in (singular, plural):
                return value, plural
    if re.fullmatch(_FRACTION, text, re.I):
        return _number(text), 'rate'
    raise _SyntaxError('unsupported_or_ambiguous_syntax')


def _reference(case):
    if not isinstance(case, Mapping) or not isinstance(case.get('reference'), Mapping):
        raise _SyntaxError('invalid_reference')
    reference = case['reference']
    value, unit = reference.get('value'), reference.get('unit')
    if (not isinstance(value, str) or not _REFERENCE_NUMBER.fullmatch(value)
            or not isinstance(unit, str) or unit not in _BASE_UNITS):
        raise _SyntaxError('invalid_reference')
    if sum(char.isdigit() for char in value) > _MAX_DIGITS:
        raise _SyntaxError('invalid_reference')
    try:
        return Fraction(value), unit
    except (ValueError, ZeroDivisionError):
        raise _SyntaxError('invalid_reference')


def grade_answer(case, answer):
    """Return label and bounded details, using only the canonical reference.

    correct/wrong require one grammar-supported quantity. Valid different units
    are wrong. Empty string, whitespace or None are no_answer. All other missing,
    invalid, unsupported or ambiguous material is unscoreable. Invalid reference
    data is unscoreable with reason invalid_reference.
    """
    if answer is None or isinstance(answer, str) and not answer.strip():
        return {'label': 'no_answer', 'detail': {'reason': 'empty_answer'}}
    if not isinstance(answer, str):
        return {'label': 'unscoreable', 'detail': {'reason': 'answer_must_be_text'}}
    if len(answer) > _MAX_LENGTH:
        return {'label': 'unscoreable', 'detail': {'reason': 'answer_too_long'}}
    try:
        expected_value, expected_unit = _reference(case)
        actual_value, actual_unit = _quantity(answer)
    except _SyntaxError as error:
        return {'label': 'unscoreable', 'detail': {'reason': str(error)}}
    same_unit = actual_unit == expected_unit
    same_value = actual_value == expected_value
    correct = same_unit and same_value
    reason = 'exact_match' if correct else ('wrong_unit' if not same_unit else 'wrong_value')
    return {'label': 'correct' if correct else 'wrong', 'detail': {
        'reason': reason,
        'actual': {'value': str(actual_value), 'unit': actual_unit},
        'reference': {'value': str(expected_value), 'unit': expected_unit},
    }}
