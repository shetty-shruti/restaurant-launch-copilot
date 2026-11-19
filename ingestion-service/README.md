# Ingestion service (Go)

Polls each configured city's open data portal (NYC Open Data first) for new
restaurant inspection results and publishes them to `inspections.new`. The Python
worker (`../ingest/worker.py`) consumes those events and writes them to Postgres.

Built in weeks 5 to 6. Until then, `make ingest` runs the Python pipeline directly.

```bash
go run ./cmd/poller
```

The module path in `go.mod` assumes the GitHub repo is named
`restaurant-launch-copilot`. Change it if you pick another name.
