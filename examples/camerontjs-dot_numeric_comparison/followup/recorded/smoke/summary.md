# Generated follow-up results

Status: **completed**.

Generated from saved records. This is a bounded synthetic study, not general numeric reliability.
The checker is frozen. Original development data, new authored candidates and model output are separate.

- Profile: gemma_harder; phase: smoke
- Mode: live
- Model configured: gemma3:12b; digest: f4031aab637d1ffa37b42570452ae0e4fad0314754d17ded67322e4b95836f8a
- Planned / attempted / failed model requests: 3 / 3 / 0
- Warm-ups: 0; retries: 0. Model replies are replayed across checkpoints.

## live

| Metric | check | validator | keyword evidence | numeric evidence |
|---|---:|---:|---:|---:|
| rows | 3 | 3 | 3 | 3 |
| evaluated | 3 | 3 | 3 | 3 |
| not_run | 0 | 0 | 0 | 0 |
| correct | 1 | 1 | 1 | 1 |
| wrong | 0 | 0 | 0 | 0 |
| unscoreable | 2 | 2 | 2 | 2 |
| no_answer | 0 | 0 | 0 | 0 |
| wrong_accepted | 0 | 0 | 0 | 0 |
| wrong_withheld | 0 | 0 | 0 | 0 |
| correct_accepted | 1 | 1 | 1 | 1 |
| correct_withheld | 0 | 0 | 0 | 0 |
| unscoreable_accepted | 2 | 0 | 2 | 0 |
| unscoreable_withheld | 0 | 2 | 0 | 2 |
| call_failed | 0 | 0 | 0 | 0 |
| all_parse_failed | 0 | 0 | 0 | 0 |
| checker_failed | 0 | 0 | 0 | 0 |
| ACCEPTED | 3 | 1 | 3 | 1 |
| REPAIRED | 0 | 0 | 0 | 0 |
| BLOCKED | 0 | 0 | 0 | 2 |
| UNCERTAIN | 0 | 2 | 0 | 0 |
| AMBIGUOUS | 0 | 0 | 0 | 0 |
| NOT_RUN | 0 | 0 | 0 | 0 |

Wrong-withheld uses scoreable wrong answers; correct-withheld uses scoreable correct answers.
Missing/unscoreable outputs, provider failures, unattempted questions and unevaluated checkpoints remain explicit.
NOT_RUN is not a rejection. Withheld includes non-ok evaluated results, including UNCERTAIN.
Unsupported answer grammar can withhold semantically correct answers; the broader grader is a separate bounded rule.
No retry recovery, independent B-versus-D algorithm, financial suitability or calibration claim is made.
