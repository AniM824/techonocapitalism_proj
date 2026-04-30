"""
Queries Google (via SerpAPI) for prior employer companies of each startup's founders,
across the same funding-stage filters as partner_ai_summaries.py.
Results written to founder_summaries.json.
"""
import json
import os
import subprocess
import time
import serpapi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "founder_summaries.json")
SERPAPI_KEYS = [
    # "67ebb83a2972682621300c54f2d60cd1aff3b17d7ebae53edc9d66eac6164e1f",
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


def extract_text_from_blocks(text_blocks: list) -> str:
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
                for nested in item.get("list", []):
                    parts.append(nested.get("snippet", ""))
        elif block_type == "expandable":
            parts.append(extract_text_from_blocks(block.get("text_blocks", [])))
    return "\n".join(filter(None, parts))


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
    query = (
        f"what companies did the startup {company} founders work at prior? "
        "answer comma separated only, nothing else"
    )

    print(f"      searching Google...", end=" ", flush=True)
    search_results = serpapi_search({
        "engine": "google",
        "q": query,
        "gl": "us",
        "hl": "en",
    })

    ai_overview_field = search_results.get("ai_overview", {})

    # AI overview text already embedded directly
    if ai_overview_field.get("text_blocks"):
        text = extract_text_from_blocks(ai_overview_field["text_blocks"])
        print(f"got AI overview (direct)")
        return text

    page_token = ai_overview_field.get("page_token")
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
    print(f"got AI overview ({len(text)} chars)")
    return text


def main():
    companies = collect_unique_companies()
    print(f"Found {len(companies)} unique companies to query.")

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
        except Exception as e:
            print(f"ERROR: {e}")
            summaries[company] = ""

        with open(OUTPUT_FILE, "w") as f:
            json.dump(summaries, f, indent=2)

        time.sleep(0.3)

    print(f"\nDone. Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
