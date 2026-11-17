# Generated follow-up results

Status: **completed**.

Generated from saved records. This is a bounded synthetic study, not general numeric reliability.
The checker is frozen. Original development data, new authored candidates and model output are separate.

- Profile: gemma_harder; phase: main
- Mode: live
- Model configured: gemma3:12b; digest: f4031aab637d1ffa37b42570452ae0e4fad0314754d17ded67322e4b95836f8a
- Planned / attempted / failed model requests: 30 / 30 / 0
- Warm-ups: 0; retries: 0. Model replies are replayed across checkpoints.

## live

| Metric | check | validator | keyword evidence | numeric evidence |
|---|---:|---:|---:|---:|
| rows | 30 | 30 | 30 | 30 |
| evaluated | 30 | 30 | 30 | 30 |
| not_run | 0 | 0 | 0 | 0 |
| correct | 8 | 8 | 8 | 8 |
| wrong | 1 | 1 | 1 | 1 |
| unscoreable | 21 | 21 | 21 | 21 |
| no_answer | 0 | 0 | 0 | 0 |
| wrong_accepted | 1 | 0 | 1 | 0 |
| wrong_withheld | 0 | 1 | 0 | 1 |
| correct_accepted | 8 | 4 | 8 | 4 |
| correct_withheld | 0 | 4 | 0 | 4 |
| unscoreable_accepted | 21 | 0 | 18 | 0 |
| unscoreable_withheld | 0 | 21 | 3 | 21 |
| call_failed | 0 | 0 | 0 | 0 |
| all_parse_failed | 0 | 0 | 0 | 0 |
| checker_failed | 0 | 0 | 0 | 0 |
| ACCEPTED | 30 | 4 | 27 | 4 |
| REPAIRED | 0 | 0 | 0 | 0 |
| BLOCKED | 0 | 0 | 3 | 26 |
| UNCERTAIN | 0 | 26 | 0 | 0 |
| AMBIGUOUS | 0 | 0 | 0 | 0 |
| NOT_RUN | 0 | 0 | 0 | 0 |

Wrong-withheld uses scoreable wrong answers; correct-withheld uses scoreable correct answers.
Missing/unscoreable outputs, provider failures, unattempted questions and unevaluated checkpoints remain explicit.
NOT_RUN is not a rejection. Withheld includes non-ok evaluated results, including UNCERTAIN.
Unsupported answer grammar can withhold semantically correct answers; the broader grader is a separate bounded rule.
No retry recovery, independent B-versus-D algorithm, financial suitability or calibration claim is made.
