# Architecture

```
            ingestion path (weeks 5 to 6)
 NYC Open Data ──> Go poller ──> Kafka: inspections.new ──> Python worker ──> Postgres + pgvector
 (inspections)                                                  │                      ▲
                                                                └─> inspections.indexed │
                                                                                        │
            query path                                                                  │
 Streamlit ──> FastAPI /ask ──> RAG chain (weeks 1 to 3) ───────────────────────────────┤
                            └─> LangGraph agent (week 4) ──> tools ─────────────────────┘
                                   planner → tool loop → writer → verifier
                                                    │
                                                    └─> Langfuse traces, audit_log
```

Rule documents (FDA Food Code, NYC Health Code Article 81, eCFR) change rarely, so
`make ingest` loads them in a batch. Every document and chunk carries a jurisdiction
(`federal`, `us-ny-nyc`, ...), and each city's inspection data has its own adapter, so
adding a city (Chicago next) means new documents and one new adapter.

Until the Kafka path exists, `make ingest` runs `ingest/pipeline.py` and writes to Postgres directly.
