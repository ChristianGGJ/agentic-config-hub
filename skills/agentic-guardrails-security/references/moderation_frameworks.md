# Moderation Framework Integrations: Llama Guard, Guardrails AI, Presidio

Concrete, current-API integration guidance for the three optional frameworks this skill
supports. Architecture and stdlib fallbacks live in `security_guardrail_patterns.md`;
measuring any of this lives in `guardrail_effectiveness_evaluation.md`.

**Version assumptions (state yours in your guard config):**

| Framework | Assumed version | Install |
|---|---|---|
| Llama Guard | Llama-Guard-3 family (`1B`, `8B`, `11B-Vision`); Llama-Guard-4-12B for multimodal | weights via Hugging Face (gated, license acceptance), Ollama, or a hosting provider (BYOK) |
| Guardrails AI | `guardrails-ai` >= 0.5 | `pip install guardrails-ai` + `guardrails configure` + per-validator hub installs |
| Presidio | `presidio-analyzer` / `presidio-anonymizer` 2.x | `pip install presidio-analyzer presidio-anonymizer` + `python -m spacy download en_core_web_lg` |

**Degradation ladder (never silently skip a checkpoint):** Llama Guard unavailable ->
signature + heuristic tier; Presidio unavailable -> stdlib Luhn/regex fallback;
Guardrails AI unavailable -> call Presidio + custom checks directly. Log every
degradation with the tier that actually ran (`GuardVerdict.degraded = True`).

---

## 1. Llama Guard

Llama Guard is a *fine-tuned classifier LLM*: you hand it a conversation, it returns a
tiny completion that is literally `safe`, or `unsafe` followed by a line of violated
category codes. It is not a chat model — never route user traffic through it as a
responder.

### 1.1 Hazard taxonomy (MLCommons-aligned)

Llama Guard 3 ships with 14 categories aligned to the MLCommons hazard taxonomy:

| Code | Category | Code | Category |
|---|---|---|---|
| S1 | Violent Crimes | S8 | Intellectual Property |
| S2 | Non-Violent Crimes | S9 | Indiscriminate Weapons |
| S3 | Sex-Related Crimes | S10 | Hate |
| S4 | Child Sexual Exploitation | S11 | Suicide & Self-Harm |
| S5 | Defamation | S12 | Sexual Content |
| S6 | Specialized Advice | S13 | Elections |
| S7 | Privacy | S14 | Code Interpreter Abuse |

Llama Guard 4 (12B, multimodal text+image) keeps the same `safe`/`unsafe` + S-codes
output contract; verify its exact category list against the current model card before
mapping codes to policy actions. Note what the taxonomy is *not*: it moderates content
harm, not prompt injection. `S14` only covers code-abuse in tool-running contexts. For
injection-specific classification, see the Prompt Guard sidebar in 1.5.

### 1.2 Prompt template and invocation (transformers, local)

Do not hand-build the policy prompt — the tokenizer's chat template embeds the policy
text, category list, and the instruction to classify the **last turn** of the
conversation. Pass a chat, get a verdict:

```python
# pip install transformers torch  (optional integration; wrap imports)
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_ID = "meta-llama/Llama-Guard-3-1B"   # 1B: cheapest; 8B: higher recall

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, device_map="auto")

def llama_guard_classify(chat: list) -> str:
    """chat = [{'role': 'user'|'assistant', 'content': '...'}, ...]
    Classifies the LAST turn. Returns the raw completion text."""
    input_ids = tokenizer.apply_chat_template(chat, return_tensors="pt").to(model.device)
    out = model.generate(input_ids=input_ids, max_new_tokens=32,
                         pad_token_id=tokenizer.eos_token_id, do_sample=False)
    return tokenizer.decode(out[0][input_ids.shape[-1]:], skip_special_tokens=True)
```

- **Input (prompt) moderation:** pass `[{"role": "user", "content": user_text}]`.
- **Output (response) moderation:** pass both turns —
  `[{"role": "user", ...}, {"role": "assistant", "content": draft}]` — the template
  then classifies the assistant turn in context.
- `do_sample=False` keeps verdicts deterministic for a given model build.
- Custom/trimmed category sets: the chat template accepts policy customization
  arguments in current transformers releases — verify the exact template kwargs
  against the model card for your model generation before relying on them.

### 1.3 Output parsing (fail-closed on garbage)

```python
def parse_llama_guard(raw: str):
    """Returns (allowed: bool, categories: list[str]).
    Unparseable output is treated as a guard failure -> caller fails closed."""
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty moderation output")
    verdict = lines[0].lower()
    if verdict == "safe":
        return True, []
    if verdict == "unsafe":
        cats = [c.strip() for c in lines[1].split(",")] if len(lines) > 1 else []
        return False, cats
    raise ValueError("unrecognized moderation output: %r" % lines[0][:40])
```

