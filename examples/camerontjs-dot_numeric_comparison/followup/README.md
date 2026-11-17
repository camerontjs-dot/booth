# Frozen-checker numeric follow-up

This prepares the harder-case follow-up invited in [issue #36](https://github.com/Vedantgitbot/booth/issues/36#issuecomment-6936276229).
It adds 30 fresh cases and three disjoint smoke cases, a broader reference grader, explicit inference gating, and offline saved-result verification.
No new experimental model output is included. The portable verifier is an optional contribution proposal.

The original checker, cases, report and raw replies in the parent folder are unchanged.
New source and outputs are separate. The checker is tested as it stands, including unsupported formats.
The numeric validator and numeric evidence arm still share one rule.

## What is ready

- `challenge_cases.json`: independently authored from the checker implementation by a separate Codex agent under a restricted information aperture.
- `CASE_PROVENANCE.json`: hashes, authorship limits and the pre-observation source-layout correction.
- `followup_grade.py`: declared, exact-rational broader grammar; never reads source facts or the numeric checker.
- `RUNS.json`, `PROTOCOL.md` and `freeze.json`: pinned configuration, denominators, source hashes and call budgets.
- `study.py`: offline planning/controls by default; a live run requires an execution flag and a matching explicit owner approval.
- `verify_recorded.py`: portable verification of the original saved study, adapted from its separate audit script.
- `verify_followup.py`: offline consistency checks for new saved runs, including partial/failure disposition.

These are separate-agent authored synthetic cases, not human-independent or blind scientific qualification.
Source facts were laid out as labelled lines after a parent interface clarification, before checker decisions were observed.
The first version and all authoring corrections are retained locally. Values, references, questions and controls did not change in that layout correction.

## Prepare without invoking a model

From the repository root, use a clean Python 3.9+ environment with the checkout installed:

```bash
python -m pip install -e '.[dev]'
python examples/camerontjs-dot_numeric_comparison/followup/study.py plan
python examples/camerontjs-dot_numeric_comparison/followup/study.py controls --out /absolute/fresh/offline-controls
python examples/camerontjs-dot_numeric_comparison/followup/verify_followup.py --run-dir /absolute/fresh/offline-controls
python examples/camerontjs-dot_numeric_comparison/followup/verify_recorded.py --run-dir examples/camerontjs-dot_numeric_comparison/recorded
python -m pytest tests examples/camerontjs-dot_numeric_comparison/test_example.py examples/camerontjs-dot_numeric_comparison/test_grading.py examples/camerontjs-dot_numeric_comparison/followup
```

The follow-up tests forbid network connections, including the tests of the opt-in gate.
Test HTTP replies are explicit unit fixtures, not experimental model observations.
The verifier writes no input files; optional `--receipt` must name a new file outside the evidence directory.
It returns nonzero on corrupt, missing, malformed or incomplete evidence.
Follow-up source-commit verification needs a Git clone containing the recorded candidate commit; it checks every frozen source blob against that commit.

## Live execution needs a separate owner go-ahead

Proposed primary matrix: `gemma_harder`, three smoke requests followed by 30 main requests.
There are zero warm-ups, retries or additional model calls for the replay arms: **33 requests maximum**.
Main requires the completed matching smoke run to pass offline consistency checks.
Model accuracy or false-withholding outcomes do not decide whether a smoke run passes infrastructure verification.

A future approved smoke command is:

```bash
python examples/camerontjs-dot_numeric_comparison/followup/study.py run --profile gemma_harder --phase smoke --run-id owner-approved-id --approval /absolute/owner-approval.json --allow-model-calls --out /absolute/fresh/smoke
```

Main uses the same approval/run ID, `--phase main`, a new output directory and `--smoke-run /absolute/fresh/smoke`.
Each phase is claimed once next to the approval file. Reusing a phase, exceeding its call cap, editing pinned files or changing the model digest blocks execution.
The approved source commit, freeze hash, approval bytes and installed BOOTH core are rechecked before every dispatch. The run retains an exact approval snapshot.
Interrupted/failed attempts are retained; a new attempt needs a new run identity and owner authorization.
The approval record prevents accidental execution; it does not authenticate a person or replace their explicit instruction.

The optional `qwen_original_optional` profile is a separate repeat of the original 20 cases.
It is unavailable until an exact installed model digest is pinned in a successor configuration; it is not included in the 33-request primary budget.
No model download, claim, push, PR or public post is automatic.

