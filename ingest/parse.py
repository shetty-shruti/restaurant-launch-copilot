"""Parse 10-K HTML into clean text split by Item 1A, Item 7 and Item 8.

Two steps:

1. html_to_text: turn the HTML into plain text where each paragraph is one line and
   each table row is one line with cells joined by " | ". Keeping a row on one line
   matters for a financial Q&A app: "Net income | 57,048 | 58,471" can be retrieved
   and read; the number on its own line, far from its label, cannot.
2. extract_sections: find where Items 1A, 7 and 8 start and end in that text.

10-Ks come in two layouts, and our two banks show both:

- Inline (BAC): the MD&A and financial statements sit directly under their
  "Item 7." and "Item 8." headings.
- Cross-referenced (JPM): "Item 7." is a single sentence saying the MD&A "appears on
  pages 46-160", and the real MD&A comes later, from the bank's annual report. For
  those we fall back to the annual report's own headings.

Every 10-K also starts with a table of contents that repeats each "Item" heading, so for
each item we take the heading occurrence that starts the longest stretch of text.

Run it from the project root to parse everything that ingest.edgar downloaded:

    python -m ingest.parse                       # all files under data/raw/
    python -m ingest.parse data/raw/JPM/2025.html

It writes one .txt per section to data/processed/{ticker}/{year}/ so you can read them.
"""

from __future__ import annotations

import argparse
import re
import warnings
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"

SECTIONS = ("Item 1A", "Item 7", "Item 8")

# Tags that start a new line of text. Everything else (span, a, b, ix:nonFraction...)
# is inline, so its text joins the words around it.
BLOCK_TAGS = ["p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"]

# "Item 7." at the start of a line. Group 1 is the item number: 1, 1A, 7, 7A, 8, 9C...
ITEM_HEADING = re.compile(r"^item\s*(\d{1,2}[a-c]?)\b", re.IGNORECASE | re.MULTILINE)

# A heading section shorter than this that mentions pages is a cross-reference stub.
CROSS_REFERENCE_MAX_CHARS = 3000

# Fallback headings for the cross-referenced layout: (start, end) of each section.
# Anchored with $ so they match the real heading line, not a table-of-contents row
# such as "Report of Independent Registered Public Accounting Firm | 162".
_INTERNAL_CONTROL = r"^management.s report on internal control over financial reporting$"
ANNUAL_REPORT_HEADINGS = {
    "Item 7": (r"^management.s discussion and analysis$", _INTERNAL_CONTROL),
    "Item 8": (_INTERNAL_CONTROL, r"^glossary of terms and acronyms$"),
}


def html_to_text(html: str) -> str:
    """Plain text with one paragraph or one table row per line."""
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    soup = BeautifulSoup(html, "lxml")

    # Drop what a reader never sees: scripts, styles, and the hidden inline-XBRL block
    # (machine-readable facts the SEC embeds in the page, which would add noise).
    for tag in soup.find_all(["script", "style", "head", "ix:header"]):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display:\s*none")):
        tag.decompose()

    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        row.replace_with(_table_row(cells) + "\n")
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_after("\n")

    lines = []
    for line in soup.get_text().splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _table_row(cells: list[str]) -> str:
    """Join a row's cells, keeping "$", "%" and ")" next to their numbers."""
    merged: list[str] = []
    for cell in (c for c in cells if c):
        if merged and merged[-1] in ("$", "("):
            merged[-1] += cell
        elif merged and cell in ("%", ")", ")%"):
            merged[-1] += cell
        else:
            merged.append(cell)
    return " | ".join(merged)


def extract_sections(html: str) -> dict[str, str]:
    """Return {"Item 1A": text, "Item 7": text, "Item 8": text}.

    A section that can't be found is left out, so check which keys came back.
    """
    text = html_to_text(html)
    headings = [(m.start(), m.group(1).upper()) for m in ITEM_HEADING.finditer(text)]

    sections: dict[str, str] = {}
    for name in SECTIONS:
        number = name.split()[1].upper()
        body = _longest_section(text, headings, number)
        if body and _is_cross_reference(body) and name in ANNUAL_REPORT_HEADINGS:
            body = _annual_report_section(text, *ANNUAL_REPORT_HEADINGS[name])
        if body:
            sections[name] = remove_page_furniture(body)
    return sections