Wire this through `run_guard()` from `security_guardrail_patterns.md` section 2 so a
`ValueError` becomes a fail-closed verdict, not an unhandled crash.

### 1.4 Deployment: local vs hosted

| Option | How | Fits when |
|---|---|---|
| Local, transformers | code above; 1B runs on CPU acceptably, 8B wants a GPU | data cannot leave the boundary; low QPS |
| Local, Ollama | `ollama run llama-guard3` (1b/8b tags), call via its local HTTP API | easiest local ops; verify tag names against the Ollama library |
| Local, vLLM | serve the model behind an OpenAI-compatible endpoint | production throughput, batching, p95 control |
| Hosted (BYOK) | several inference providers serve the Llama Guard family; send the chat, parse the same completion | no GPU to run; provider must be in your data boundary |

Latency defaults for firewall budgeting: 1B local ~50-200 ms, 8B ~100-500 ms
(hardware-dependent — measure yours; the eval harness records latency per tier).

### 1.5 Sidebar: Prompt Guard (injection-specific classifier)

Meta also publishes small dedicated jailbreak/injection classifiers (Prompt Guard /
Llama Prompt Guard 2 family, ~22M-86M parameters) that output a malicious-probability
score rather than S-codes — far cheaper than Llama Guard for the injection tier and a
natural score source for the two-threshold design in
`guardrail_effectiveness_evaluation.md`. Verify current model names and label heads
against the Hugging Face model cards before integrating.

---

## 2. Guardrails AI

Guardrails AI structures the *output validation pipeline*: a `Guard` runs an ordered
set of validators, each with a declared `on_fail` action. Most hub validators run
locally (many wrap local ML models or Presidio) — no paid service required.

### 2.1 Install and add validators

```bash
pip install guardrails-ai
guardrails configure                     # one-time; hub token is free
guardrails hub install hub://guardrails/toxic_language
guardrails hub install hub://guardrails/detect_pii
guardrails hub install hub://guardrails/regex_match
```

### 2.2 Guard + validators + on_fail

```python
# as of guardrails-ai 0.5+
from guardrails import Guard, OnFailAction
from guardrails.hub import ToxicLanguage, DetectPII, RegexMatch

guard = Guard().use_many(
    ToxicLanguage(threshold=0.5, validation_method="sentence",
                  on_fail=OnFailAction.EXCEPTION),
    DetectPII(pii_entities=["EMAIL_ADDRESS", "CREDIT_CARD", "US_SSN"],
              on_fail=OnFailAction.FIX),          # FIX = redact in place
    RegexMatch(regex=r"^[\s\S]{1,4000}$", on_fail=OnFailAction.EXCEPTION),
)

outcome = guard.validate(model_draft)          # -> ValidationOutcome
if outcome.validation_passed:
    ship(outcome.validated_output)             # may differ from input (FIX/FILTER)
```

`on_fail` actions and when to pick each:

| Action | Behavior | Use for |
|---|---|---|
| `EXCEPTION` | raise `ValidationError` | fail-closed checkpoints (input firewall, regulated output) |
| `FIX` | validator repairs the text (e.g. redacts PII) | PII redaction where the rest of the response is fine |
| `FILTER` | remove the offending span | list-shaped outputs where one bad item is droppable |
| `REFRAIN` | return no output at all | whole response is unusable if any check fails |
| `REASK` | re-prompt the LLM with the failure | only inside a bounded retry loop with declared exit conditions (see the schema loop in `security_guardrail_patterns.md` section 5) |
| `NOOP` | record failure, pass text through | shadow mode: measure a new validator's FP rate before enforcing it |

`NOOP` shadow mode is the correct first deployment for any new validator — collect
verdicts into the eval corpus, measure, then flip to an enforcing action.

### 2.3 Notes and boundaries

- `DetectPII` wraps Presidio under the hood — if you need custom recognizers or
  per-entity operators, drop to Presidio directly (section 3) instead of stacking both.
