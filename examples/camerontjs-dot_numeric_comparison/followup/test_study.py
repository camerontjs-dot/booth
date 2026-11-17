"""Deterministic gate/failure tests. Fake HTTP replies are unit fixtures only."""
import base64
import http.client
import json
from pathlib import Path
import shutil
import urllib.error
import urllib.request

import pytest

import runtime
import study
from verify_followup import verify


def approve(tmp_path, **changes):
    declaration = runtime.plan("gemma_harder", "smoke")
    value = {
        "status": "OWNER_APPROVED", "owner": "Cameron", "run_id": "unit-fixture",
        "profile": "gemma_harder", "freeze_sha256": declaration["freeze_sha256"],
        "source_commit": declaration["source_commit"], "model": declaration["model"],
        "digest": declaration["digest"], "approved_utc": "2000-01-01T00:00:00+00:00",
        "owner_instruction": "Synthetic unit test only; all HTTP is faked and network is forbidden",
        "phase_call_limits": {"smoke": 3, "main": 30},
    }
    value.update(changes)
    path = tmp_path / "unit-fixture-approval.json"
    runtime.write_json(path, value)
    return path


def args(approval, out, **changes):
    value = dict(command="run", profile="gemma_harder", phase="smoke", out=str(out),
                 run_id="unit-fixture", approval=str(approval), allow_model_calls=True, smoke_run=None)
    value.update(changes)
    from argparse import Namespace
    return Namespace(**value)


class Response:
    def __init__(self, body=None, partial=False):
        self.body, self.partial = body, partial

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def read(self):
        if self.partial:
            raise http.client.IncompleteRead(self.body, 50)
        return self.body


