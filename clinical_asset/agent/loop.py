"""The improvement loop: propose, test and gate a fix for an open lesson, on development material only.

For an OPEN lesson (its regression check fails):
  1. context: the source of the functions and files the lesson names (`where`), plus the failing check's detail;
  2. proposal: the model returns a diagnosis, the general rule, and exact search-and-replace edits (no free-form diff);
  3. sandbox: the code (clinical_asset, scripts, tests) is copied to a sandbox that sees the project's data read-only
     through a directory junction; the edits are applied there;
  4. gates, all in the sandbox: the target lesson's check passes, no lesson that passed before fails, and the whole
     test suite passes;
  5. outcome: accepted proposals are saved as a patch (data/agent/proposals/) and recorded in the lessons register;
     nothing is applied to the project unless `apply=True`, and nothing is ever committed by the loop.

The loop never reads a blind or temporal trial's registry results and never runs a scoring stage.
"""

import difflib
import inspect
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import lessons as L

ROOT = Path(__file__).resolve().parents[2]
SANDBOX = ROOT / "tmp" / "agent_sandbox"
PROPOSALS = ROOT / "data" / "agent" / "proposals"
COPY = ("clinical_asset", "scripts", "tests", "pyproject.toml")
SCHEMA_TEXT = {"type": "string"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["diagnosis", "general_rule", "edits"],
          "properties": {"diagnosis": SCHEMA_TEXT, "general_rule": SCHEMA_TEXT,
                         "edits": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                              "required": ["file", "old", "new", "reason"],
                                                              "properties": {"file": SCHEMA_TEXT, "old": SCHEMA_TEXT,
                                                                             "new": SCHEMA_TEXT, "reason": SCHEMA_TEXT}}}}}
INSTRUCTIONS = (
    "You fix one defect in a clinical-trial simulation pipeline (Python). You get the lesson (the defect and the "
    "general rule it teaches), the failing regression check with its detail and source, and the relevant source code. "
    "Return a diagnosis, the general rule, and edits that fix the defect GENERALLY (never by special-casing the check's "
    "examples): each edit replaces one exact, unique 'old' snippet of a file (path relative to the project root, as "
    "given) by 'new'. Keep edits minimal and in the style of the surrounding code; keep clinical vocabulary out of "
    "Python code; do not change the regression check or the tests.")


def _source_of(ref: str) -> dict[str, str]:
    """'protocol.compiler._as_fraction' -> that function's source; a path -> the file (truncated)."""
    out = {}
    for token in [t.strip(" ,") for t in ref.replace(";", " ").split()]:
        path = ROOT / token.split(":")[0]
        if path.is_file():
            out[token] = path.read_text(encoding="utf-8")[:12000]
            continue
        parts = token.split(".")
        for cut in range(len(parts), 0, -1):
            try:
                mod = importlib.import_module("clinical_asset." + ".".join(parts[:cut]))
            except Exception:  # noqa: BLE001
                continue
            obj = mod
            for name in parts[cut:]:
                obj = getattr(obj, name, None)
            if obj is not None:
                try:
                    out[f"{Path(inspect.getsourcefile(obj)).relative_to(ROOT).as_posix()}::{token}"] = inspect.getsource(obj)[:12000]
                except (TypeError, OSError):
                    pass
            break
    return out


def _remove_sandbox(box: Path) -> None:
    """Delete a sandbox without ever touching the project data behind its junction: the junction is removed first
    (rmdir on a junction removes the link only), and nothing outside tmp/agent_sandbox is ever deleted."""
    assert box.parent == SANDBOX and box.name, f"refusing to delete {box}"
    link = box / "data"
    if os.path.lexists(link):
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()
    assert not os.path.lexists(link)

    def retry(func, path, _exc):                        # read-only or briefly locked files: clear the flag, retry once
        os.chmod(path, 0o700)
        try:
            func(path)
        except OSError:
            pass
    shutil.rmtree(box, onerror=retry)


def _sandbox(name: str) -> Path:
    box = SANDBOX / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}"
    box.mkdir(parents=True)
    for item in COPY:
        src = ROOT / item
        if src.is_dir():
            shutil.copytree(src, box / item, ignore=shutil.ignore_patterns("__pycache__"))
        elif src.exists():
            shutil.copy2(src, box / item)
    if os.name == "nt":                                   # the project's data, seen through a junction (no copy)
        subprocess.run(["cmd", "/c", "mklink", "/J", str(box / "data"), str(ROOT / "data")], capture_output=True, check=True)
    else:
        (box / "data").symlink_to(ROOT / "data")
    (box / "protocols").mkdir(exist_ok=True)
    return box


