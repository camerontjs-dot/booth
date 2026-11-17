# Generated follow-up results

Status: **completed**.

Generated from saved records. This is a bounded synthetic study, not general numeric reliability.
The checker is frozen. Original development data, new authored candidates and model output are separate.

- Profile: gemma_harder; phase: main
- Mode: offline_controls
- Model configured: gemma3:12b; digest: f4031aab637d1ffa37b42570452ae0e4fad0314754d17ded67322e4b95836f8a
- Planned / attempted / failed model requests: 0 / 0 / 0
- Warm-ups: 0; retries: 0. Model replies are replayed across checkpoints.

**These are authored answer candidates, not model outputs. No model was invoked.**

## independent_authored_candidates

| Metric | check | validator | keyword evidence | numeric evidence |
|---|---:|---:|---:|---:|
| rows | 60 | 60 | 60 | 60 |
| evaluated | 60 | 60 | 60 | 60 |
| not_run | 0 | 0 | 0 | 0 |
| correct | 30 | 30 | 30 | 30 |
| wrong | 30 | 30 | 30 | 30 |
| unscoreable | 0 | 0 | 0 | 0 |
| no_answer | 0 | 0 | 0 | 0 |
| wrong_accepted | 30 | 0 | 25 | 0 |
| wrong_withheld | 0 | 30 | 5 | 30 |
| correct_accepted | 30 | 3 | 18 | 3 |
| correct_withheld | 0 | 27 | 12 | 27 |
| unscoreable_accepted | 0 | 0 | 0 | 0 |
| unscoreable_withheld | 0 | 0 | 0 | 0 |
| call_failed | 0 | 0 | 0 | 0 |
| all_parse_failed | 0 | 0 | 0 | 0 |
| checker_failed | 0 | 0 | 0 | 0 |
| ACCEPTED | 60 | 3 | 43 | 3 |
| REPAIRED | 0 | 0 | 0 | 0 |
| BLOCKED | 0 | 0 | 17 | 57 |
| UNCERTAIN | 0 | 57 | 0 | 0 |
| AMBIGUOUS | 0 | 0 | 0 | 0 |
| NOT_RUN | 0 | 0 | 0 | 0 |

Wrong-withheld uses scoreable wrong answers; correct-withheld uses scoreable correct answers.
Missing/unscoreable outputs, provider failures, unattempted questions and unevaluated checkpoints remain explicit.
NOT_RUN is not a rejection. Withheld includes non-ok evaluated results, including UNCERTAIN.
Unsupported answer grammar can withhold semantically correct answers; the broader grader is a separate bounded rule.
No retry recovery, independent B-versus-D algorithm, financial suitability or calibration claim is made.
