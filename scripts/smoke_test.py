"""Week 0 smoke test: prove every moving part of the stack works end to end, once.

    python scripts/smoke_test.py      (run from the project root, with .venv activated)

It runs six checks in pipeline order. Each prints PASS, FAIL (with the reason) or SKIP
(when a check it depends on failed), and the script exits with code 1 if anything failed.

  1. config     .env is read and the settings the other checks need are filled in
  2. embedding  bge-small turns text into 384 numbers, and similar text lands close together
  3. database   Postgres is up, the pgvector extension and the schema from db/init.sql exist
  4. retrieval  store a few vectors in pgvector and get the right one back for a question
  5. llm        send the retrieved text plus the question to Claude and get an answer
  6. langfuse   the keys work, and steps 2, 4 and 5 show up as one trace in the Langfuse UI

Nothing it writes is kept: the vectors go into a TEMP table that disappears on disconnect.
"""

import sys
import time
from collections.abc import Callable
from typing import Any

from app.config import get_settings

# A tiny "corpus" of three passages. The question should retrieve the one at EXPECTED_PASSAGE.
PASSAGES = [
    "Cold food must be held at 41 degrees Fahrenheit or below.",
    "The restaurant group opened 12 new locations across Brooklyn and Queens during the year.",
    "An inspection score of 0 to 13 points earns the restaurant an A grade.",
]
QUESTION = "How many new locations did the restaurant group open?"
# The checks compare against these two, so change them together with QUESTION.
EXPECTED_PASSAGE = 1  # index in PASSAGES of the passage that answers QUESTION
EXPECTED_IN_ANSWER = "12"  # text the LLM's answer must contain
EXPECTED_DIM = 384

# Results shared between checks (later checks reuse what earlier ones produced).
state: dict[str, Any] = {}


def check_config() -> str:
    s = get_settings()
    missing = [
        name
        for name, value in {
            "LLM_PROVIDER": s.llm_provider,
            "LLM_MODEL_SMALL": s.llm_model_small,
            "ANTHROPIC_API_KEY": s.anthropic_api_key,
            "LANGFUSE_PUBLIC_KEY": s.langfuse_public_key,
            "LANGFUSE_SECRET_KEY": s.langfuse_secret_key,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"missing in .env: {', '.join(missing)}")
    if s.embedding_dim != EXPECTED_DIM:
        raise RuntimeError(f"EMBEDDING_DIM={s.embedding_dim}, but db/init.sql uses vector(384)")
    return f"provider={s.llm_provider}, model={s.llm_model_small}"


def check_embedding() -> str:
    from rag.embeddings import embed_query, embed_texts

    t0 = time.perf_counter()
    doc_vectors = embed_texts(PASSAGES)
    query_vector = embed_query(QUESTION)
    elapsed = time.perf_counter() - t0

    if len(query_vector) != EXPECTED_DIM:
        raise RuntimeError(f"expected {EXPECTED_DIM} dimensions, got {len(query_vector)}")

    # Vectors are normalised, so the dot product is the cosine similarity (-1 to 1).
    sims = [sum(q * d for q, d in zip(query_vector, v, strict=True)) for v in doc_vectors]
    best = max(range(len(sims)), key=sims.__getitem__)
    if best != EXPECTED_PASSAGE:
        raise RuntimeError(
            f"question was closest to passage {best}, not {EXPECTED_PASSAGE}: sims={sims}"
        )

    state["doc_vectors"], state["query_vector"] = doc_vectors, query_vector
    pretty = ", ".join(f"{x:.2f}" for x in sims)
    return f"dim={len(query_vector)}, similarities=[{pretty}], took {elapsed:.1f}s"


def _connect() -> Any:
    import psycopg
    from pgvector.psycopg import register_vector

    # DATABASE_URL is in SQLAlchemy form (postgresql+psycopg://); psycopg wants postgresql://.
    url = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(url, connect_timeout=5, autocommit=True)
    register_vector(conn)  # lets us pass Python lists / numpy arrays as `vector` values
    return conn


def check_database() -> str:
    conn = _connect()
    ext = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
    if ext is None:
        raise RuntimeError("pgvector extension is not installed (did db/init.sql run?)")
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
    }
    expected = {"filings", "sections", "chunks", "xbrl_cache", "audit_log"}
    if missing := expected - tables:
        raise RuntimeError(f"tables missing: {sorted(missing)}")
    state["conn"] = conn
    return f"pgvector {ext[0]}, tables: {', '.join(sorted(expected))}"


