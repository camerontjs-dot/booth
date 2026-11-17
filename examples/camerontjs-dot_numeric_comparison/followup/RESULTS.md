# Frozen numeric checker: wider-format follow-up

On 30 fresh synthetic questions, the frozen follow-up reference grader marked 8 answers correct, 1 wrong and 21 unscoreable. Both numeric integrations accepted 4 answers and withheld 26, including 4 of the 8 declared correct answers. Every numeric withholding stopped at grammar validation; none demonstrated a numeric-disagreement decision.

This is a limits report for the bounded example rule from [PR #39](https://github.com/Vedantgitbot/booth/pull/39). It does not estimate a general numeric-error catch rate or propose a BOOTH core change.

## Method and identity

Codex helped implement, execute and check this study. A separate Codex task authored the cases under recorded restrictions excluding the checker implementation, original cases, grader and results. This is synthetic agent-authored material, not an external or blinded benchmark. [CASE_PROVENANCE.json](CASE_PROVENANCE.json) records the aperture and a source-layout clarification made before checker outcomes were observed; values, references, questions and controls were unchanged by that clarification.

The original numeric rule, BOOTH core, thresholds and original study files stayed unchanged. Broader source/answer forms were tested against that frozen rule, including forms it does not advertise supporting. The application still supplies the target field label and rounding instruction.

A makes one real BOOTH-default-prompt call per question. B replays that same raw reply through the validator. C and D evaluate A's parsed answer against the same source. B and D share a numeric rule; this is not four independent generations or two independent numeric algorithms.

| Setting | Value |
|---|---|
| Experimental source | [658519e2b25ba3b1cec0d3ff62a1a665f5b66629](https://github.com/camerontjs-dot/booth/commit/658519e2b25ba3b1cec0d3ff62a1a665f5b66629) |
| Source freeze | [freeze.json](freeze.json), SHA-256 `02eb21ecaa09a5f2d8e3865c466dfcadcc3d4e48fdcedce4723c2d3effea8015` |
| BOOTH / Python | 0.5.9 / 3.12.13 |
| Provider / model | local Ollama 0.40.16 / `gemma3:12b`, Q4_K_M |
| Model digest | `f4031aab637d1ffa37b42570452ae0e4fad0314754d17ded67322e4b95836f8a` |
| Hardware | Apple M3, 8 logical CPUs, 24 GiB RAM |
| Generation | temperature 0, seed 42, num_predict 1024, num_ctx 4096, timeout 300 seconds |
| Calls | 3 separate smoke + 30 main = 33; zero warm-ups or retries |
| Phase elapsed time | smoke 33.6 s; main 287.6 s, including phase bookkeeping |

The smoke evidence passed saved-run verification before main began. Smoke completion concerns infrastructure and evidence integrity, not favorable answer accuracy. No source, case, prompt, grading rule or threshold was changed after inference began. See the frozen [protocol](PROTOCOL.md).

The apparatus README/protocol are preserved preparation snapshots. This report and `recorded/` document the completed run.

## Main results: all 30 questions

All replies parsed as BOOTH JSON; there were no transport, parse or checker failures and no missing answers. The 21 unscoreables are quantity-grader exclusions, not failed calls or automatically wrong answers. They prevent a defensible overall accuracy estimate from the declared labels.

| Checkpoint | Accepted / 30 | Correct accepted / 8 | Correct withheld / 8 | Wrong accepted / 1 | Unscoreable accepted / 21 |
|---|---:|---:|---:|---:|---:|
| Plain check | 30 | 8 | 0 | 1 | 21 |
| Numeric validator | 4 | 4 | 4 | 0 | 0 |
| Keyword evidence | 27 | 8 | 0 | 1 | 18 |
| Numeric evidence | 4 | 4 | 4 | 0 | 0 |

The numeric validator returned `UNCERTAIN` for 26 answers; numeric evidence returned `BLOCKED` for those same 26. Reasons were 13 unsupported-grammar and 13 missing-unit failures. The four numeric acceptances were declared correct.

These counts measure this selected stress set. They do not estimate false-withholding or detection rates within the rule's advertised supported domain.

## Observed wrong quantities and the actual rejection stage

| Case | Raw answer field | Required quantity | Frozen follow-up grade | Numeric reason |
|---|---|---|---|---|
| main_17 | `40000 GBP` | `4000 GBP` | wrong | unsupported quantity grammar |
| main_26 | `-9.9` | `-10.0 GBP` | unscoreable | unsupported quantity grammar |
| main_27 | `-12.5` | `-13 CAD` | unscoreable | explicit unit or currency required |
| main_28 | `8.5` | `9 EUR` | unscoreable | explicit unit or currency required |

For main_17, `0.000004 billion GBP` is `4000 GBP`; the model returned ten times that amount at confidence 0.95. Plain check and keyword matching accepted it. The numeric gates withheld it before value comparison because the source uses unsupported GBP/billion syntax. This does not demonstrate that the comparator detected the tenfold error.

The other three rows are separate contextual rounding observations: half-up rounding of -9.95 to one decimal is -10.0; -12.5 to zero decimals is -13; 8.5 to zero decimals is 9. These answers omitted units and remain **unscoreable in the primary results**. All three had confidence 1.0 and passed plain check and keyword matching. Their numeric withholds also stopped before mismatch checking.

The [contextual review](contextual_review.json) preserves this distinction; it does not replace the frozen grades.

## Correct replies withheld outside the grammar

- main_15: `-12.5%` is correct; the requested source contains Unicode minus.
- main_19: `−0.000 percent` is correct; Unicode minus is unsupported.
- main_21: `12 345 678.90 EUR` is correct; thin-space grouping is unsupported.
- main_24: `9,876,543 JPY` is correct; the frozen rule supports CAD/USD/EUR.

These are expected boundaries of the declared grammar. A caller needs to distinguish an unsupported comparison from evidence of a numeric disagreement.

## Reference-grader and prompt limits

The frozen follow-up grader differs from the historical grader. It uses exact rational arithmetic and a declared broader syntax, but is not a strict superset of the original parser. Candidate answers are never rounded during grading.

Of the 21 unscoreables, 19 are plain numbers without units, one is the bare rate fraction `7/8`, and one is `25/4 USD`, which lacks the grader's required literal `fraction` prefix. Separate contextual review found 18 matching magnitudes and the three rounding misses above. This post-run diagnostic is not a replacement model-accuracy table.

The case `answer_format` metadata was **not appended to the actual model prompt**. The grader therefore requires an explicit output format without ensuring the model received that exact formatting instruction. This is a limitation of the experiment. No prompt or grading patch, new generation or silent relabeling was used to remove it.

## Separate authored-candidate layer

The 30 main cases each have a correct and wrong authored answer. These 60 fixtures use parseable JSON, confidence 0.99 and ambiguous=false. They are not model outputs or measured confidence observations.

Both numeric integrations withheld all 30 wrong candidates and 27 of 30 correct candidates. Plain check accepted all fixtures by construction. Keyword matching accepted 25 wrong candidates and withheld 12 correct candidates. These outcomes stress syntax coverage; they are not general comparator-accuracy estimates.

[Authored records](recorded/authored-main/records.jsonl) and their [generated summary](recorded/authored-main/summary.md) are separate from main and smoke model results.

## Evidence and offline verification

- [Main exact provider requests, replies and HTTP response-body bytes](recorded/main/provider_calls.jsonl)
- [Main checkpoint records](recorded/main/records.jsonl), [manifest](recorded/main/manifest.json), [summary](recorded/main/summary.md)
- [Smoke evidence](recorded/smoke/)
- [Compact verification receipts](verification.json)
- [Follow-up verifier](verify_followup.py)
- [Original-study verifier](verify_recorded.py), adapted from the separately implemented original saved-run auditor

The raw run files are byte-for-byte copies of the original saved evidence. There were no call failures in this run. Failure-path unit fixtures, prior preparation failures and authoring versions remain retained locally.

From the repository root, install this checkout in a clean environment and verify without a model:

```bash
python -m pip install -e '.[dev]'
python examples/camerontjs-dot_numeric_comparison/followup/verify_followup.py --run-dir examples/camerontjs-dot_numeric_comparison/followup/recorded/smoke
python examples/camerontjs-dot_numeric_comparison/followup/verify_followup.py --run-dir examples/camerontjs-dot_numeric_comparison/followup/recorded/main
python examples/camerontjs-dot_numeric_comparison/followup/verify_followup.py --run-dir examples/camerontjs-dot_numeric_comparison/followup/recorded/authored-main
```

Follow-up source binding needs a Git clone containing the recorded experimental commit. The verifier rejects missing, malformed, contradictory or incomplete evidence and makes no model/provider calls.

Smoke passed 132 saved-evidence checks; main passed 645; authored candidates passed 710. A separate saved-run review reconciled 107 checks, all 33 raw replies, source/reference pairs and seven rounding references. A further methods review found no material numerical or conclusion correction. These are agent reviews and saved-run consistency checks, not human-independent or blind scientific qualification.

The source suite passed 535 tests, 344 subtests and six skips with real network calls blocked during preparation. Replay and corruption tests use explicit unit fixtures, not model observations.

## Interpretation

The supported conclusion is narrow: the frozen example's behavior depends on representation and grammar coverage. Confidence and word overlap admitted the observed numeric mistakes, while numeric gates withheld correct out-of-grammar quantities as well. This run supplies no reliable numeric-discrimination rate, calibration result, retry-recovery result or general finance-reliability claim.

A useful next step would be an agreed answer-format/unit contract and clearer reporting of unsupported comparisons. Any changed prompt, grader or grammar would require a successor experiment. No BOOTH core or dependency change is proposed here.
