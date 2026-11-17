# Follow-up protocol: fresh cases, unchanged checker

## Authority and boundary

The maintainer invited harder cases with wider answer grammar in issue #36, comment 6936276229.
The independent-case method and portable verifier are proposed implementation choices.
Private preparation does not claim upstream scope approval, publication, acceptance or model execution.
This protocol governs only this example's follow-up; it changes no BOOTH core, dependencies or other examples.

The original `run_example.py`, `grade_answers.py`, `cases.json`, `PROTOCOL.md`, tests, report and recorded evidence are byte-pinned in `freeze.json`.
Original evidence remains in the parent `recorded/` folder and the preserved original run directories.
This directory owns new apparatus. New evidence always goes to fresh directories outside the historical study.
Once inference begins, any apparatus, case, grader or protocol change requires a successor candidate and run; failed runs are never repaired in place.

## Question

How do the four existing checkpoints respond to independently authored harder numeric cases and broader source/answer formats when their numeric rule stays unchanged?

The 30 main cases and three smoke cases were authored by a separate Codex agent without reading the checker, original cases, grader or results.
The author received the task and a declared data interface. A source-layout correction placed facts on separate labelled lines before any checker outcomes were observed.
References, numeric values, questions, answer controls and grammar choices were unchanged by that correction.
Full authorship and version history are preserved locally; CASE_PROVENANCE.json records the public lineage.
This is synthetic restricted-aperture authorship, not blind scientific qualification or a human-independent benchmark.

## Layers and scope

1. Original development controls and saved live run: unchanged historical evidence, verified separately.
2. New authored candidates: one declared correct and wrong answer for each case; confidence 0.99 and ambiguous=false are fixtures, not measured confidence.
3. New live model answers: one BOOTH-default-prompt request per question, no retries. B replays A's exact raw reply. C and D assess A's parsed answer.
4. Optional smaller-model original-case repeat: separate configuration, denominators and report. It is not automatically part of layer 3.

Never pool these layers. Smoke IDs do not occur in main.
The positive/wrong authored candidates test checkpoint decisions, not model accuracy or calibration.
Cases include supported anchors, wrong-field/unit traps and formats outside the frozen rule.
The application still supplies the requested field label and rounding metadata.
The rule is not expanded to understand new units, language or formats. Unsupported inputs and correct answers withheld are findings.

## Grading and recorded diagnostics

The new reference grader consults only each declared final reference quantity.
It uses exact rational arithmetic and an anchored broader syntax, documented in followup_grade.py.
It supports selected wrappers, exponent notation, explicit rational fractions, currency scale abbreviations, named currencies and specified Unicode normalization.
It rejects ambiguous/multiple quantities, unsupported prose, absent units, malformed grouping and non-finite values.
Candidate values are never rounded. Explicit money half-up rounding is already represented by the declared reference.
This broader grader is distinct from the frozen comparator; the old bounded grade is retained only as a diagnostic and may be unscoreable under the new reference schema.

Each answer records whether its source quantity and answer quantity fit the frozen parser's grammar.
These scope diagnostics accompany every evaluated case. The outcomes are not retuned away.
Generated accuracy, acceptance/withholding and support limitations are different questions.

## Frozen primary matrix and budget

- Local Ollama gemma3:12b, Q4_K_M.
- Required digest: f4031aab637d1ffa37b42570452ae0e4fad0314754d17ded67322e4b95836f8a.
- BOOTH 0.5.9, pinned core bytes and original numeric rule.
- Temperature 0; seed 42; num_predict 1024; num_ctx 4096; per-call timeout 300 seconds.
- One repetition, deterministic random.Random(42) case shuffle per phase.
- Three separate smoke questions, then 30 main questions; **33 model requests maximum**.
- Zero warm-ups, zero retries, zero new calls for replayed B/C/D.
- No parallel model calls or resume. Any provider/incomplete-generation failure stops and preserves a partial run.
- Exact request text, durable pre-call intent, raw provider text, HTTP bytes/base64/SHA, status, parsed answers, reasons and timings are retained before reporting.

The main phase requires a complete matching smoke run with passing offline consistency checks.
Smoke success concerns infrastructure and evidence integrity, not numeric accuracy or favorable results.
A transport failure or token-limit abort gets a fresh run identity if retried; its evidence is preserved.
The optional Qwen profile proposes three original smoke plus 20 original main questions (23 requests), but is not installed/pinned and remains blocked.
Its model installation/pinning and any inference require a separate decision and successor freeze.

## Approval and execution gate

No experimental model calls are authorized by this preparation.
Planning, offline authored candidates, saved-evidence replay and normal tests make no model calls.
Only `run` with `--allow-model-calls` and a matching owner approval record can start local inference.
The record must name Cameron, the exact source commit/freeze hash, model/digest, profile, run ID, explicit owner instruction, time and exact phase call limits.
Each phase is create-only claimed next to that approval; call intents are durable and capped.
The recorded commit must contain every frozen source blob. Before each dispatch, the permit rechecks the approved commit, freeze hash, approval bytes and installed BOOTH core.
Main smoke evidence must belong to the same run ID and exact approval record. The raw approval snapshot is retained with live evidence.
Only the declared local endpoint is supported. No hosted inference, embeddings, downloads or publication is hidden in the runner.
The gate is an explicit workflow control, not identity authentication.

## Counts, failures and reporting

For every layer and arm report record count, evaluated/NOT_RUN counts, correct/wrong/unscoreable/missing, accepted/withheld, statuses, call failures, parse failures and checker failures.
Wrong-withheld and correct-withheld denominators are scoreable wrong and correct answers, respectively.
Unscoreable/missing answers remain explicit in the full record denominator.
For live runs report planned, attempted, successful, failed and not-attempted model requests.
NOT_RUN is never counted as a successful rejection.
A provider failure retains its failed A result; B/C/D are NOT_RUN rather than pretending an incomplete answer was replayed.
Partial/failed runs cannot receive a complete verifier PASS.

Generated summaries derive only from saved records and execution counts.
No live result exists until authorized execution occurs.
Before any publication, inspect raw replies, failure records, independent grading, statuses, support diagnostics and reconstructed reports with Cameron.
Do not infer retry repair, independent B/D algorithm replication, financial/compliance suitability, reliability across models or generalization.

## Verification and update discipline

Run the frozen BOOTH/example suite and new tests offline. Verify original evidence with verify_recorded.py and new evidence with verify_followup.py.
Test gate denial, budget caps, identity drift, create-only phase/output claims, corrupt/resealed records, missing evidence, timeouts, invalid UTF-8, partial HTTP bytes and unparseable replies.
These failure-path fixtures are unit evidence, not live operational or model evidence.
Portable verification establishes saved-run consistency, not external authenticity.
Source/config/protocol/case hashes are frozen before inference; any change after inference gets a successor rather than modifying prior evidence.

