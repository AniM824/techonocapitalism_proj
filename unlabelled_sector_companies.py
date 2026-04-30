"""
Parses unlabelled_companies.txt (format: "Company — Sector1; Sector2")
into unlabelled_sector_map.json.
"""
import json
import os

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE  = os.path.join(SCRIPT_DIR, "unlabelled_companies.txt")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "unlabelled_sector_map.json")

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


def main():
    sector_map: dict[str, list[str]] = {}
    unmatched = []

    with open(INPUT_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or "—" not in line:
                continue
            company, _, raw_sectors = line.partition("—")
            company = company.strip()
            matched = []
            for part in raw_sectors.split(";"):
                canonical = SECTORS_LOWER.get(part.strip().lower())
                if canonical and canonical not in matched:
                    matched.append(canonical)
            sector_map[company] = matched
            if raw_sectors.strip() and not matched:
                unmatched.append((company, raw_sectors.strip()))

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
        print(f"\nUnmatched ({len(unmatched)}):")
        for company, raw in unmatched:
            print(f"  {company}: {raw!r}")

    print(f"\nWritten to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
