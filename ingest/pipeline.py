"""Python ingestion path used by `make ingest` until the Kafka path exists."""


def main() -> None:
    # rule documents: download -> parse -> chunk -> embed -> write to pgvector
    # inspections: download the city's open data -> write to Postgres
    raise NotImplementedError("Week 1")


if __name__ == "__main__":
    main()
