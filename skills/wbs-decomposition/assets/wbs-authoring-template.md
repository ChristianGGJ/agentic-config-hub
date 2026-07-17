# WBS Authoring Template

Copy a skeleton, replace the placeholders, then validate:

```bash
python scripts/wbs_validator.py my_wbs.json --check-estimates
```

## Nested shape (preferred for authoring)

```json
{
  "name": "<project name>",
  "objective": "<1-3 sentence macro objective, plus exclusions>",
  "wbs": [
    {
      "id": "1",
      "description": "<level-2 element: one decomposition basis per level>",
      "children": [
        {
          "id": "1.1",
          "description": "<leaf: deliverable-oriented, unique wording>",
          "deliverable": "<noun + observable acceptance signal>",
          "owner": "<single accountable owner>",
          "estimate_hours": 16,
          "estimate_basis": "<analogous | three-point | expert judgment>"
        },
        {
          "id": "1.2",
          "description": "<second child - every non-leaf needs >= 2>",
          "deliverable": "<...>",
          "owner": "<...>",
          "estimate_hours": 24,
          "estimate_basis": "<...>"
        }
      ]
    }
  ]
}
```

## Flat shape (for spreadsheet/CSV-derived data)

```json
{
  "name": "<project name>",
  "objective": "<...>",
  "elements": [
    {"id": "1", "description": "<branch>", "parent": null},
    {"id": "1.1", "description": "<leaf>", "parent": "1",
     "deliverable": "<...>", "estimate_hours": 16}
  ]
}
```

## Authoring rules (enforced by the validator where possible)

- Unique, non-empty `id` on every element (U1).
- Every non-leaf has >= 2 children (B1, 100-percent-rule structural proxy).
- Tree depth between 2 and 4 levels by default (D1).
- No duplicate or near-duplicate descriptions (X1/X2).
- Flat form: every `parent` must exist (O1).
- Dotted ids should extend their parent's id: `2.1` under `2` (N1).
- Leaves carry a `deliverable` (G1) and, ideally, `estimate_hours` within
  8-80 plus an `estimate_basis` (H1 with `--check-estimates`).
- `milestone: true`, `duration_days`, `baseline_start`, `baseline_finish`
  are optional extras passed through to the emitted plan.json.

Remember the honest limit: the validator proves structure, not semantic
completeness. Review the 100-percent question per branch by hand before the
human gate.
