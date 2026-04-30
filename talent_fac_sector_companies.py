"""
Parses talent_fac_sector_summaries.json into talent_fac_sector_map.json.
Same logic as sector_companies.py.
"""
import json
import os

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SUMMARIES_FILE = os.path.join(SCRIPT_DIR, "talent_fac_sector_summaries.json")
OUTPUT_FILE    = os.path.join(SCRIPT_DIR, "talent_fac_sector_map.json")

SECTORS = [
    "AI / Foundation Models",
    "AI Applications",
    "Defense / Dual-Use",
    "Fintech",
    "Data / Dev Infra",
    "Biotech / Life Sciences",
    "Robotics / Autonomy",
    "Energy / Climate",
    "Healthcare",
    "Space",
]

SECTORS_LOWER = {s.lower(): s for s in SECTORS}


def parse_sectors(raw: str) -> list[str]:
    candidates = [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]
    matched = []
    for candidate in candidates:
        canonical = SECTORS_LOWER.get(candidate.lower())
        if canonical and canonical not in matched:
            matched.append(canonical)
        if len(matched) == 2:
            break
    return matched


def main():
    if not os.path.exists(SUMMARIES_FILE):
        print(f"Missing {SUMMARIES_FILE} — run talent_fac_sector_summaries.py first.")
        return

    with open(SUMMARIES_FILE) as f:
        summaries: dict[str, str] = json.load(f)

    sector_map: dict[str, list[str]] = {}
    unmatched = []

    for company, raw in summaries.items():
        sectors = parse_sectors(raw) if raw else []
        sector_map[company] = sectors
        if raw and not sectors:
            unmatched.append((company, raw))

    with open(OUTPUT_FILE, "w") as f:
        json.dump(sector_map, f, indent=2)

    tagged   = sum(1 for v in sector_map.values() if v)
    untagged = sum(1 for v in sector_map.values() if not v)
    sector_counts: dict[str, int] = {}
    for sectors in sector_map.values():
        for s in sectors:
            sector_counts[s] = sector_counts.get(s, 0) + 1

    print(f"Done. {tagged} companies tagged, {untagged} untagged.")
    print(f"\nSector distribution:")
    for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
        print(f"  {sector:<30} {count}")

    if unmatched:
        print(f"\nUnmatched responses ({len(unmatched)}):")
        for company, raw in unmatched:
            print(f"  {company}: {raw!r}")

    print(f"\nWritten to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
