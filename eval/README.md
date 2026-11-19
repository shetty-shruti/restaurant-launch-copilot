# Eval

`dataset.jsonl` holds one question per line:

```json
{"id": "q001", "type": "single_fact", "question": "At what temperature must cold food be held in an NYC restaurant?", "expected_answer": "...", "jurisdiction": "us-ny-nyc", "source": "NYC Health Code Article 81", "section": "81.09"}
```

Types: `single_fact`, `cross_jurisdiction` (city vs federal rule), `inspection_numbers`
(answered from inspection data), `unanswerable`, `multi_step`.
