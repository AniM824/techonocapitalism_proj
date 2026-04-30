"""
Same sector classification methodology as sector_ai_summaries.py,
but for companies listed in unlabelled_companies.txt.
Results written to unlabelled_sector_summaries.json.
Run unlabelled_sector_companies.py afterward to produce unlabelled_sector_map.json.
"""
import json
import os
import time
import serpapi

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE   = os.path.join(SCRIPT_DIR, "unlabelled_companies.txt")
OUTPUT_FILE  = os.path.join(SCRIPT_DIR, "unlabelled_sector_summaries.json")
SERPAPI_KEYS = [
    "123d79baacd8540765ffad91ffefd6e0ff1dec1547c9e2cdbe96d29935c30af3",
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


def load_companies() -> list[str]:
    with open(INPUT_FILE) as f:
        return [line.strip() for line in f if line.strip()]


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
    companies = load_companies()
    print(f"Found {len(companies)} companies in unlabelled_companies.txt.")

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
