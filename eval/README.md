# Evaluation data

| File | What |
|---|---|
| `golden_set.jsonl` | The golden question set, one JSON object per line (empty until the questions are drafted) |
| `reports/` | One report per evaluation run (created with the first run) |

The format, question types, metrics and process are in [docs/evaluation-plan.md](../docs/evaluation-plan.md).

## Adding or verifying a question
1. Add a line to `golden_set.jsonl` (copy the example from the plan). New ids continue the sequence (`q007` after `q006`).
2. Open the PDF at the cited page and check that `quote` is there and supports `expected_answer`.
3. Set `verified_on` to today's date. Leave it `null` while it's a draft.
4. Check the file:
   ```bash
   uv run python -m app.cli check-golden-set
   ```
   It lists every problem with its line number, then a summary (verified vs. draft, by type, by author).