def _longest_section(text: str, headings: list[tuple[int, str]], number: str) -> str:
    """Of all "Item {number}" headings, take the one followed by the most text.

    A section runs from its heading to the next heading for a different item. Table of
    contents entries are a line apart, so they lose to the real heading.
    """
    best = ""
    for i, (start, item) in enumerate(headings):
        if item != number:
            continue
        end = next((pos for pos, other in headings[i + 1 :] if other != number), len(text))
        if end - start > len(best):
            best = text[start:end]
    return best


def _is_cross_reference(body: str) -> bool:
    return len(body) < CROSS_REFERENCE_MAX_CHARS and re.search(r"\bpages?\s+\d", body) is not None


def _annual_report_section(text: str, start_pattern: str, end_pattern: str) -> str:
    """Find a section by the annual report's own headings (cross-referenced layout).

    Takes the start heading that comes after the "Item" headings end, so we skip the
    annual report's table of contents, then runs to the next end heading.
    """
    flags = re.IGNORECASE | re.MULTILINE
    after_items = max((m.start() for m in ITEM_HEADING.finditer(text)), default=0)
    start = re.compile(start_pattern, flags).search(text, after_items)
    if not start:
        return ""
    end = re.compile(end_pattern, flags).search(text, start.end())
    return text[start.start() : end.start() if end else len(text)]


def remove_page_furniture(body: str) -> str:
    """Drop page numbers and the running headers and footers printed on every page.

    A short line that repeats on many pages, such as "Bank of America 86" or
    "JPMorgan Chase & Co./2025 Form 10-K | 161", is page furniture, not content.
    Left in, it would show up in every chunk and blur retrieval. Page numbers
    differ from page to page, so lines are compared with the page number taken off.
    """
    lines = body.splitlines()
    keys = [_without_page_number(line) for line in lines]
    counts = Counter(keys)
    kept = [
        line
        for line, key in zip(lines, keys, strict=True)
        if key and not (_looks_like_furniture(key) and counts[key] >= 50)
    ]
    return "\n".join(kept)


def _looks_like_furniture(key: str) -> bool:
    # Table rows (with " | ") are content even when they repeat: a column header such as
    # "Year ended December 31, (in millions) | 2025 | 2024" says what the numbers mean.
    return 12 <= len(key) < 80 and "|" not in key


def _without_page_number(line: str) -> str:
    """ "Bank of America 86" -> "Bank of America"; "86 Bank of America" -> "Bank of America"."""
    return re.sub(r"^\d{1,3}(?: \| | )|(?: \| | )\d{1,3}$|^\d{1,3}$", "", line)


def parse_file(html_path: Path) -> dict[str, str]:
    """Parse one downloaded filing and write its sections to data/processed/."""
    sections = extract_sections(html_path.read_text(encoding="utf-8", errors="replace"))
    out_dir = PROCESSED_DIR / html_path.parent.name / html_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, body in sections.items():
        file_name = name.lower().replace(" ", "_") + ".txt"  # item_1a.txt, item_7.txt...
        (out_dir / file_name).write_text(body, encoding="utf-8")
    return sections


def main() -> None:
    parser = argparse.ArgumentParser(description="Split downloaded 10-Ks into sections")
    parser.add_argument("files", nargs="*", type=Path, help="defaults to data/raw/*/*.html")
    args = parser.parse_args()

    for html_path in args.files or sorted(RAW_DIR.glob("*/*.html")):
        sections = parse_file(html_path)
        sizes = ", ".join(f"{name}: {len(body) // 1000}k chars" for name, body in sections.items())
        missing = [name for name in SECTIONS if name not in sections]
        print(f"{html_path.parent.name} {html_path.stem}: {sizes}")
        if missing:
            print(f"    MISSING: {', '.join(missing)}")


if __name__ == "__main__":
    main()