def fake_http(monkeypatch, mode="correct", wrong_digest=False):
    calls = []
    config = runtime.read_json(runtime.HERE / "RUNS.json")
    profile = config["profiles"]["gemma_harder"]
    cases = runtime.cases_for(profile, "smoke")
    by_prompt = {study.load_frozen().prompt_for(c): c for c in cases}
    suffix = study.load_frozen().booth.core._CONFIDENCE_SUFFIX

    def fake(request, timeout=None):
        if isinstance(request, str):
            if request.endswith("/api/tags"):
                model = {"name": profile["model"], "digest": "wrong" if wrong_digest else profile["digest"], "size": 1, "details": {}}
                return Response(json.dumps({"models": [model]}).encode())
            if request.endswith("/api/version"):
                return Response(b'{"version":"unit-fixture"}')
            raise AssertionError("Unexpected metadata endpoint: " + request)
        payload = json.loads(request.data)
        calls.append(payload)
        if mode == "timeout":
            raise urllib.error.URLError("unit-fixture timeout")
        if mode == "invalid_utf8":
            return Response(b"\xff")
        if mode == "partial":
            return Response(b'{"response":"unit-fixture', partial=True)
        assert payload["prompt"].endswith(suffix)
        case = by_prompt[payload["prompt"][:-len(suffix)]]
        answer = case["correct_answer"]
        raw = "not JSON" if mode == "unparseable" else json.dumps({
            "ambiguous": False, "interpretations": [], "chosen_interpretation": None,
            "answer": answer, "confidence": 1.0,
        })
        return Response(json.dumps({"response": raw, "done": True, "done_reason": "stop"}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls


def test_default_plan_and_missing_optin_never_touch_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No HTTP even for metadata without owner opt-in")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    assert study.main([]) == 0
    assert study.main(["run", "--phase", "smoke", "--out", str(tmp_path / "no-run")]) == 2
    assert not (tmp_path / "no-run").exists()


@pytest.mark.parametrize("change", [
    {"status": "NOT_AUTHORIZED"}, {"owner": "someone"}, {"run_id": "different"},
    {"profile": "qwen_original_optional"}, {"freeze_sha256": "wrong"},
    {"source_commit": "wrong"}, {"digest": "wrong"}, {"model": "wrong"},
    {"phase_call_limits": {"smoke": 4}}, {"approved_utc": None},
    {"owner_instruction": None},
])
def test_mismatched_approval_blocks_before_http(tmp_path, monkeypatch, change):
    approval = approve(tmp_path, **change)
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid approval must block HTTP")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    with pytest.raises(runtime.Blocked):
        study.run(args(approval, tmp_path / "not-created"))
    assert not (tmp_path / "not-created").exists()


def test_optin_flag_is_separate_from_valid_fixture_approval(tmp_path):
    approval = approve(tmp_path)
    with pytest.raises(runtime.Blocked, match="disabled"):
        study.run(args(approval, tmp_path / "never", allow_model_calls=False))


def test_call_budget_and_phase_claim_are_hard_caps(tmp_path):
    approval = approve(tmp_path)
    declaration = runtime.plan("gemma_harder", "smoke")
    permit = runtime.authorize(declaration, approval, True, "unit-fixture", tmp_path / "fresh")
    for _ in range(3):
        permit.before_call()
    with pytest.raises(runtime.Blocked, match="exhausted"):
        permit.before_call()
    assert permit.attempted == 3
    with pytest.raises(runtime.Blocked, match="already claimed"):
        runtime.authorize(declaration, approval, True, "unit-fixture", tmp_path / "another-fresh")


def test_optional_unpinned_model_cannot_be_approved(tmp_path):
    declaration = runtime.plan("qwen_original_optional", "smoke")
    approval = approve(tmp_path, profile="qwen_original_optional", model=declaration["model"], digest=None)
    with pytest.raises(runtime.Blocked, match="not pinned"):
        runtime.authorize(declaration, approval, True, "unit-fixture", tmp_path / "never")


def test_main_requires_passing_matching_smoke(tmp_path):
    approval = approve(tmp_path)
    with pytest.raises(runtime.Blocked, match="smoke"):
        study.run(args(approval, tmp_path / "never", phase="main"))


def test_offline_candidates_preserve_controls_and_verify(tmp_path):
    out = tmp_path / "controls"
    assert study.main(["controls", "--phase", "smoke", "--out", str(out)]) == 0
    completion = runtime.read_json(out / "completion.json")
    assert completion["attempted_case_calls"] == 0
    assert completion["records"] == 6
    receipt = verify(out)
    assert receipt["status"] == "PASS", receipt


@pytest.mark.parametrize("mode", ["correct", "unparseable"])
def test_fake_completed_smoke_is_replayed_and_verified(tmp_path, monkeypatch, mode):
    approval, out = approve(tmp_path), tmp_path / "synthetic-smoke"
    calls = fake_http(monkeypatch, mode)
    assert study.run(args(approval, out)) == 0
    assert len(calls) == 3
    completion = runtime.read_json(out / "completion.json")
    assert completion["attempted_case_calls"] == 3 and completion["warmup_calls"] == 0
    receipt = verify(out)
    assert receipt["status"] == "PASS", receipt
    if mode == "unparseable":
        summary = runtime.read_json(out / "summary.json")
        assert summary["layers"]["live"]["arms"]["check"]["all_parse_failed"] == 3
        assert summary["layers"]["live"]["arms"]["check"]["no_answer"] == 3


@pytest.mark.parametrize("mode", ["timeout", "invalid_utf8", "partial"])
def test_provider_failures_preserve_bytes_rows_and_denominators(tmp_path, monkeypatch, mode):
    approval, out = approve(tmp_path), tmp_path / "failed-unit-fixture"
    calls = fake_http(monkeypatch, mode)
    assert study.run(args(approval, out)) == 2
    assert len(calls) == 1
    completion = runtime.read_json(out / "completion.json")
    assert completion["status"] == "blocked"
    assert completion["attempted_case_calls"] == completion["failed_case_calls"] == 1
    assert completion["not_attempted_case_calls"] == 2
    assert (out / "failure.json").is_file()
    trace = runtime.read_jsonl(out / "provider_calls.jsonl")[0]
    if mode == "invalid_utf8":
        assert base64.b64decode(trace["response_base64"]) == b"\xff"
    if mode == "partial":
        assert base64.b64decode(trace["response_base64"]) == b'{"response":"unit-fixture'
    row = runtime.read_jsonl(out / "records.jsonl")[0]
    assert row["arms"]["check"]["call_failed"] is True
    assert all(row["arms"][a]["status"] == "NOT_RUN" for a in runtime.ARMS[1:])
    assert verify(out)["status"] == "INCOMPLETE"
    with pytest.raises(runtime.Blocked, match="overwrite"):
        study.run(args(approval, out))


def test_identity_drift_stops_before_generation(tmp_path, monkeypatch):
    approval, out = approve(tmp_path), tmp_path / "wrong-model"
    calls = fake_http(monkeypatch, wrong_digest=True)
    assert study.run(args(approval, out)) == 2
    assert calls == []
    assert runtime.read_json(out / "completion.json")["attempted_case_calls"] == 0


def test_resealed_grade_and_summary_mutations_are_detected(tmp_path):
    original = tmp_path / "controls"
    assert study.main(["controls", "--phase", "smoke", "--out", str(original)]) == 0
    for mutation in ("grade", "summary"):
        out = tmp_path / mutation
        shutil.copytree(original, out)
        if mutation == "grade":
            path = out / "records.jsonl"
            records = runtime.read_jsonl(path)
            records[0]["grade"]["label"] = "wrong"
            path.write_text("".join(json.dumps(r) + "\n" for r in records))
        else:
            path = out / "summary.json"
            summary = runtime.read_json(path)
            summary["layers"]["independent_authored_candidates"]["arms"]["check"]["wrong_accepted"] += 1
            path.write_text(json.dumps(summary))
        checksum_path = out / "checksums.json"
        checksum_path.write_text(json.dumps({p.name: runtime.sha(p.read_bytes()) for p in out.iterdir() if p.name != "checksums.json"}))
        assert verify(out)["status"] != "PASS"


def test_verifier_receipt_cannot_overwrite_input(tmp_path):
    from verify_followup import main
    out = tmp_path / "controls"
    assert study.main(["controls", "--phase", "smoke", "--out", str(out)]) == 0
    before = (out / "manifest.json").read_bytes()
    with pytest.raises(SystemExit):
        main(["--run-dir", str(out), "--receipt", str(out / "manifest.json")])
    assert (out / "manifest.json").read_bytes() == before


def test_permit_rechecks_freeze_git_approval_and_booth_before_each_call(tmp_path, monkeypatch):
    approval = approve(tmp_path)
    declaration = runtime.plan("gemma_harder", "smoke")
    permit = runtime.authorize(declaration, approval, True, "unit-fixture", tmp_path / "unused")
    frozen, freeze_hash = runtime.file_manifest()
    with monkeypatch.context() as m:
        m.setattr(runtime, "file_manifest", lambda: (frozen, "changed-freeze"))
        with pytest.raises(runtime.Blocked, match="drifted"):
            permit.before_call()
    with monkeypatch.context() as m:
        m.setattr(runtime, "git_identity", lambda: "0" * 40)
        with pytest.raises(runtime.Blocked, match="drifted"):
            permit.before_call()
    import booth
    with monkeypatch.context() as m:
        m.setattr(booth, "__version__", "0.0.unit-fixture")
        with pytest.raises(runtime.Blocked, match="BOOTH core"):
            permit.before_call()
    approval.write_text(approval.read_text() + " ")
    with pytest.raises(runtime.Blocked, match="approval changed"):
        permit.before_call()
    assert permit.attempted == 0


def test_gate_failure_after_success_never_reuses_stale_trace(tmp_path, monkeypatch):
    approval, out = approve(tmp_path), tmp_path / "gate-failure-fixture"
    calls = fake_http(monkeypatch)
    original = runtime.Permit.before_call
    n = 0

    def fail_second(self):
        nonlocal n
        n += 1
        if n == 2:
            raise runtime.Blocked("unit-fixture gate denied second request")
        return original(self)

    monkeypatch.setattr(runtime.Permit, "before_call", fail_second)
    assert study.run(args(approval, out)) == 2
    assert len(calls) == 1
    completion = runtime.read_json(out / "completion.json")
    assert completion["attempted_case_calls"] == completion["successful_case_calls"] == 1
    assert completion["failed_case_calls"] == 0
    assert completion["not_attempted_case_calls"] == 2
    records = runtime.read_jsonl(out / "records.jsonl")
    assert len(records) == 2
    assert records[1]["answer"] is None
    assert records[1]["provider_calls"] == 0 and records[1]["provider_trace_index"] is None
    assert records[1]["arms"]["check"]["call_failed"] is True
    assert all(records[1]["arms"][a]["status"] == "NOT_RUN" for a in runtime.ARMS[1:])
    assert verify(out)["status"] == "INCOMPLETE"


def test_main_is_bound_to_the_same_approval_and_run(tmp_path, monkeypatch):
    approval, out = approve(tmp_path), tmp_path / "synthetic-smoke"
    fake_http(monkeypatch)
    assert study.run(args(approval, out)) == 0
    assert verify(out)["status"] == "PASS"
    other = tmp_path / "other"
    other.mkdir()
    different = approve(other, run_id="other-fixture")
    declaration = runtime.plan("gemma_harder", "main")
    with pytest.raises(runtime.Blocked, match="different run ID"):
        runtime.authorize(declaration, different, True, "other-fixture", tmp_path / "unused-main", out)


@pytest.mark.parametrize("field,value", [
    ("source_commit", "0" * 40), ("expected_total_model_calls", 999),
    ("planned_case_calls", 999), ("configured_case_calls", 999), ("warmup_calls", 999),
    ("replay_model_calls", 999), ("quantization", "wrong"), ("host", "https://unexpected.invalid"),
    ("approval_sha256", "fake"), ("case_set", "wrong"), ("repetitions", 999),
])
def test_resealed_manifest_declaration_tampering_is_detected(tmp_path, field, value):
    out = tmp_path / "controls"
    assert study.main(["controls", "--phase", "smoke", "--out", str(out)]) == 0
    path = out / "manifest.json"
    manifest = runtime.read_json(path)
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    reseal(out)
    assert verify(out)["status"] != "PASS"


def reseal(out):
    (out / "checksums.json").write_text(json.dumps({
        p.name: runtime.sha(p.read_bytes()) for p in out.iterdir() if p.is_file() and p.name != "checksums.json"
    }))


def test_contradictory_trace_status_and_approval_snapshot_are_detected(tmp_path, monkeypatch):
    approval, out = approve(tmp_path), tmp_path / "synthetic-smoke"
    fake_http(monkeypatch)
    assert study.run(args(approval, out)) == 0
    trace = out / "provider_calls.jsonl"
    records = runtime.read_jsonl(trace)
    records[0]["done"] = False
    records[0]["done_reason"] = "length"
    trace.write_text("".join(json.dumps(r) + "\n" for r in records))
    reseal(out)
    assert verify(out)["status"] != "PASS"
    snapshot = runtime.read_json(out / "approval.json")
    snapshot["digest"] = "wrong"
    (out / "approval.json").write_text(json.dumps(snapshot))
    reseal(out)
    assert verify(out)["status"] != "PASS"


@pytest.mark.parametrize("bad_time", ["not-a-timestamp", "2000-01-01T00:00:00", 42])
def test_resealed_approval_timestamp_matches_execution_gate(tmp_path, monkeypatch, bad_time):
    approval, out = approve(tmp_path), tmp_path / "synthetic-smoke"
    fake_http(monkeypatch)
    assert study.run(args(approval, out)) == 0
    path = out / "approval.json"
    snapshot = runtime.read_json(path)
    snapshot["approved_utc"] = bad_time
    path.write_text(json.dumps(snapshot))
    manifest = runtime.read_json(out / "manifest.json")
    manifest["approval_sha256"] = runtime.sha(path.read_bytes())
    (out / "manifest.json").write_text(json.dumps(manifest))
    reseal(out)
    result = verify(out)
    assert result["status"] != "PASS"
    assert "approval instruction/time" in result["findings"]
    assert runtime.valid_approval_time(bad_time) is False