def check_retrieval() -> str:
    import numpy as np

    conn = state["conn"]
    conn.execute(
        f"CREATE TEMP TABLE smoke_chunks (id int, content text, embedding vector({EXPECTED_DIM}))"
    )
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO smoke_chunks VALUES (%s, %s, %s)",
            [
                (i, text, np.array(vec))
                for i, (text, vec) in enumerate(zip(PASSAGES, state["doc_vectors"], strict=True))
            ],
        )
    # <=> is pgvector's cosine DISTANCE operator (1 - cosine similarity), so smallest = closest.
    row = conn.execute(
        "SELECT id, content, embedding <=> %s AS distance FROM smoke_chunks ORDER BY distance "
        "LIMIT 1",
        (np.array(state["query_vector"]),),
    ).fetchone()
    if row[0] != EXPECTED_PASSAGE:
        raise RuntimeError(f"top hit was passage {row[0]}, expected {EXPECTED_PASSAGE}")
    state["context"] = row[1]
    return f"top hit = passage {row[0]} (cosine distance {row[2]:.3f})"


def check_llm() -> str:
    from rag.llm import get_llm_client

    system = "Answer only from the context. If the context does not say, reply 'not found'."
    user = f"Context:\n{state['context']}\n\nQuestion: {QUESTION}"
    t0 = time.perf_counter()
    answer = get_llm_client().complete(system, user)
    elapsed = time.perf_counter() - t0
    if EXPECTED_IN_ANSWER not in answer:
        raise RuntimeError(f"answer does not contain {EXPECTED_IN_ANSWER}: {answer!r}")
    state["prompt"], state["answer"] = {"system": system, "user": user}, answer
    return f"{answer.strip()[:80]!r} ({elapsed:.1f}s)"


def check_langfuse() -> str:
    from langfuse import Langfuse

    s = get_settings()
    langfuse = Langfuse(
        public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, host=s.langfuse_host
    )
    langfuse.auth_check()  # raises if the keys or host are wrong

    # Record what the earlier checks did as one trace: a parent span with three children.
    # (From week 1 the real code traces itself; here we replay the steps after the fact.)
    with langfuse.start_as_current_observation(
        name="smoke-test", input={"question": QUESTION}
    ) as root:
        with langfuse.start_as_current_observation(
            name="embed-query", as_type="embedding", model=s.embedding_model, input=QUESTION
        ) as obs:
            obs.update(output={"dim": len(state["query_vector"])})
        with langfuse.start_as_current_observation(
            name="vector-search", as_type="retriever", input=QUESTION
        ) as obs:
            obs.update(output=[state["context"]])
        with langfuse.start_as_current_observation(
            name="llm-answer", as_type="generation", model=s.llm_model_small, input=state["prompt"]
        ) as obs:
            obs.update(output=state["answer"])
        root.update(output=state["answer"])
        trace_id = langfuse.get_current_trace_id()

    langfuse.flush()  # the SDK batches in the background; flush so the trace is sent now
    return f"trace sent: {langfuse.get_trace_url(trace_id=trace_id)}"


CHECKS: list[tuple[str, Callable[[], str], list[str]]] = [
    # (name, function, names of checks it depends on)
    ("config", check_config, []),
    ("embedding", check_embedding, ["config"]),
    ("database", check_database, ["config"]),
    ("retrieval", check_retrieval, ["embedding", "database"]),
    ("llm", check_llm, ["retrieval"]),
    ("langfuse", check_langfuse, ["llm"]),
]


def main() -> int:
    passed: set[str] = set()
    failed = 0
    for name, fn, needs in CHECKS:
        if missing := [n for n in needs if n not in passed]:
            print(f"SKIP  {name:<10} needs {', '.join(missing)}")
            continue
        try:
            detail = fn()
        except Exception as exc:  # report every failure and keep going
            failed += 1
            print(f"FAIL  {name:<10} {type(exc).__name__}: {exc}")
        else:
            passed.add(name)
            print(f"PASS  {name:<10} {detail}")
    if "conn" in state:
        state["conn"].close()
    print(f"\n{len(passed)}/{len(CHECKS)} checks passed")
    return 1 if failed or len(passed) < len(CHECKS) else 0


if __name__ == "__main__":
    sys.exit(main())