def _in_box(box: Path, code: str, timeout: int = 1800) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(box), "PYTHONIOENCODING": "utf-8"}
    env.pop("CLINICAL_EVIDENCE_CUTOFF", None)
    return subprocess.run([sys.executable, "-c", code], cwd=box, env=env, capture_output=True, text=True, timeout=timeout)


def _checks(box: Path) -> dict:
    r = _in_box(box, "import json; from clinical_asset.agent import lessons as L; print(json.dumps({x['id']: x['status'] for x in L.run_checks()}))")
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {"_error": r.stderr[-2000:]}


def _tests(box: Path) -> tuple[bool, str]:
    r = _in_box(box, "import sys, pytest; sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '--basetemp', 'pytest_tmp', 'tests']))", timeout=3600)
    return r.returncode == 0, (r.stdout.strip().splitlines() or ["no output"])[-1]


def improve(model, lesson_id: str, apply: bool = False) -> dict:
    lesson = next(x for x in L.load() if x["id"] == lesson_id)
    before = {x["id"]: x["status"] for x in L.run_checks()}
    if before.get(lesson_id) != "OPEN":
        return {"lesson": lesson_id, "outcome": "not open"}
    detail = next(x["detail"] for x in L.run_checks() if x["id"] == lesson_id)
    context = _source_of(lesson.get("where", "")) | {f"clinical_asset/agent/lessons.py::{lesson['check']}": inspect.getsource(L.CHECKS[lesson["check"]])}
    payload = {"instructions": INSTRUCTIONS, "lesson": lesson, "failing_check_detail": detail, "source": context}
    proposal = model.extract("agent_fix_proposal", SCHEMA, payload)
    box = _sandbox(lesson_id)
    applied, problems = [], []
    for e in proposal["edits"]:
        f = box / e["file"]
        text = f.read_text(encoding="utf-8") if f.exists() else None
        if text is None or text.count(e["old"]) != 1:
            problems.append(f"{e['file']}: 'old' snippet found {0 if text is None else text.count(e['old'])} times")
            continue
        f.write_text(text.replace(e["old"], e["new"]), encoding="utf-8")
        applied.append(e)
    after = _checks(box) if not problems else {}
    regressions = [k for k, v in before.items() if v == "PASS" and after.get(k) != "PASS"]
    tests_ok, tests_line = _tests(box) if not problems and after.get(lesson_id) == "PASS" and not regressions else (False, "not run")
    accepted = not problems and after.get(lesson_id) == "PASS" and not regressions and tests_ok
    record = {"lesson": lesson_id, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "diagnosis": proposal["diagnosis"],
              "general_rule": proposal["general_rule"], "edits": [{k: e[k] for k in ("file", "reason")} for e in proposal["edits"]],
              "problems": problems, "target_after": after.get(lesson_id), "regressions": regressions, "tests": tests_line,
              "outcome": "ACCEPTED" if accepted else "REJECTED"}
    if accepted:
        PROPOSALS.mkdir(parents=True, exist_ok=True)
        diff = []
        for e in applied:
            old = (ROOT / e["file"]).read_text(encoding="utf-8").splitlines(keepends=True)
            new = (box / e["file"]).read_text(encoding="utf-8").splitlines(keepends=True)
            diff += difflib.unified_diff(old, new, f"a/{e['file']}", f"b/{e['file']}")
        patch = PROPOSALS / f"{lesson_id}_{time.strftime('%Y%m%d_%H%M%S')}.patch"
        patch.write_text("".join(diff), encoding="utf-8")
        record["patch"] = str(patch.relative_to(ROOT)).replace("\\", "/")
        if apply:
            for e in applied:
                shutil.copy2(box / e["file"], ROOT / e["file"])
            record["applied_to_project"] = True
    with open(ROOT / "data" / "agent" / "loop_log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    _remove_sandbox(box)
    if accepted:
        with open(L.REGISTER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": lesson_id, "fix": record["patch"], "fixed_by": "agent loop" + (" (applied)" if apply else " (proposed)"),
                                 "agent_diagnosis": proposal["diagnosis"]}, ensure_ascii=False) + "\n")
    return record


def run(model, apply: bool = False) -> list[dict]:
    return [improve(model, x["id"], apply) for x in L.run_checks() if x["status"] == "OPEN"]
