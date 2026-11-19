"""Request and response models for the API."""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    # Limit the search to one jurisdiction, e.g. "us-ny-nyc" or "federal". None searches all.
    jurisdiction: str | None = None


class Citation(BaseModel):
    id: int
    jurisdiction: str  # "federal", "us-ny-nyc", ...
    source: str  # document title, e.g. "FDA Food Code 2022" or "NYC Health Code Article 81"
    section: str
    url: str
    snippet: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    confidence: str = "unknown"  # high | partial | not_found