- `Guard` can also wrap LLM calls directly (`guard(...)` with model/messages routed
  via LiteLLM) and validate streamed output; pydantic-schema guards exist
  (`Guard.from_pydantic(output_class=...)` historically; the constructor family was
  renamed in newer releases — verify against your installed version's docs). This
  skill prefers the plain `guard.validate(text)` surface: it composes cleanly with the
  checkpoint wrapper and keeps the LLM call under your own routing/budget control.
- Legacy `.rail` XML specs still exist but code-first validators are the current
  recommended surface; do not start new work on RAIL.
- Validators are detectors: they have FP/FN curves. Measure each enforcing validator
  against your labeled corpus like any other guard tier.

---

## 3. Presidio (PII detection and redaction)

Presidio splits detection (`presidio-analyzer`: NER + patterns + checksums + context
words) from remediation (`presidio-anonymizer`: operators applied to detected spans).
It runs fully local.

### 3.1 Analyze then anonymize

```python
# as of presidio-analyzer / presidio-anonymizer 2.x
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

analyzer = AnalyzerEngine()        # loads spaCy NER (en_core_web_lg by default config)
anonymizer = AnonymizerEngine()

def redact_pii(text: str) -> str:
    results = analyzer.analyze(
        text=text,
        language="en",
        entities=["CREDIT_CARD", "EMAIL_ADDRESS", "PHONE_NUMBER",
                  "US_SSN", "PERSON", "IP_ADDRESS"],   # omit -> all recognizers
        score_threshold=0.5,       # tune against your corpus, not by vibes
    )
    # results: list[RecognizerResult] with .entity_type .start .end .score
    redacted = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators={
            "DEFAULT":       OperatorConfig("replace", {"new_value": "<PII>"}),
            "CREDIT_CARD":   OperatorConfig("mask", {"masking_char": "*",
                                                     "chars_to_mask": 12,
                                                     "from_end": False}),
            "EMAIL_ADDRESS": OperatorConfig("hash", {"hash_type": "sha256"}),
        },
    )
    return redacted.text
```

Operator selection maps to the SKILL.md "PII action selection" table: `replace`
(redact with tag), `mask` (partial), `hash` (joinable key), `redact` (delete span),
`encrypt`/`decrypt` (reversible, keyed), `keep`, `custom` (callable). The built-in
`CREDIT_CARD` recognizer performs **Luhn checksum validation** — this is why Presidio
beats any bare 13-16-digit regex on false positives (the exact failure the audit
flagged in this skill's previous version).

### 3.2 Custom recognizer (pattern + context words)

```python
from presidio_analyzer import Pattern, PatternRecognizer

employee_id = PatternRecognizer(
    supported_entity="EMPLOYEE_ID",
    patterns=[Pattern(name="emp_id", regex=r"\bEMP-\d{6}\b", score=0.6)],
    context=["employee", "staff", "badge"],   # nearby words boost the score
)
analyzer.registry.add_recognizer(employee_id)

results = analyzer.analyze(text=text, language="en")   # now includes EMPLOYEE_ID
```

Deny-list recognizers (`PatternRecognizer(supported_entity=..., deny_list=[...])`)
handle finite sets like internal project codenames. For entities needing real NER, a
custom NLP engine (spaCy or transformers-based) can be configured via
`NlpEngineProvider` — verify configuration keys against current Presidio docs.

### 3.3 Operational notes

- **Threshold tuning:** `score_threshold` trades FP for FN exactly like any detector;
  sweep it with the labeled-corpus harness (`guardrail_eval.py --sweep` over per-span
  scores aggregated to a per-sample decision).
- **Allow-listing:** pass known-benign tokens (support emails, demo card numbers) via
  `analyzer.analyze(..., allow_list=[...])` rather than lowering the global threshold.
- **Latency:** 10-50 ms typical per response locally; NER dominates. For
  high-throughput paths restrict `entities=` to what the policy actually needs.
- **Degradation:** wrap imports; on `ImportError` fall back to
  `redact_pii_fallback()` (stdlib Luhn version in `security_guardrail_patterns.md`
  section 5) and set `degraded=True` on the verdict.

---

## 4. Wiring all three into the checkpoints

```python
def output_firewall(user_text: str, draft: str) -> str:
    # Tier 1: moderation (Llama Guard on the assistant turn) - fail closed
    verdict = run_guard(
        lambda d: _lg_verdict(user_text, d), draft, timeout_s=2.0, fail_open=False)
    if not verdict.allowed:
        raise GuardrailExhausted("moderation block: %s" % verdict.reason)

    # Tier 2: PII (Presidio if available, stdlib Luhn fallback otherwise)
    try:
        clean = redact_pii(draft)                      # section 3
    except ImportError:
        clean = redact_pii_fallback(draft)             # stdlib fallback, log degraded

    # Tier 3: structural validators (Guardrails AI), shadow-mode first
    return _run_validators(clean)                      # section 2
```

Placement recap: Llama Guard belongs at input and output (content harm), Presidio at
output (PII), Guardrails AI at output (structure + policy checks), and none of them
replace the tool-call firewall — that checkpoint is structural prevention and stays
framework-free (`security_guardrail_patterns.md` section 4).
