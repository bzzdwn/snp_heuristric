import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from allocator import Request, allocate


@dataclass
class Case:
    case_id: str
    available_qty: int = 0
    header: str = ""
    requests: list[Request] | None = None
    error: str | None = None


def load_cases(data_dir: Path) -> list[Case]:
    cases: dict[str, Case] = {}
    with open(data_dir / "supply.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = row["case_id"]
            if cid in cases:
                cases[cid].error = "несколько строк supply на один case_id"
                continue
            case = cases[cid] = Case(cid, requests=[])
            case.header = f"{row['period']} {row['item']} {row['source_location']}"
            try:
                case.available_qty = int(row["available_qty"])
            except ValueError:
                case.error = f"available_qty не целое: {row['available_qty']!r}"

    with open(data_dir / "requests.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = row["case_id"]
            if cid not in cases:
                cases[cid] = Case(cid, requests=[], header="нет строки supply, доступно 0")
            try:
                cases[cid].requests.append(Request(
                    request_id=row["request_id"], dest_location=row["dest_location"],
                    priority=int(row["priority"]), demand_qty=int(row["demand_qty"]),
                    min_lot=int(row["min_lot"]), rounding_value=int(row["rounding_value"])))
            except ValueError:
                cases[cid].error = f"не парсится строка заявки {row['request_id']}"
    return [cases[cid] for cid in sorted(cases)]


def print_case(case: Case) -> None:
    print(f"\n=== {case.case_id} | {case.header} | доступно {case.available_qty} ===")
    if case.error:
        print(f"  ОШИБКА КЕЙСА: {case.error} — кейс пропущен")
        return
    try:
        plan = allocate(case.available_qty, case.requests)
    except ValueError as e:
        print(f"  ОШИБКА КЕЙСА: {e} — кейс пропущен")
        return
    print(f"  {'request':<8}{'dest':<7}{'prio':>5}{'demand':>8}{'min_lot':>9}{'round':>7}{'shipped':>9}")
    for r in sorted(case.requests, key=lambda r: r.request_id):
        q = plan[r.request_id]
        over = f" (+{q - r.demand_qty})" if q > r.demand_qty > 0 else ""
        print(f"  {r.request_id:<8}{r.dest_location:<7}{r.priority:>5}{r.demand_qty:>8}"
              f"{r.min_lot:>9}{r.rounding_value:>7}{q:>9}{over}")
    shipped = sum(plan.values())
    print(f"  Распределено {shipped}, нераспределено {case.available_qty - shipped}")


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
    for case in load_cases(data_dir):
        print_case(case)


if __name__ == "__main__":
    main()
