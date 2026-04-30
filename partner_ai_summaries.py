"""
Queries Google (via SerpAPI) for partner/integration info on the top companies across
several funding-stage filters, deduplicates, and writes results to partner_summaries.json.
"""
import json
import os
import subprocess
import time
import serpapi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "partner_summaries.json")
SERPAPI_KEYS = [
    "bb292251dabf1eea7b58fdb5d0d20859eeb437e0424407cda439665affa81c3a",
    "6f802f50fe8fcffbfbb7e46a8a5a114c01e757423dd975c0f0c1e3468de2e255",
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
        rank_token = line[:5].strip()
        if not rank_token.isdigit():
            continue
        company = line[6:46].strip()
        if company:
            companies.append(company)
    return companies


def get_companies(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["python3", "top_funded_companies.py"] + args,
        capture_output=True,
        text=True,
        cwd=SCRIPT_DIR,
    )
    return parse_companies(result.stdout)


def collect_unique_companies() -> list[str]:
    seen = set()
    ordered = []
    for args in QUERIES:
        for company in get_companies(args):
            if company not in seen:
                seen.add(company)
                ordered.append(company)
    return ordered


def serpapi_search(params: dict) -> dict:
    """Try each API key in order, falling back on error."""
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


def query_serpapi(company: str) -> str:
    query = f"top companies and startups that {company} has partnered with or integrated with, please list comma separated nothing else"

    # Step 1: Regular search to get page_token
    search_results = serpapi_search({
        "engine": "google",
        "q": query,
        "gl": "us",
        "hl": "en",
    })

    ai_overview_field = search_results.get("ai_overview", {})

    # Check if text_blocks are already embedded directly (no extra request needed)
    if ai_overview_field.get("text_blocks"):
        return extract_text_from_blocks(ai_overview_field["text_blocks"])

    # Otherwise use page_token for second request
    page_token = ai_overview_field.get("page_token")
    if not page_token:
        print(f"      -> no AI overview available")
        return ""

    # Step 2: Fetch full AI overview — must happen within 4 minutes
    ai_results = serpapi_search({
        "engine": "google_ai_overview",
        "page_token": page_token,
    })

    text_blocks = (ai_results.get("ai_overview") or {}).get("text_blocks", [])
    return extract_text_from_blocks(text_blocks)


def extract_text_from_blocks(text_blocks: list) -> str:
    """
    Flatten SerpAPI's nested text_blocks structure into a single string.
    Handles paragraphs, headings, lists, and expandable sections.
    """
    parts = []

    for block in text_blocks:
        block_type = block.get("type")

        if block_type in ("paragraph", "heading"):
            parts.append(block.get("snippet", ""))

        elif block_type == "list":
            for item in block.get("list", []):
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                parts.append(f"{title} {snippet}".strip())
                # Handle nested lists
                for nested in item.get("list", []):
                    parts.append(nested.get("snippet", ""))

        elif block_type == "expandable":
            # Recurse into expandable sections
            parts.append(extract_text_from_blocks(block.get("text_blocks", [])))

    return "\n".join(filter(None, parts))

def main():
    companies = collect_unique_companies()
    print(f"Found {len(companies)} unique companies to query.")

    # Load existing results so we can resume if interrupted
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
            summaries[company] = query_serpapi(company)
            print("done")
        except Exception as e:
            print(f"ERROR: {e}")
            summaries[company] = ""

        # Write after every company so progress is never lost
        with open(OUTPUT_FILE, "w") as f:
            json.dump(summaries, f, indent=2)

        time.sleep(0.3)

    print(f"\nDone. Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
