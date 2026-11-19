"""Agent tools (week 4)."""


def search_rules(
    query: str, jurisdiction: str | None = None, section: str | None = None
) -> list[dict]:
    """Search rule documents (federal + city). Wraps the best retriever from weeks 2 to 3."""
    raise NotImplementedError("Week 4")


def get_inspection_stats(city: str, violation_code: str | None = None) -> dict:
    """Exact numbers from the city's restaurant inspection open data, cached in Postgres.

    For NYC: DOHMH restaurant inspection results (NYC Open Data dataset 43nn-pn8j).
    Each city gets its own adapter, so the agent sees the same shape everywhere.
    """
    raise NotImplementedError("Week 4")


def calculate(expression: str) -> float:
    """Safe arithmetic for counts, rates and percentages (no eval())."""
    raise NotImplementedError("Week 4")
