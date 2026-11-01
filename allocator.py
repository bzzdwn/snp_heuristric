from collections import Counter
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Iterable

@dataclass(frozen=True)
class Request:
    request_id: str
    priority: int
    demand_qty: int
    min_lot: int = 0
    rounding_value: int = 1
    dest_location: str = ""


def _round_up(qty: int, step: int) -> int:
    return -(-qty // step) * step


def _effective_min(r: Request) -> int:
    """Наименьшее допустимое ненулевое количество: кратное rounding и не меньше min_lot."""
    return _round_up(max(r.min_lot, 1), r.rounding_value)


def _tail(r: Request) -> tuple:
    """Общий хвост ключа для ничьих: больший спрос, затем request_id."""
    return (-r.demand_qty, r.request_id)


def _validate(requests: list[Request]) -> list[Request]:
    """Возвращает заявки, пригодные к распределению; остальные получат 0 с причиной."""
    counts = Counter(r.request_id for r in requests)
    valid = []
    for r in sorted(requests, key=lambda r: r.request_id):
        rid = r.request_id
        if counts[rid] > 1:
            print(f"  {rid}: карантин — request_id повторяется в кейсе")
        elif r.priority < 1:
            print(f"  {rid}: карантин — некорректный priority={r.priority}")
        elif r.demand_qty < 0:
            print(f"  {rid}: карантин — отрицательный спрос {r.demand_qty}")
        elif r.min_lot < 0 or r.rounding_value < 0:
            print(f"  {rid}: карантин — отрицательные min_lot/rounding_value")
        elif r.demand_qty == 0:
            print(f"  {rid}: 0 — нет спроса")
        else:
            if r.rounding_value == 0:
                print(f"  {rid}: rounding_value=0 трактуем как 1 (нет кратности)")
                r = replace(r, rounding_value=1)
            if _effective_min(r) > _round_up(r.demand_qty, r.rounding_value):
                print(f"  {rid}: карантин — минимальная партия {_effective_min(r)} "
                      f"больше спроса {r.demand_qty} более чем на одну кратность")
            else:
                valid.append(r)
    return valid


def _share_level(budget: int, level: list[Request]) -> dict[str, int]:
    """Распределяет budget между заявками одного уровня приоритета (основной проход)."""
    # Потолок основного прохода: спрос с округлением вниз, но не меньше минимальной
    # партии (если она больше спроса в пределах одной кратности).
    target = {r.request_id: max(r.demand_qty // r.rounding_value * r.rounding_value,
                                _effective_min(r)) for r in level}
    if sum(target.values()) <= budget:
        return target

    active, excluded = sorted(level, key=_tail), []
    share: dict[str, Fraction] = {}
    while active:
        total = sum(r.demand_qty for r in active)
        share = {r.request_id: Fraction(budget * r.demand_qty, total) for r in active}
        worst = None
        for r in active:  # '<=' — при равенстве исключается последняя по хвосту ключа
            ratio = share[r.request_id] / _effective_min(r)
            if ratio < 1 and (worst is None or ratio <= worst[0]):
                worst = (ratio, r)
        if worst is None:
            break
        active.remove(worst[1])
        excluded.append(worst[1])

    alloc = {r.request_id: 0 for r in level}
    for r in active:
        step = r.rounding_value
        alloc[r.request_id] = min(target[r.request_id], int(share[r.request_id] // step) * step)
    left = budget - sum(alloc.values())

    # Наибольший остаток в единицах кратности; sorted стабилен, ничьи — по хвосту ключа.
    order = sorted(active, key=lambda r: -(share[r.request_id] - alloc[r.request_id]) / r.rounding_value)
    progress = True
    while progress:
        progress = False
        for r in order:
            step = r.rounding_value
            if step <= left and alloc[r.request_id] + step <= target[r.request_id]:
                alloc[r.request_id] += step
                left -= step
                progress = True

    # Возврат исключённых, если после округлений остатка хватает на минимальную партию.
    for r in sorted(excluded, key=_tail):
        amount = min(target[r.request_id], left // r.rounding_value * r.rounding_value)
        if amount >= _effective_min(r):
            alloc[r.request_id] = amount
            left -= amount
        elif budget == 0:
            print(f"  {r.request_id}: 0 — весь объём забрали более высокие приоритеты")
        else:
            print(f"  {r.request_id}: 0 — доступного объёма уровня не хватает "
                  f"на минимальную партию {_effective_min(r)}")
    return alloc


def allocate(available_qty: int, requests: Iterable[Request]) -> dict[str, int]:
    """Возвращает отгрузку по каждой заявке; сумма не превышает available_qty."""
    if available_qty < 0:
        raise ValueError(f"available_qty < 0: {available_qty}")
    requests = list(requests)
    result = {r.request_id: 0 for r in sorted(requests, key=lambda r: r.request_id)}
    valid = _validate(requests)

    left = available_qty
    for priority in sorted({r.priority for r in valid}):
        alloc = _share_level(left, [r for r in valid if r.priority == priority])
        result.update(alloc)
        left -= sum(alloc.values())

    # Перегруз: только остаток после покрытия реального спроса всех уровней,
    # не больше одной кратности сверх спроса.
    for r in sorted(valid, key=lambda r: (r.priority, *_tail(r))):
        need = _round_up(r.demand_qty, r.rounding_value) - result[r.request_id]
        if 0 < need <= left:
            result[r.request_id] += need
            left -= need
            print(f"  {r.request_id}: перегруз до кратности {r.rounding_value} — "
                  f"{result[r.request_id]} при спросе {r.demand_qty}")
    return result
