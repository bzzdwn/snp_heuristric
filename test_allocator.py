"""Тесты распределения. Запуск: python -m pytest -q"""
import random
from dataclasses import replace
from pathlib import Path

import pytest

from allocator import Request, _effective_min, _round_up, allocate
from main import load_cases

CASES = {c.case_id: c for c in load_cases(Path(__file__).parent / "data")}


def run(case_id: str) -> dict[str, int]:
    c = CASES[case_id]
    return allocate(c.available_qty, c.requests)


# ---------------------------------------------------------------- кейсы из CSV

def test_case_01_overship_from_leftover():
    """Кратность 25 при спросе 40: сначала всем по 25, остаток 25 — перегрузом одной заявке.
    Сломается, если округлять вверх сразу (50/50/0) или запретить перегруз (25 на складе)."""
    assert run("CASE_01") == {"R-101": 50, "R-102": 25, "R-103": 25}


def test_case_02_min_lot_excludes_one_and_reshares():
    """Доля 25 < min_lot 30: исключается одна заявка (R-204), трём — 40/30/30.
    Сломается, если исключать всех сразу (0/0/0/0) или заполнять жадно (50/50/0/0)."""
    assert run("CASE_02") == {"R-201": 40, "R-202": 30, "R-203": 30, "R-204": 0}


def test_case_03_bad_data_quarantine_and_fix():
    """demand=0 → 0, demand<0 → карантин, rounding=0 → 1; остаток уходит на приоритет 3.
    Сломается, если падать на кривых данных или терять объём, не взятый приоритетом 1."""
    assert run("CASE_03") == {"R-301": 0, "R-302": 0, "R-303": 30, "R-304": 30}


def test_case_04_tie_break_ignores_row_order():
    """Равные заявки, остаток 2 единицы: получают R-401 и R-402 по request_id, а не первые строки CSV.
    Сломается, если тай-брейк зависит от порядка строк (лишнюю единицу получит R-405)."""
    assert run("CASE_04") == {"R-401": 20, "R-402": 20, "R-403": 19, "R-404": 19, "R-405": 19}


def test_case_05_surplus_rounds_up_once():
    """Объёма в избытке: каждая заявка округляется вверх ровно до ближайшей кратности.
    Сломается, если перегруз ограничить спросом (25/30/5) или не ограничить одной кратностью."""
    assert run("CASE_05") == {"R-501": 50, "R-502": 40, "R-503": 10}


def test_case_06_infeasible_min_lot_and_effective_min():
    """R-602: min_lot 250 > спроса 100 — карантин; R-601: min_lot 30 при кратности 25 → минимум 50.
    Сломается, если отгружать min_lot сверх допуска или считать 30 допустимым количеством."""
    assert run("CASE_06") == {"R-601": 100, "R-602": 0, "R-603": 84}


def test_case_07_hard_priority():
    """Жёсткий приоритет: приоритет 1 забирает всё, 2 и 3 получают 0.
    Сломается при переходе на пропорцию или веса (≈83/8/8)."""
    assert run("CASE_07") == {"R-701": 100, "R-702": 0, "R-703": 0}


# ---------------------------------------------------------------- собственные тесты

def test_permutation_invariance():
    """Требование 3: перестановка строк заявок не меняет план ни в одном кейсе.
    Сломается, если какой-либо шаг (тай-брейк, исключение, перегруз) опирается на порядок ввода."""
    for c in CASES.values():
        expected = allocate(c.available_qty, c.requests)
        for seed in range(20):
            shuffled = c.requests[:]
            random.Random(seed).shuffle(shuffled)
            assert allocate(c.available_qty, shuffled) == expected, (c.case_id, seed)


def test_invariants_on_random_data():
    """Требования 1 и 2 на 500 случайных кейсах с кривыми данными: сумма ≤ available, отгрузка 0 или кратна
    и ≥ минимальной партии, перегруз ≤ одной кратности, demand < 0 и priority < 1 → 0, rounding = 0 → как 1.
    Сломается при любой ошибке в округлении, остатке, возврате исключённых или валидации."""
    rng = random.Random(42)
    for _ in range(500):
        reqs = [Request(f"R{i:02d}", priority=rng.randint(0, 3), demand_qty=rng.randint(-20, 120),
                        min_lot=rng.choice([0, 0, rng.randint(1, 150)]),
                        rounding_value=rng.choice([0, 1, 5, 7, 10, 25]))
                for i in range(rng.randint(1, 8))]
        available = rng.randint(0, 400)
        plan = allocate(available, reqs)
        assert sum(plan.values()) <= available
        for r in reqs:
            q = plan[r.request_id]
            if r.priority < 1 or r.demand_qty < 0:
                assert q == 0, r
                continue
            if q == 0:
                continue
            r = replace(r, rounding_value=r.rounding_value or 1)
            assert q % r.rounding_value == 0, r
            assert q >= _effective_min(r), r
            assert q <= _round_up(r.demand_qty, r.rounding_value), r


def test_readmission_after_rounding():
    """Возврат исключённых: доля X (88) < min_lot 90, но A из-за кратности берёт только 50,
    и остатка 90 хватает вернуть X. Сломается без возврата: X=0, а 90 уйдут ниже или останутся."""
    reqs = [Request("A", 1, 59, rounding_value=10), Request("X", 1, 100, min_lot=90)]
    assert allocate(140, reqs) == {"A": 50, "X": 90}


def test_negative_available_raises():
    """available_qty < 0 — ошибка кейса, а не пустой план.
    Сломается, если молча вернуть нули: планировщик не узнает о битых данных."""
    with pytest.raises(ValueError):
        allocate(-1, [Request("A", 1, 10)])
