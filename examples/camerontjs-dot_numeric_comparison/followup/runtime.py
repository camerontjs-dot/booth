"""Explicit opt-in, pinned source identity and bounded local inference.

Importing this module, planning, offline controls and saved-result verification
never invoke a model. Only a valid owner approval AND the execution flag can
create a live permit. This is a workflow gate, not authentication of a person.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
ARMS = ("check", "validator", "keyword_evidence", "numeric_evidence")
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
LIVE_HOST = "http://127.0.0.1:11434"


class Blocked(RuntimeError):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def append_jsonl(path, value):
    import os
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def file_manifest():
    manifest_path = HERE / "freeze.json"
    if not manifest_path.is_file():
        raise Blocked("freeze.json is missing; candidate is not ready")
    frozen = read_json(manifest_path)
    for relative, expected in frozen["files"].items():
        path = (EXAMPLE / relative).resolve()
        if EXAMPLE not in path.parents:
            raise Blocked("unsafe frozen source path")
        if not path.is_file() or sha(path.read_bytes()) != expected:
            raise Blocked("frozen source changed: " + relative)
    return frozen, sha(manifest_path.read_bytes())


def load_frozen():
    file_manifest()
    # The original module imports its own independent reference grader.
    # Use only the byte-pinned original files and keep their public names stable.
    if str(EXAMPLE) not in sys.path:
        sys.path.insert(0, str(EXAMPLE))
    loaded = sys.modules.get("grade_answers")
    if loaded is not None and Path(loaded.__file__).resolve() != EXAMPLE / "grade_answers.py":
        raise Blocked("another grade_answers module is already imported")
    spec = importlib.util.spec_from_file_location("booth36_frozen_runner", EXAMPLE / "run_example.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    frozen, _ = file_manifest()
    if module.booth.__version__ != "0.5.9":
        raise Blocked("requires BOOTH 0.5.9")
    if sha(Path(module.booth.core.__file__).read_bytes()) != frozen["booth_core_sha256"]:
        raise Blocked("installed BOOTH core differs from the frozen source")
    return module


def git_identity():
    return subprocess.check_output(["git", "-C", str(HERE), "rev-parse", "HEAD"], text=True).strip()


def commit_matches(commit, freeze_hash):
    """Bind the declared Git commit to every frozen source blob, including the freeze."""
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise Blocked("source commit must be a full Git SHA")
    frozen, actual_hash = file_manifest()
    if actual_hash != freeze_hash:
        raise Blocked("candidate freeze differs from declaration")
    prefix = "examples/camerontjs-dot_numeric_comparison/"
    try:
        listing = subprocess.check_output(["git", "-C", str(EXAMPLE), "ls-tree", "-rz", "--full-tree", commit, "--", prefix], stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Blocked("recorded source commit is unavailable in this Git clone") from exc
    entries = {}
    for item in listing.split(b"\0"):
        if item:
            meta, name = item.split(b"\t", 1)
            entries[name.decode()] = meta.split()[2].decode()
    for relative in list(frozen["files"]) + ["followup/freeze.json"]:
        data = (EXAMPLE / relative).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if entries.get(prefix + relative) != blob:
            raise Blocked("source commit does not contain the frozen file: " + relative)
    return True


def cases_for(profile, phase):
    source = HERE / "challenge_cases.json" if profile["case_set"] == "harder" else EXAMPLE / "cases.json"
    fixture = read_json(source)
    key = "smoke_cases" if phase == "smoke" else ("main_cases" if profile["case_set"] == "harder" else "cases")
    cases = fixture[key]
    return list(cases)


def plan(profile_name, phase):
    config = read_json(HERE / "RUNS.json")
    if profile_name not in config["profiles"]:
        raise Blocked("unknown run profile")
    profile = config["profiles"][profile_name]
    cases = cases_for(profile, phase)
    if len(cases) != profile["phase_calls"][phase]:
        raise Blocked("case count does not match declared call budget")
    _, freeze_hash = file_manifest()
    return {
        "schema": 2, "status": "PLAN_ONLY_NO_MODEL_CALLS",
        "profile": profile_name, "phase": phase, "case_set": profile["case_set"],
        "model": profile["model"], "digest": profile["digest"],
        "quantization": profile["quantization"], "model_ready": profile["ready"],
        "host": config["host"], "settings": config["settings"],
        "planned_case_calls": len(cases), "warmup_calls": 0, "replay_model_calls": 0,
        "expected_total_model_calls": len(cases), "repetitions": 1,
        "freeze_sha256": freeze_hash, "source_commit": git_identity(),
        "case_ids": [case["id"] for case in cases],
        "unshuffled_cases_sha256": sha(json.dumps(cases, ensure_ascii=False, sort_keys=True).encode()),
    }


class Permit:
    """One claimed phase and its hard call cap; never instantiated by tests by default."""
    def __init__(self, declaration, approval, claim_path, approval_path):
        self.declaration = declaration
        self.approval = approval
        self.claim_path = claim_path
        self.approval_path = approval_path
        self.approval_sha256 = sha(approval_path.read_bytes())
        self.attempted = 0

    def before_call(self):
        frozen, current_hash = file_manifest()
        if current_hash != self.declaration["freeze_sha256"] or git_identity() != self.declaration["source_commit"]:
            raise Blocked("approved candidate identity drifted before model dispatch")
        if sha(self.approval_path.read_bytes()) != self.approval_sha256:
            raise Blocked("owner approval changed before model dispatch")
        import booth
        if booth.__version__ != "0.5.9" or sha(Path(booth.core.__file__).read_bytes()) != frozen["booth_core_sha256"]:
            raise Blocked("installed BOOTH core drifted before model dispatch")
        if self.attempted >= self.declaration["expected_total_model_calls"]:
            raise Blocked("approved model-call budget exhausted")
        self.attempted += 1
        append_jsonl(self.claim_path.with_suffix(".calls.jsonl"), {
            "attempt": self.attempted, "utc": utc(), "profile": self.declaration["profile"],
            "phase": self.declaration["phase"],
        })


def authorize(declaration, approval_path, execute, run_id, out, smoke_run=None):
    # Validate every gate before claiming a phase or invoking any network code.
    if execute is not True:
        raise Blocked("model calls disabled; requires --allow-model-calls AND an owner approval file")
    if approval_path is None:
        raise Blocked("an explicit owner approval file is required")
    if not SAFE_ID.fullmatch(run_id or ""):
        raise Blocked("run-id must be a short lowercase identifier")
    approval_path = Path(approval_path).resolve()
    approval = read_json(approval_path)
    required = {
        "status": "OWNER_APPROVED", "owner": "Cameron", "run_id": run_id,
        "profile": declaration["profile"], "freeze_sha256": declaration["freeze_sha256"],
        "source_commit": declaration["source_commit"], "model": declaration["model"],
        "digest": declaration["digest"],
    }
    for key, expected in required.items():
        if approval.get(key) != expected:
            raise Blocked("owner approval missing or mismatched: " + key)
    if not isinstance(approval.get("approved_utc"), str) or not isinstance(approval.get("owner_instruction"), str) or not approval["owner_instruction"].strip():
        raise Blocked("approval needs the explicit owner instruction and time")
    try:
        approved_time = dt.datetime.fromisoformat(approval["approved_utc"].replace("Z", "+00:00"))
        if approved_time.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError as exc:
        raise Blocked("approval time must be an explicit timezone-aware ISO timestamp") from exc
    phases = approval.get("phase_call_limits", {})
    if type(phases.get(declaration["phase"])) is not int or phases[declaration["phase"]] != declaration["expected_total_model_calls"]:
        raise Blocked("phase is not approved for its exact call budget")
    if not declaration["model_ready"] or not declaration["digest"]:
        raise Blocked("model identity is not pinned/ready")
    if declaration["host"] != LIVE_HOST:
        raise Blocked("only the declared local Ollama endpoint is permitted")
    commit_matches(declaration["source_commit"], declaration["freeze_sha256"])
    if Path(out).exists():
        raise Blocked("output must be a fresh directory; resume/overwrite is disabled")
    if declaration["phase"] == "main":
        if smoke_run is None:
            raise Blocked("main requires --smoke-run from the completed, verified smoke phase")
        from verify_followup import verify
        smoke_result = verify(Path(smoke_run))
        sm = read_json(Path(smoke_run) / "manifest.json")
        completion = read_json(Path(smoke_run) / "completion.json")
        if smoke_result["status"] != "PASS" or sm["phase"] != "smoke" or sm["profile"] != declaration["profile"]:
            raise Blocked("smoke evidence is not a passing matching smoke phase")
        if sm["run_id"] != run_id or sm["approval_sha256"] != sha(approval_path.read_bytes()):
            raise Blocked("smoke evidence belongs to a different run ID or owner approval")
        for key in ("freeze_sha256", "source_commit", "model", "digest"):
            if sm[key] != declaration[key]:
                raise Blocked("smoke identity differs: " + key)
        if completion["attempted_case_calls"] != 3:
            raise Blocked("smoke call count differs from protocol")
    claims = approval_path.parent / (approval_path.name + ".claims")
    claims.mkdir(exist_ok=True)
    claim_path = claims / (run_id + "-" + declaration["phase"] + ".json")
    try:
        write_json(claim_path, {
            "state": "PHASE_CLAIMED", "utc": utc(), "approval_sha256": sha(approval_path.read_bytes()),
            "run_id": run_id, "output": str(Path(out).resolve()), "declaration": declaration,
        })
    except FileExistsError as exc:
        raise Blocked("this phase was already claimed; preserve it and obtain a new run approval") from exc
    return Permit(declaration, approval, claim_path, approval_path)

