"""Prepare, exercise offline controls, or explicitly authorize a numeric follow-up.

Default: print the plan, with zero network/model calls.
  python followup/study.py plan
  python followup/study.py controls --out /fresh/offline-output
  python followup/study.py run --phase smoke --run-id owner-chosen-id \
      --approval /owner/approval.json --allow-model-calls --out /fresh/smoke

Main additionally requires --smoke-run /completed/verified/smoke.
No warm-ups, retries, automatic model downloads, resume or automatic publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import random
import sys
import time

from runtime import (
    ARMS, HERE, EXAMPLE, Blocked, append_jsonl, authorize, cases_for,
    file_manifest, load_frozen, plan, read_json, sha, utc, write_json,
)


def grade(case, answer, case_set, frozen):
    if case_set == "original":
        return frozen.grade_answer(case, answer)
    from followup_grade import grade_answer
    return grade_answer(case, answer)


def checkpoints(case, raw, case_set, frozen, first=None, provider_prompt=None):
    row = frozen.checkpoints(case, raw, first, provider_prompt)
    row["original_bounded_grade"] = row["grade"]
    row["grade"] = grade(case, row["answer"], case_set, frozen)
    source_values = [line.partition(":")[2].strip() for line in case["source"].splitlines()
                     if line.partition(":")[1] and line.partition(":")[0].strip().casefold() == case["target"].casefold()]
    support = {"target_fields": len(source_values)}
    for key, value in (("source_quantity", source_values[0] if len(source_values) == 1 else None),
                       ("answer_quantity", row["answer"])):
        try:
            frozen.parse_quantity(value)
            support[key] = {"supported": True, "reason": None}
        except (ValueError, TypeError) as exc:
            support[key] = {"supported": False, "reason": str(exc)}
    row["frozen_grammar_support"] = support
    return row


def stopped_row(case, first, case_set, frozen):
    skipped = {
        "ok": False, "status": "NOT_RUN", "call_failed": False,
        "all_parse_failed": False, "checker_failed": False,
        "reason": "provider_failure", "detail": "No completed provider reply to replay",
    }
    return {
        "case_id": case["id"], "category": case["category"], "answer": first.answer,
        "grade": grade(case, first.answer, case_set, frozen),
        "original_bounded_grade": frozen.grade_answer(case, first.answer),
        "numeric_rule": {"passed": False, "reason": "NOT_RUN: provider failure"},
        "arms": {arm: first.to_dict() if arm == "check" else dict(skipped) for arm in ARMS},
    }


def summarize(records, execution):
    from collections import Counter
    layers = {}
    for layer in sorted({r["layer"] for r in records}):
        rows = [r for r in records if r["layer"] == layer]
        arms = {}
        for arm in ARMS:
            counts, statuses = Counter(), Counter()
            for row in rows:
                result, label = row["arms"][arm], row["grade"]["label"]
                counts["rows"] += 1
                counts[label] += 1
                if result["status"] == "NOT_RUN":
                    counts["not_run"] += 1
                else:
                    counts["evaluated"] += 1
                    counts[label + ("_accepted" if result["ok"] else "_withheld")] += 1
                statuses[result["status"]] += 1
                for key in ("call_failed", "all_parse_failed", "checker_failed"):
                    counts[key] += bool(result.get(key, False))
            keys = ("rows", "evaluated", "not_run", "correct", "wrong", "unscoreable", "no_answer",
                    "correct_accepted", "correct_withheld", "wrong_accepted", "wrong_withheld",
                    "unscoreable_accepted", "unscoreable_withheld", "no_answer_accepted", "no_answer_withheld",
                    "call_failed", "all_parse_failed", "checker_failed")
            arms[arm] = {k: counts[k] for k in keys}
            arms[arm]["statuses"] = dict(sorted(statuses.items()))
        layers[layer] = {"rows": len(rows), "arms": arms}
    return {"schema": 2, "execution": execution, "layers": layers}


def render(summary, manifest, completion):
    lines = ["# Generated follow-up results", "", "Status: **" + completion["status"] + "**.", "",
             "Generated from saved records. This is a bounded synthetic study, not general numeric reliability.",
             "The checker is frozen. Original development data, new authored candidates and model output are separate.",
             "", "- Profile: " + manifest["profile"] + "; phase: " + manifest["phase"],
             "- Mode: " + manifest["mode"],
             "- Model configured: " + manifest["model"] + "; digest: " + str(manifest["digest"]),
             "- Planned / attempted / failed model requests: " +
             " / ".join(str(summary["execution"][k]) for k in ("planned_case_calls", "attempted_case_calls", "failed_case_calls")),
             "- Warm-ups: 0; retries: 0. Model replies are replayed across checkpoints.", ""]
    if manifest["mode"] == "offline_controls":
        lines += ["**These are authored answer candidates, not model outputs. No model was invoked.**", ""]
    for layer, item in summary["layers"].items():
        lines += ["## " + layer, "", "| Metric | check | validator | keyword evidence | numeric evidence |",
                  "|---|---:|---:|---:|---:|"]
        for key in ("rows", "evaluated", "not_run", "correct", "wrong", "unscoreable", "no_answer",
                    "wrong_accepted", "wrong_withheld", "correct_accepted", "correct_withheld",
                    "unscoreable_accepted", "unscoreable_withheld", "call_failed", "all_parse_failed", "checker_failed"):
            lines.append("| " + key + " | " + " | ".join(str(item["arms"][a][key]) for a in ARMS) + " |")
        for status in ("ACCEPTED", "REPAIRED", "BLOCKED", "UNCERTAIN", "AMBIGUOUS", "NOT_RUN"):
            lines.append("| " + status + " | " + " | ".join(str(item["arms"][a]["statuses"].get(status, 0)) for a in ARMS) + " |")
        lines.append("")
    lines += ["Wrong-withheld uses scoreable wrong answers; correct-withheld uses scoreable correct answers.",
              "Missing/unscoreable outputs, provider failures, unattempted questions and unevaluated checkpoints remain explicit.",
              "NOT_RUN is not a rejection. Withheld includes non-ok evaluated results, including UNCERTAIN.",
              "Unsupported answer grammar can withhold semantically correct answers; the broader grader is a separate bounded rule.",
              "No retry recovery, independent B-versus-D algorithm, financial suitability or calibration claim is made.", ""]
    return "\n".join(lines)


def execution_counts(mode, planned, attempted, successful, failed):
    return {"planned_case_calls": planned if mode == "live" else 0,
            "attempted_case_calls": attempted, "successful_case_calls": successful,
            "failed_case_calls": failed, "not_attempted_case_calls": (planned - attempted) if mode == "live" else 0,
            "warmup_calls": 0, "replay_model_calls": 0}


def save_outputs(out, manifest, records, execution, status, elapsed, error=None):
    completion = {
        "schema": 2, "status": status, "finished_utc": utc(), "elapsed_s": elapsed,
        **execution, "records": len(records), "error": error,
    }
    summary = summarize(records, execution)
    write_json(out / "completion.json", completion)
    write_json(out / "summary.json", summary)
    (out / "summary.md").write_text(render(summary, manifest, completion), encoding="utf-8")
    write_json(out / "checksums.json", {
        p.name: sha(p.read_bytes()) for p in sorted(out.iterdir()) if p.is_file()
    })
    return completion


def run(args):
    declaration = plan(args.profile, args.phase)
    config = read_json(HERE / "RUNS.json")
    profile = config["profiles"][args.profile]
    out = Path(args.out).resolve()
    if out.exists():
        raise Blocked("output directory already exists; no overwrite or resume")
    frozen = load_frozen()
    permit = None
    mode = "offline_controls" if args.command == "controls" else "live"
    if mode == "live":
        permit = authorize(declaration, args.approval, args.allow_model_calls,
                           args.run_id, out, args.smoke_run)
    cases = cases_for(profile, args.phase)
    random.Random(config["settings"]["seed"]).shuffle(cases)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {
        **declaration, "status": "DESIGNED" if mode == "offline_controls" else "OWNER_APPROVED",
        "schema": 2, "mode": mode, "run_id": args.run_id if mode == "live" else out.name,
        "started_utc": utc(), "cases": cases, "case_order": [c["id"] for c in cases],
        "booth_version": frozen.booth.__version__,
        "booth_core_sha256": sha(Path(frozen.booth.core.__file__).read_bytes()),
        "python": platform.python_version(), "os": platform.platform(),
        "hardware": frozen.hardware(), "freeze": read_json(HERE / "freeze.json"),
        "configured_case_calls": len(cases), "planned_case_calls": len(cases) if mode == "live" else 0,
        "expected_total_model_calls": len(cases) if mode == "live" else 0,
        "approval_sha256": sha(Path(args.approval).read_bytes()) if mode == "live" else None,
        "non_claims": ["new controls are authored, not model output", "same frozen numeric rule in B and D",
                       "broader reference grading is bounded", "no retry repair", "no blind scientific qualification"],
    }
    write_json(out / "manifest.json", manifest)
    if mode == "live":
        with (out / "approval.json").open("xb") as stream:
            stream.write(Path(args.approval).read_bytes())
    started = time.monotonic()
    records, successful, failed, attempted = [], 0, 0, 0
    provider = None
    status, error = "completed", None
    try:
        if mode == "offline_controls":
            for case in cases:
                for field, label in (("correct_answer", "correct"), ("wrong_answer", "wrong")):
                    raw = json.dumps({"ambiguous": False, "interpretations": [], "chosen_interpretation": None,
                                      "answer": case[field], "confidence": 0.99})
                    row = checkpoints(case, raw, profile["case_set"], frozen)
                    row.update(layer="independent_authored_candidates" if profile["case_set"] == "harder" else "original_development_controls",
                               control=label, fixture_reply=raw, provider_calls=0)
                    append_jsonl(out / "records.jsonl", row)
                    records.append(row)
                    if row["grade"]["label"] != label:
                        raise Blocked("authored candidate disagrees with the declared reference: " + case["id"])
        else:
            before = frozen.model_identity(config["host"], profile["model"])
            if before["digest"] != profile["digest"]:
                raise Blocked("installed model digest differs from pinned/approved identity")
            # Manifest was saved before any network; save additional metadata separately.
            write_json(out / "model_before.json", before)
            write_json(out / "ollama_version.json", frozen.get_json(config["host"], "version"))
            options = {k: config["settings"][k] for k in ("temperature", "seed", "num_predict", "num_ctx")}

            class GuardedProvider(frozen.Provider):
                def __call__(self, prompt):
                    self.last = None
                    permit.before_call()
                    payload = {"model": self.model, "prompt": prompt, "stream": False,
                               "keep_alive": "5m", "options": self.options}
                    request_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    append_jsonl(self.out / "request_intents.jsonl", {
                        "case_id": self.case_id, "intent_index": permit.attempted - 1, "utc": utc(),
                        "request_text": request_text, "request_sha256": sha(request_text.encode()),
                    })
                    return super().__call__(prompt)

            provider = GuardedProvider(config["host"], profile["model"], options, config["settings"]["timeout_s"], out)
            for case in cases:
                provider.case_id = case["id"]
                prior_calls = provider.calls
                first = frozen.booth.check(provider, frozen.prompt_for(case), threshold=0.7, max_retries=0)
                attempted = provider.calls
                dispatched = provider.calls - prior_calls
                if first.call_failed or dispatched != 1 or provider.last is None or provider.last.get("error") or provider.last.get("case_id") != case["id"]:
                    failed += 1
                    row = stopped_row(case, first, profile["case_set"], frozen)
                    row.update(layer="live", provider_calls=dispatched,
                               provider_trace_index=provider.calls - 1 if dispatched == 1 and provider.last is not None else None,
                               provider_error=provider.last.get("error") if provider.last else "execution gate or request-intent recording failed before HTTP dispatch")
                    append_jsonl(out / "records.jsonl", row)
                    records.append(row)
                    raise Blocked("provider failed; partial evidence preserved for " + case["id"])
                successful += 1
                row = checkpoints(case, provider.last["raw_reply"], profile["case_set"], frozen, first,
                                  json.loads(provider.last["request_text"])["prompt"])
                row.update(layer="live", provider_calls=1, provider_trace_index=provider.calls - 1, provider_error=None)
                append_jsonl(out / "records.jsonl", row)
                records.append(row)
                print(json.dumps({"case_completed": case["id"], "completed": successful, "planned": len(cases)}), flush=True)
            after = frozen.model_identity(config["host"], profile["model"])
            write_json(out / "model_after.json", after)
            if after["digest"] != profile["digest"]:
                raise Blocked("model identity drifted during execution")
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit, Exception)):
            status, error = "blocked", type(exc).__name__ + ": " + str(exc)
        else:
            raise
        if provider is not None:
            attempted = provider.calls
        write_json(out / "failure.json", {"status": "blocked", "utc": utc(), "error": error,
                                         "model_requests_attempted": attempted,
                                         "intent_count": permit.attempted if permit else 0,
                                         "note": "No resume. Preserve this directory and authorize a new run identity."})
    failed = max(0, attempted - successful)
    execution = execution_counts(mode, len(cases), attempted, successful, failed)
    completion = save_outputs(out, manifest, records, execution, status, time.monotonic() - started, error)
    print(json.dumps({"status": completion["status"], "output": str(out),
                      "model_requests_attempted": attempted, "new_model_calls_in_replay": 0}), flush=True)
    return 0 if status == "completed" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("plan", "controls", "run"), default="plan")
    parser.add_argument("--profile", default="gemma_harder")
    parser.add_argument("--phase", choices=("smoke", "main"), default="main")
    parser.add_argument("--out")
    parser.add_argument("--run-id")
    parser.add_argument("--approval")
    parser.add_argument("--allow-model-calls", action="store_true")
    parser.add_argument("--smoke-run")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            print(json.dumps(plan(args.profile, args.phase), indent=2))
            return 0
        if not args.out:
            raise Blocked("--out must name a fresh output directory")
        return run(args)
    except (Blocked, ValueError, OSError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED_BEFORE_MODEL_CALLS", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
