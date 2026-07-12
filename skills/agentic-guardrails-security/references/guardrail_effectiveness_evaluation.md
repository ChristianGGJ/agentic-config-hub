# Guardrail Effectiveness Evaluation

A guardrail you have not measured is a guardrail you do not have. This file is the
methodology for proving a detector (Llama Guard, a Presidio recognizer, an injection
classifier, a regex filter) actually works — and at what operating point.

> The audit found that no skill in the hub teaches detector *effectiveness*. This skill
> owns it. Threat modeling lives in `ai-security`; package auditing in
> `skill-security-auditor`.

## 1. The confusion matrix, in guardrail terms

For a binary guard (block / allow) over a labeled corpus:

| | Actually unsafe | Actually safe |
|---|---|---|
| **Guard blocked** | True Positive (TP) | **False Positive (FP)** — a legitimate request blocked |
| **Guard allowed** | **False Negative (FN)** — an attack got through | True Negative (TN) |

- **Recall (TPR) = TP / (TP + FN)** — of all real attacks, how many were caught.
- **Precision = TP / (TP + FP)** — of all blocks, how many were real attacks.
- **False Positive Rate (FPR) = FP / (FP + TN)** — of all legitimate traffic, how much was wrongly blocked.

## 2. Why FPR, not recall, decides adoption

Recall gets the attention; **FPR gets guardrails turned off.** Base-rate reasoning:

> At 1% attack prevalence, a guard with 95% recall and 5% FPR sees, per 10,000 requests:
> ~95 true blocks (of 100 attacks) and ~495 false blocks (5% of 9,900 legit).
> **~5 false blocks for every true block.** Operations disables the guard within a week.

The rarer the attack, the more a small FPR dominates the user experience. Always report
FPR against realistic prevalence, not just recall on a balanced test set.

## 3. Building the labeled corpus

- **Positives (unsafe):** curated attacks per category (injection, jailbreak, PII leak,
  toxic content). Reuse public red-team sets; add your own product-specific attacks.
- **Negatives (safe):** *representative production traffic*, not toy sentences. FPR is
  only meaningful against the real distribution the guard will see. Include hard
  negatives — benign text that superficially resembles attacks (a user quoting
  "ignore previous instructions" while asking how injection works).
- **Hold-out discipline:** tune thresholds on a dev split, report final numbers on a
  hold-out split you never tuned against. Rotate the corpus as attackers adapt.
- **Stratify by category:** an aggregate 95% recall can hide 40% recall on one attack
  class. Report per-category recall/FPR.

## 4. Two-threshold (allow / review / block) design

A single threshold forces every borderline case into a wrong bucket. Use two:

```
score < t_low            -> ALLOW        (fast path, no cost)
t_low <= score < t_high  -> REVIEW        (LLM-judge or human; small % of traffic)
score >= t_high          -> BLOCK
```

Set `t_high` for high precision (few false blocks) and `t_low` for high recall (few
misses), routing only the uncertain band to expensive review. This is how you get both
low FPR and low FN without paying judge cost on every request.

## 5. Choosing the operating point

- Sweep the threshold and plot the **ROC curve** (TPR vs FPR) and the
  **precision-recall curve** (PR is more informative at low prevalence).
- Pick the point by *cost*, not by a round number: assign a cost to a missed attack
  (FN) and to a false block (FP), then minimize expected cost at your prevalence.
- Report the whole curve, never a single cherry-picked number. A guard is a dial, not a
  switch.

## 6. Deterministic scoring (stdlib)

```python
def metrics(results):
    """results: list of (predicted_block: bool, actually_unsafe: bool)."""
    tp = sum(1 for p, a in results if p and a)
    fp = sum(1 for p, a in results if p and not a)
    fn = sum(1 for p, a in results if not p and a)
    tn = sum(1 for p, a in results if not p and not a)
    recall    = tp / (tp + fn) if tp + fn else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    fpr       = fp / (fp + tn) if fp + tn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": round(recall, 4), "precision": round(precision, 4),
            "fpr": round(fpr, 4)}
```

No LLM or network needed to score — labels in, metrics out. Regenerate on every guard
change and every corpus refresh; treat a recall drop or FPR rise as a regression.

## 7. Hub canon integration

- Effectiveness evaluation is a `success_predicate`: a guard ships only when it clears
  the agreed recall floor AND the FPR ceiling on the hold-out set.
- A guard whose FPR rises past the ceiling in production fires an `escalation_trigger`
  (route to human, do not silently loosen the threshold).
- Log every REVIEW-band decision so the corpus grows from real traffic (closes the loop
  without over-fitting to the original test set).
