"""Download a small, license-clean corpus of real documents for manual testing.

Public-domain financial PDFs (acronym-dense, deeply sectioned — they exercise the
BM25 keyword branch and tag-scoped search the way scientific prose never would)
plus one arXiv paper as an out-of-domain control. All sources are public and need
no auth. Files land in corpus/; existing files are skipped.

Usage: uv run python scripts/fetch_corpus.py
Then ingest with the tags printed at the end (see docs/manual-walkthrough.md).
"""

import pathlib
import sys

import httpx

# IRS/BIS/NIST reject an empty User-Agent; any real-looking string is fine.
_UA = "Mozilla/5.0 (DocumentIntelligenceServer corpus fetcher)"
OUT_DIR = pathlib.Path("corpus")

# (filename, url, suggested tags) — edit freely. Sources chosen for being
# programmatically fetchable (EUR-Lex, SEC EDGAR, etc. bot-block or serve HTML).
CORPUS: list[tuple[str, str, str]] = [
    ("basel3.pdf", "https://www.bis.org/bcbs/publ/d424.pdf", "capital"),
    ("irs-employer-tax-guide.pdf", "https://www.irs.gov/pub/irs-pdf/p15.pdf", "payroll"),
    ("irs-investment-income.pdf", "https://www.irs.gov/pub/irs-pdf/p550.pdf", "investments"),
    ("nist-cybersecurity-framework.pdf", "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf", "security"),
    ("attention-is-all-you-need.pdf", "https://arxiv.org/pdf/1706.03762", "research"),
]


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    downloaded: list[tuple[str, str]] = []
    with httpx.Client(headers={"User-Agent": _UA}, follow_redirects=True, timeout=120) as c:
        for name, url, tags in CORPUS:
            dest = OUT_DIR / name
            if dest.exists():
                print(f"skip   {name} (already present)")
                downloaded.append((name, tags))
                continue
            print(f"get    {name} <- {url}")
            try:
                r = c.get(url)
                r.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"  FAILED: {exc}", file=sys.stderr)
                continue
            dest.write_bytes(r.content)
            print(f"  saved {len(r.content):,} bytes")
            downloaded.append((name, tags))

    print("\nIngest cheat-sheet (filename -> tags):")
    for name, tags in downloaded:
        print(f"  {name:32} tags={tags}")
    print(f"\n{len(downloaded)} file(s) in {OUT_DIR}/. See docs/manual-walkthrough.md.")


if __name__ == "__main__":
    main()
