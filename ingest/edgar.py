"""SEC EDGAR client. Sends the required User-Agent and stays under 10 requests/second.

How the pieces fit together:

1. Ticker -> CIK. The SEC publishes every ticker and its CIK (Central Index Key, the
   SEC's id for a company) in one JSON file: https://www.sec.gov/files/company_tickers.json
2. CIK -> list of filings. https://data.sec.gov/submissions/CIK##########.json (CIK padded
   to 10 digits) lists a company's filings as parallel arrays: form[i], accessionNumber[i],
   filingDate[i], reportDate[i] and primaryDocument[i] all describe filing i.
3. Filing -> document. The 10-K itself is the "primary document" inside the filing folder:
   https://www.sec.gov/Archives/edgar/data/{cik}/{accession without dashes}/{primaryDocument}

Run it from the project root (so .env is found):

    python -m ingest.edgar            # tickers and years from .env (TICKERS, FILING_YEARS)
    python -m ingest.edgar JPM --years 1
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# The SEC allows 10 requests/second per client. Stay well under it.
MIN_SECONDS_BETWEEN_REQUESTS = 0.15


class EdgarClient:
    """A small HTTP client that adds the SEC User-Agent, throttles and retries."""

    def __init__(self, user_agent: str | None = None) -> None:
        user_agent = user_agent or get_settings().sec_user_agent
        if not user_agent or "example.com" in user_agent:
            raise RuntimeError('Set SEC_USER_AGENT="Your Name your.email@domain" in .env')
        self._http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=30.0,
            follow_redirects=True,
        )
        self._last_request = 0.0

    def get(self, url: str) -> httpx.Response:
        for attempt in range(4):
            wait = MIN_SECONDS_BETWEEN_REQUESTS - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            response = self._http.get(url)
            # 429 = too many requests, 5xx = SEC having a bad moment. Back off and retry.
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            return response
        response.raise_for_status()
        return response

    def get_json(self, url: str) -> Any:
        return self.get(url).json()


def lookup_cik(client: EdgarClient, ticker: str) -> int:
    """Find a company's CIK from its ticker. The ticker file is cached in data/raw/."""
    cache = RAW_DIR / "company_tickers.json"
    if cache.exists():
        companies = json.loads(cache.read_text(encoding="utf-8"))
    else:
        companies = client.get_json(TICKERS_URL)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(companies), encoding="utf-8")

    # Shape: {"0": {"cik_str": 19617, "ticker": "JPM", "title": "JPMORGAN CHASE & CO"}, ...}
    for company in companies.values():
        if company["ticker"].upper() == ticker.upper():
            return int(company["cik_str"])
    raise ValueError(f"Ticker {ticker!r} not found in {TICKERS_URL}")


def _rows(columns: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Turn EDGAR's parallel arrays into one dict per filing."""
    keys = list(columns)
    return [dict(zip(keys, values, strict=True)) for values in zip(*columns.values(), strict=True)]


def list_10k_filings(client: EdgarClient, cik: int, years: int = 3) -> list[dict]:
    """Return the latest `years` original 10-K filings for a company, newest first."""
    submissions = client.get_json(SUBMISSIONS_URL.format(cik=cik))
    pages = [submissions["filings"]["recent"]]
    # "recent" holds only the last ~1000 filings. Big banks file thousands of prospectuses
    # (form 424B2) a year, so older 10-Ks can sit in extra pages listed under "files".
    older_pages = [p["name"] for p in submissions["filings"].get("files", [])]

    filings: list[dict] = []
    while True:
        for row in _rows(pages.pop()):
            if row["form"] != "10-K":  # skips amendments (10-K/A) on purpose
                continue
            accession = row["accessionNumber"]
            report_date = row.get("reportDate") or ""
            filings.append(
                {
                    "cik": cik,
                    "accession_number": accession,
                    "filing_date": row["filingDate"],
                    "report_date": report_date,
                    # Banks close their year on Dec 31, so the period end gives the fiscal year.
                    # If it is missing, the 10-K covers the year before it was filed.
                    "fiscal_year": int(report_date[:4] or int(row["filingDate"][:4]) - 1),
                    "primary_document": row["primaryDocument"],
                    "source_url": ARCHIVE_URL.format(
                        cik=cik,
                        accession=accession.replace("-", ""),
                        document=row["primaryDocument"],
                    ),
                }
            )
        if len(filings) >= years or not older_pages:
            break
        pages.append(client.get_json(SUBMISSIONS_PAGE_URL.format(name=older_pages.pop(0))))

    filings.sort(key=lambda f: f["filing_date"], reverse=True)
    return filings[:years]


def download_filing(client: EdgarClient, url: str, dest_path: Path) -> bool:
    """Save raw HTML to dest_path. Returns False if it was already downloaded."""
    if dest_path.exists() and dest_path.stat().st_size > 0:
        return False
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(client.get(url).content)
    return True


def download_10ks(client: EdgarClient, ticker: str, years: int = 3) -> list[dict]:
    """Download a company's last `years` 10-Ks to data/raw/{ticker}/{year}.html.

    Next to each .html it writes {year}.json with the filing's metadata, which the
    pipeline later inserts into the `filings` table (and uses for citation links).
    """
    ticker = ticker.upper()
    cik = lookup_cik(client, ticker)
    filings = list_10k_filings(client, cik, years)
    for filing in filings:
        filing["ticker"] = ticker
        html_path = RAW_DIR / ticker / f"{filing['fiscal_year']}.html"
        fresh = download_filing(client, filing["source_url"], html_path)
        html_path.with_suffix(".json").write_text(json.dumps(filing, indent=2), encoding="utf-8")
        size_kb = html_path.stat().st_size // 1024
        status = "downloaded" if fresh else "already had"
        print(f"{ticker} FY{filing['fiscal_year']}: {status} {html_path.name} ({size_kb} KB)")
        print(f"    {filing['source_url']}")
    return filings


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Download 10-K filings from SEC EDGAR")
    parser.add_argument("tickers", nargs="*", help="defaults to TICKERS in .env")
    parser.add_argument("--years", type=int, default=settings.filing_years)
    args = parser.parse_args()

    client = EdgarClient()
    for ticker in args.tickers or settings.ticker_list:
        download_10ks(client, ticker, args.years)


if __name__ == "__main__":
    main()
