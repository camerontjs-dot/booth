"""Verify follow-up saved evidence offline. Never contacts a model.

PASS is complete saved-run consistency under the pinned rules. It is not
independent scientific qualification or external authenticity. INCOMPLETE and
FAIL return nonzero. Partial outputs and all failures remain unchanged.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import random

from runtime import ARMS, HERE, Blocked, cases_for, commit_matches, file_manifest, load_frozen, sha, utc, write_json
from verify_recorded import offline, parse_json


def load(path):
    return parse_json(Path(path).read_text(encoding="utf-8"))


def rows(path):
    return [parse_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def verify(run_dir):
    run = Path(run_dir).resolve()
    findings, count, incomplete = [], 0, False
    hashes = {}

    def check(name, ok):
        nonlocal count
        count += 1
        if not ok:
            findings.append(name)

    def read(name, jsonl=False):
        nonlocal incomplete
        path = run / name
        try:
            raw = path.read_bytes()
            hashes[name] = sha(raw)
            return rows(path) if jsonl else load(path)
        except (OSError, ValueError, UnicodeError, TypeError) as exc:
            incomplete = True
            findings.append(name + ": " + type(exc).__name__ + ": " + str(exc))
            return None

    manifest, completion = read("manifest.json"), read("completion.json")
    records, summary, checksums = read("records.jsonl", True), read("summary.json"), read("checksums.json")
    try:
        if not all(x is not None for x in (manifest, completion, records, summary, checksums)):
            raise Blocked("required evidence missing or malformed")
        check("schema2", manifest["schema"] == 2 and completion["schema"] == 2 and summary["schema"] == 2)
        if completion["status"] != "completed":
            incomplete = True
            findings.append("run did not complete; failure evidence retained")
        config = load(HERE / "RUNS.json")
        profile = config["profiles"][manifest["profile"]]
        phase = manifest["phase"]
        canonical_cases = cases_for(profile, phase)
        random.Random(config["settings"]["seed"]).shuffle(canonical_cases)
        check("case source/order", manifest["cases"] == canonical_cases)
        check("case IDs", manifest["case_order"] == [c["id"] for c in canonical_cases])
        check("unique case IDs", len({c["id"] for c in canonical_cases}) == len(canonical_cases))
        check("settings", manifest["settings"] == config["settings"])
        check("model declaration", (manifest["model"], manifest["digest"]) == (profile["model"], profile["digest"]))
        frozen, freeze_hash = file_manifest()
        check("frozen identity", manifest["freeze_sha256"] == freeze_hash and manifest["freeze"] == frozen)
        check("booth identity", manifest["booth_version"] == "0.5.9" and manifest["booth_core_sha256"] == frozen["booth_core_sha256"])
        check("checksum membership", set(checksums) == {p.name for p in run.iterdir() if p.is_file()} - {"checksums.json"})
        for name, expected in checksums.items():
            check("safe checksum filename: " + name, Path(name).name == name and name not in (".", ".."))
            if Path(name).name != name:
                continue
            path = run / name
            check("saved SHA: " + name, path.is_file() and sha(path.read_bytes()) == expected)
        by_id = {c["id"]: c for c in canonical_cases}
        mode = manifest["mode"]
        check("mode", mode in ("live", "offline_controls"))
        commit_matches(manifest["source_commit"], freeze_hash)
        check("committed source binding", True)
        expected_calls = len(canonical_cases) if mode == "live" else 0
        check("declared phase budget", profile["phase_calls"][phase] == len(canonical_cases))
        for key, expected in {
            "quantization": profile["quantization"], "host": config["host"],
            "case_set": profile["case_set"], "model_ready": profile["ready"],
            "repetitions": 1, "warmup_calls": 0, "replay_model_calls": 0,
            "configured_case_calls": len(canonical_cases), "planned_case_calls": expected_calls,
            "expected_total_model_calls": expected_calls,
            "status": "OWNER_APPROVED" if mode == "live" else "DESIGNED",
        }.items():
            check("manifest declaration " + key, manifest.get(key) == expected)
        unshuffled = cases_for(profile, phase)
        check("unshuffled case hash", manifest["unshuffled_cases_sha256"] == sha(json.dumps(unshuffled, ensure_ascii=False, sort_keys=True).encode()))
        check("complete run has no error", completion["error"] is None)
        if mode == "offline_controls":
            check("offline approval absent", manifest["approval_sha256"] is None and not (run / "approval.json").exists())
        else:
            approval = read("approval.json")
            if approval is None:
                raise Blocked("owner approval snapshot is missing or malformed")
            check("approval bytes/hash", hashes["approval.json"] == manifest["approval_sha256"])
            for key, expected in {
                "status": "OWNER_APPROVED", "owner": "Cameron", "run_id": manifest["run_id"],
                "profile": manifest["profile"], "freeze_sha256": freeze_hash,
                "source_commit": manifest["source_commit"], "model": profile["model"], "digest": profile["digest"],
            }.items():
                check("approval binding " + key, approval.get(key) == expected)
            check("approval call cap", approval["phase_call_limits"].get(phase) == expected_calls)
            check("approval instruction/time", isinstance(approval.get("owner_instruction"), str) and bool(approval["owner_instruction"].strip()) and bool(approval.get("approved_utc")))
        expected_rows = len(canonical_cases) * (2 if mode == "offline_controls" else 1)
        check("record count", len(records) == expected_rows and completion["records"] == len(records))
        expected_keys = [(c["id"], label) for c in canonical_cases for label in ("correct", "wrong")] if mode == "offline_controls" else [(c["id"], None) for c in canonical_cases]
        actual_keys = [(r["case_id"], r.get("control")) for r in records]
        check("record coverage/order", actual_keys == expected_keys)
        check("no duplicate records", len(set(actual_keys)) == len(actual_keys))

        with offline():
            frozen_runner = load_frozen()
            from study import checkpoints, execution_counts, render, summarize
            expected_execution = execution_counts(mode, len(canonical_cases), 0, 0, 0)
            traces = []
            if mode == "live":
                traces, intents = read("provider_calls.jsonl", True), read("request_intents.jsonl", True)
                before, after = read("model_before.json"), read("model_after.json")
                read("ollama_version.json")
                if traces is None or intents is None or before is None or after is None:
                    raise Blocked("live evidence incomplete")
                check("provider trace/intent count", len(traces) == len(intents) == len(canonical_cases))
                check("model before/after", before["digest"] == after["digest"] == profile["digest"] and before["name"] == after["name"] == profile["model"])
                check("provider order", [r["case_id"] for r in traces] == manifest["case_order"])
                check("intent order", [r["case_id"] for r in intents] == manifest["case_order"])
                expected_execution = execution_counts(mode, len(canonical_cases), len(traces),
                                                      sum(not r.get("error") for r in traces),
                                                      sum(bool(r.get("error")) for r in traces))
                for index, trace in enumerate(traces):
                    intent = intents[index]
                    wire = base64.b64decode(trace["response_base64"], validate=True)
                    check("raw bytes SHA " + str(index), sha(wire) == trace["response_sha256"])
                    check("raw bytes/text " + str(index), wire.decode("utf-8") == trace["response_text"])
                    response = parse_json(wire.decode("utf-8"))
                    check("raw reply " + str(index), response["response"] == trace["raw_reply"])
                    check("trace/raw status " + str(index), trace.get("done") == response.get("done") and trace.get("done_reason") == response.get("done_reason"))
                    check("completed provider reply " + str(index), trace.get("error") is None and response.get("done") is True and response.get("done_reason") != "length")
                    check("request SHA " + str(index), sha(trace["request_text"].encode()) == trace["request_sha256"])
                    check("intent/request " + str(index), intent["request_text"] == trace["request_text"] and intent["request_sha256"] == trace["request_sha256"] and intent["intent_index"] == index)
                    request = parse_json(trace["request_text"])
                    case = by_id[trace["case_id"]]
                    settings = config["settings"]
                    expected_request = {
                        "model": profile["model"], "prompt": frozen_runner.prompt_for(case) + frozen_runner.booth.core._CONFIDENCE_SUFFIX,
                        "stream": False, "keep_alive": "5m",
                        "options": {k: settings[k] for k in ("temperature", "seed", "num_predict", "num_ctx")},
                    }
                    check("exact request " + str(index), request == expected_request)
                    check("elapsed " + str(index), isinstance(trace["elapsed_s"], (float, int)) and trace["elapsed_s"] >= 0)
            else:
                check("offline has no provider traces", not (run / "provider_calls.jsonl").exists() and not (run / "request_intents.jsonl").exists())
            for index, row in enumerate(records):
                case = by_id[row["case_id"]]
                if mode == "offline_controls":
                    label = row["control"]
                    raw = json.dumps({"ambiguous": False, "interpretations": [], "chosen_interpretation": None,
                                      "answer": case["correct_answer" if label == "correct" else "wrong_answer"], "confidence": 0.99})
                    check("authored payload " + str(index), row["fixture_reply"] == raw)
                    check("control label " + str(index), row["grade"]["label"] == label)
                    check("offline layer " + str(index), row["layer"] == ("independent_authored_candidates" if profile["case_set"] == "harder" else "original_development_controls"))
                else:
                    trace = traces[index]
                    raw = trace["raw_reply"]
                    check("trace reference " + str(index), row["provider_trace_index"] == index and row["provider_calls"] == 1)
                    check("live layer " + str(index), row["layer"] == "live" and row.get("provider_error") is None)
                reconstructed = checkpoints(case, raw, profile["case_set"], frozen_runner)
                for key in ("case_id", "category", "answer", "grade", "original_bounded_grade", "numeric_rule", "frozen_grammar_support"):
                    check("recomputed " + key + " " + str(index), row[key] == reconstructed[key])
                # Replay duration/timestamps are expected to vary; result semantics must not.
                def stable(value):
                    if isinstance(value, dict):
                        return {k: stable(v) for k, v in value.items() if k not in ("latency_s", "elapsed_s", "duration_s")}
                    if isinstance(value, list):
                        return [stable(v) for v in value]
                    return value
                check("replayed checkpoint decisions " + str(index), stable(row["arms"]) == stable(reconstructed["arms"]))
            check("execution counts", summary["execution"] == expected_execution)
            for key, value in expected_execution.items():
                check("completion " + key, completion[key] == value)
            rebuilt = summarize(records, expected_execution)
            check("reconstructed summary", summary == rebuilt)
            check("generated Markdown", (run / "summary.md").read_text(encoding="utf-8") == render(rebuilt, manifest, completion))
    except (Exception, KeyboardInterrupt) as exc:
        incomplete = True
        findings.append(type(exc).__name__ + ": " + str(exc))
    return {"schema": 1, "verified_utc": utc(),
            "status": "INCOMPLETE" if incomplete else ("FAIL" if findings else "PASS"),
            "scientific_qualification": False, "network_and_model_calls": 0,
            "checks": {"total": count, "failed": len(findings)}, "findings": findings,
            "evidence_sha256": hashes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--receipt")
    args = parser.parse_args(argv)
    result = verify(args.run_dir)
    if args.receipt:
        receipt = Path(args.receipt).resolve()
        run = Path(args.run_dir).resolve()
        if receipt == run or run in receipt.parents:
            parser.error("receipt must be outside the audited evidence directory")
        write_json(receipt, result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
