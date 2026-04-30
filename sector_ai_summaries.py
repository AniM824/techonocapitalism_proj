"""
Queries Google (via SerpAPI) to classify each company into 1-2 sectors.
Results written to sector_summaries.json.
"""
import json
import os
import subprocess
import time
import serpapi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "sector_summaries.json")
SERPAPI_KEYS = [
    "0fb8be13914337aa60969804e50b6cbd6fdd520afc0feef7ec6615e14df57ce2"
]

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

QUERIES = [
    ["--top", "50"],
    ["--top", "75", "--max-round", "Series F"],
    ["--top", "75", "--max-round", "Series C"],
    ["--top", "75", "--max-round", "Series B"],
    ["--top", "75", "--max-round", "Series A"],
]


def parse_companies(output: str) -> list[str]:
    companies = []
    for line in output.splitlines():
        if not line or line.startswith("Rank") or line.startswith("-"):
            continue
        if not line[:5].strip().isdigit():
            continue
        company = line[6:46].strip()
        if company:
            companies.append(company)
    return companies


def get_companies(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["python3", "top_funded_companies.py"] + args,
        capture_output=True, text=True, cwd=SCRIPT_DIR,
    )
    return parse_companies(result.stdout)


def collect_unique_companies() -> list[str]:
    seen, ordered = set(), []
    for args in QUERIES:
        for company in get_companies(args):
            if company not in seen:
                seen.add(company)
                ordered.append(company)
    return ordered


def extract_text_from_blocks(text_blocks: list) -> str:
    parts = []
    for block in text_blocks:
        block_type = block.get("type")
        if block_type in ("paragraph", "heading"):
            parts.append(block.get("snippet", ""))
        elif block_type == "list":
            for item in block.get("list", []):
                title   = item.get("title", "")
                snippet = item.get("snippet", "")
                parts.append(f"{title} {snippet}".strip())
                for nested in item.get("list", []):
                    parts.append(nested.get("snippet", ""))
        elif block_type == "expandable":
            parts.append(extract_text_from_blocks(block.get("text_blocks", [])))
    return "\n".join(filter(None, parts))


def serpapi_search(params: dict) -> dict:
    last_err = None
    for key in SERPAPI_KEYS:
        try:
            results = serpapi.Client(api_key=key).search(params)
            if results.get("error"):
                raise RuntimeError(results["error"])
            return results
        except Exception as e:
            print(f"\n      key ...{key[-6:]} failed ({e}), trying next...", end=" ", flush=True)
            last_err = e
    raise RuntimeError(f"All API keys exhausted: {last_err}")


def query_sector(company: str) -> str:
    sector_list = ", ".join(SECTORS)
    query = (
        f"what 1 or 2 sectors would you label {company} as being from this list: "
        f"{sector_list}. Answer as a comma separated list and nothing else"
    )

    print(f"      searching...", end=" ", flush=True)
    search_results = serpapi_search({
        "engine": "google",
        "q": query,
        "gl": "us",
        "hl": "en",
    })

    ai_field = search_results.get("ai_overview", {})

    if ai_field.get("text_blocks"):
        text = extract_text_from_blocks(ai_field["text_blocks"])
        print(f"got AI overview (direct)")
        return text

    page_token = ai_field.get("page_token")
    if not page_token:
        print(f"no AI overview")
        return ""

    print(f"fetching AI overview...", end=" ", flush=True)
    ai_results = serpapi_search({
        "engine": "google_ai_overview",
        "page_token": page_token,
    })
    text_blocks = (ai_results.get("ai_overview") or {}).get("text_blocks", [])
    text = extract_text_from_blocks(text_blocks)
    print(f"got ({len(text)} chars)")
    return text


def main():
    companies = collect_unique_companies()
    print(f"Found {len(companies)} unique companies to classify.")

    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            content = f.read().strip()
        summaries: dict[str, str] = json.loads(content) if content else {}
    else:
        summaries = {}

    for i, company in enumerate(companies, 1):
        if company in summaries:
            print(f"[{i}/{len(companies)}] {company} — skipped (cached)")
            continue

        print(f"[{i}/{len(companies)}] {company} ...", end=" ", flush=True)
        try:
            summaries[company] = query_sector(company)
        except Exception as e:
            print(f"ERROR: {e}")
            summaries[company] = ""

        with open(OUTPUT_FILE, "w") as f:
            json.dump(summaries, f, indent=2)

        time.sleep(0.3)

    print(f"\nDone. Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
