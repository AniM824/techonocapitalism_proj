import argparse
import os
from dataclasses import dataclass, field

ROUND_ORDER = [
    "Pre Seed Round",
    "Seed Round",
    "Series A",
    "Series B",
    "Series C",
    "Series D",
    "Series E",
    "Series F",
    "Series G",
    "Series H",
    "Series I",
    "Series J",
    # Late-stage / non-standard — treated as beyond any series cap
    "Venture Round",
    "Debt Financing",
    "Secondary Market",
    "Private Equity Round",
    "Post-IPO Equity",
]

ROUND_RANK = {r: i for i, r in enumerate(ROUND_ORDER)}


@dataclass
class Round:
    round_type: str
    amount: float
    vcs: list = field(default_factory=list)


class Company:
    def __init__(self, name: str):
        self.name = name
        # key: (round_type, amount) -> Round
        self._rounds: dict[tuple, Round] = {}

    def add_round(self, round_type: str, amount: float, vc: str):
        key = (round_type, amount)
        if key not in self._rounds:
            self._rounds[key] = Round(round_type=round_type, amount=amount)
        if vc not in self._rounds[key].vcs:
            self._rounds[key].vcs.append(vc)

    @property
    def rounds(self) -> list[Round]:
        return list(self._rounds.values())

    @property
    def available_rounds(self) -> list[str]:
        seen = set()
        result = []
        for r in self._rounds.values():
            if r.round_type not in seen:
                seen.add(r.round_type)
                result.append(r.round_type)
        return result

    @property
    def total_funding(self) -> float:
        return sum(r.amount for r in self._rounds.values())

    def max_round_rank(self) -> int:
        """Highest rank among all rounds this company has raised.
        Unknown round types are treated as beyond all known stages (float('inf') cast to int max)."""
        has_unknown = any(r.round_type not in ROUND_RANK for r in self._rounds.values())
        if has_unknown:
            return len(ROUND_ORDER)  # beyond any valid cap
        ranks = [ROUND_RANK[r.round_type] for r in self._rounds.values()]
        return max(ranks) if ranks else len(ROUND_ORDER)

    def __repr__(self):
        return f"Company({self.name!r}, total=${self.total_funding:,.0f})"


def parse_amount(raw: str) -> float:
    raw = raw.strip().lstrip("$").replace(",", "")
    multipliers = {"B": 1e9, "M": 1e6, "K": 1e3}
    for suffix, mult in multipliers.items():
        if raw.upper().endswith(suffix):
            return float(raw[:-1]) * mult
    return float(raw)


def parse_round_type(line: str) -> str:
    # Line format: "Series A - CompanyName"
    # Extract everything before the last " - CompanyName" occurrence
    parts = line.rsplit(" - ", 1)
    return parts[0].strip()


def parse_file(filepath: str) -> list[dict]:
    vc_name = os.path.splitext(os.path.basename(filepath))[0]
    entries = []

    with open(filepath, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f.readlines()]

    i = 0
    while i + 6 < len(lines):
        date = lines[i].strip()
        # lines[i+1]: "<Company> Logo" — skip
        company = lines[i + 2].strip()
        # lines[i+3]: flag — skip
        # lines[i+4]: "<Round> - <Company> Logo" — skip
        round_type = parse_round_type(lines[i + 5])
        amount_raw = lines[i + 6].strip()

        if amount_raw.startswith("$"):
            try:
                amount = parse_amount(amount_raw)
                entries.append({
                    "vc": vc_name,
                    "company": company,
                    "round_type": round_type,
                    "amount": amount,
                    "date": date,
                })
            except ValueError:
                pass
            i += 7
        else:
            i += 1

    return entries


def main():
    parser = argparse.ArgumentParser(description="Top funded companies from VC portfolio data.")
    parser.add_argument(
        "--max-round",
        metavar="ROUND",
        help=f"Only show companies whose highest round is at or below this stage. "
             f"Valid values: {', '.join(repr(r) for r in ROUND_ORDER)}",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        metavar="N",
        help="Number of companies to display (default: 30).",
    )
    args = parser.parse_args()

    cap_rank: int | None = None
    if args.max_round:
        if args.max_round not in ROUND_RANK:
            parser.error(f"Unknown round '{args.max_round}'. Valid values: {', '.join(ROUND_ORDER)}")
        cap_rank = ROUND_RANK[args.max_round]

    data_dir = os.path.dirname(os.path.abspath(__file__))
    txt_files = [
        os.path.join(data_dir, f)
        for f in os.listdir(data_dir)
        if f.endswith(".txt")
    ]

    companies: dict[str, Company] = {}

    for filepath in txt_files:
        for entry in parse_file(filepath):
            name = entry["company"]
            if name not in companies:
                companies[name] = Company(name)
            companies[name].add_round(entry["round_type"], entry["amount"], entry["vc"])

    candidates = companies.values()
    if cap_rank is not None:
        candidates = [c for c in candidates if c.max_round_rank() <= cap_rank]

    sorted_companies = sorted(candidates, key=lambda c: c.total_funding, reverse=True)

    cap_label = f" (max round: {args.max_round})" if args.max_round else ""
    print(f"{'Rank':<5} {'Company':<40} {'Total Funding':>16}  {'Rounds':<35}  VCs per Round{cap_label}")
    print("-" * 130)
    for rank, co in enumerate(sorted_companies[:args.top], 1):
        rounds_str = ", ".join(co.available_rounds)
        vc_detail = " | ".join(
            f"{r.round_type}: [{', '.join(r.vcs)}]" for r in co.rounds
        )
        funding_str = f"${co.total_funding:,.0f}"
        print(f"{rank:<5} {co.name:<40} {funding_str:>16}  {rounds_str:<35}  {vc_detail}")


if __name__ == "__main__":
    main()
