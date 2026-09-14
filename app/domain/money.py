"""Денежная и количественная арифметика.

Все расчёты ведутся в Decimal: копейки округляются по правилу
"половина вверх" (математическое округление), как это принято
в бухгалтерском учёте РФ.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Union

Numeric = Union[Decimal, int, float, str]

MONEY_EXP = Decimal("0.01")
QUANTITY_EXP = Decimal("0.000001")
RATE_EXP = Decimal("0.0001")


def to_decimal(value: Numeric) -> Decimal:
    """Приводит значение к Decimal без потери точности."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # str() отсекает артефакты двоичного представления float
        return Decimal(str(value))
    return Decimal(value)


def money(value: Numeric) -> Decimal:
    """Округляет сумму до копеек."""
    return to_decimal(value).quantize(MONEY_EXP, rounding=ROUND_HALF_UP)


def quantity(value: Numeric) -> Decimal:
    """Округляет количество до шести знаков."""
    return to_decimal(value).quantize(QUANTITY_EXP, rounding=ROUND_HALF_UP)


def rate(value: Numeric) -> Decimal:
    """Округляет коэффициент/ставку до четырёх знаков."""
    return to_decimal(value).quantize(RATE_EXP, rounding=ROUND_HALF_UP)


def vat_amount(base: Numeric, vat_rate: Numeric) -> Decimal:
    """НДС, начисленный сверху на базу (ставка задаётся в процентах)."""
    return money(to_decimal(base) * to_decimal(vat_rate) / Decimal(100))
