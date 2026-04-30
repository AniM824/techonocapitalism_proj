"""
Reads partner_summaries.json and builds a mapping of company -> validated partner list.
Partners are validated against the master company set (all companies across all VC files).
Matching is fuzzy: strips parentheticals, then compares first min(a, b) words case-insensitively.
"""
import json
import os
import re
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SUMMARIES_FILE = os.path.join(SCRIPT_DIR, "partner_summaries.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "partner_map.json")
TALENT_FAC_FILE = os.path.join(SCRIPT_DIR, "talent_fac.txt")


def get_talent_fac_companies() -> set[str]:
    if not os.path.exists(TALENT_FAC_FILE):
        return set()
    with open(TALENT_FAC_FILE) as f:
        return {line.strip() for line in f if line.strip()}


def get_all_companies() -> set[str]:
    result = subprocess.run(
        ["python3", "top_funded_companies.py", "--top", "9999"],
        capture_output=True,
        text=True,
        cwd=SCRIPT_DIR,
    )
    companies = set()
    for line in result.stdout.splitlines():
        if not line or line.startswith("Rank") or line.startswith("-"):
            continue
        rank_token = line[:5].strip()
        if not rank_token.isdigit():
            continue
        company = line[6:46].strip()
        if company:
            companies.add(company)
    return companies


def strip_parens(name: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", name).strip()


def normalize_words(name: str) -> list[str]:
    return strip_parens(name).lower().split()


def fuzzy_match(candidate: str, master_companies: set[str]) -> str | None:
    """Return the master company name that fuzzy-matches candidate, or None."""
    cand_words = normalize_words(candidate)
    if not cand_words:
        return None
    for master in master_companies:
        master_words = normalize_words(master)
        if not master_words:
            continue
        n = min(len(cand_words), len(master_words))
        if cand_words[:n] == master_words[:n]:
            return master
    return None


def parse_partners(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def main():
    if not os.path.exists(SUMMARIES_FILE):
        print(f"Missing {SUMMARIES_FILE} — run partner_ai_summaries.py first.")
        return

    with open(SUMMARIES_FILE) as f:
        summaries: dict[str, str] = json.load(f)

    master_companies = get_all_companies() | get_talent_fac_companies()
    print(f"Master company set: {len(master_companies)} companies")

    partner_map: dict[str, list[str]] = {}

    for company, raw_summary in summaries.items():
        if not raw_summary:
            partner_map[company] = []
            continue

        candidates = parse_partners(raw_summary)
        validated = []
        for candidate in candidates:
            match = fuzzy_match(candidate, master_companies)
            if match and match != company:
                validated.append(match)

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for v in validated:
            if v not in seen:
                seen.add(v)
                deduped.append(v)

        partner_map[company] = deduped

    with open(OUTPUT_FILE, "w") as f:
        json.dump(partner_map, f, indent=2)

    total_links = sum(len(v) for v in partner_map.values())
    print(f"Done. {total_links} validated partner links across {len(partner_map)} companies.")
    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
