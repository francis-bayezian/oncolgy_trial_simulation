import json
import os
import stat

import pytest

from clinical_asset.trial import lock


def _source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    (src / "b.md").write_text("report", encoding="utf-8")
    (tmp_path / "input.pdf").write_bytes(b"%PDF-1.4 test")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "m.py").write_text("X = 1\n", encoding="utf-8")
    return src, pkg


def _unlock(path):
    for p in path.iterdir():
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)


def test_lock_seals_files_inputs_and_code_and_verifies(tmp_path):
    src, pkg = _source(tmp_path)
    record = lock.lock(src, tmp_path / "locked", "demo", "1.0.0", {"pdf": tmp_path / "input.pdf"}, [pkg], {"gate": "PASS"})
    assert set(record["files"]) == {"a.json", "b.md"} and record["inputs"]["pdf"]["sha256"] and record["code"]["sha256"]
    assert lock.load_locked(tmp_path / "locked", "a.json") == {"x": 1}
    assert not os.access(tmp_path / "locked" / "a.json", os.W_OK)
    _unlock(tmp_path / "locked")


def test_a_locked_version_is_never_overwritten(tmp_path):
    src, pkg = _source(tmp_path)
    lock.lock(src, tmp_path / "locked", "demo", "1.0.0", {}, [pkg], {})
    with pytest.raises(lock.LockError):
        lock.lock(src, tmp_path / "locked", "demo", "1.0.0", {}, [pkg], {})
    _unlock(tmp_path / "locked")


def test_tampering_or_extra_files_are_detected(tmp_path):
    src, pkg = _source(tmp_path)
    locked = tmp_path / "locked"
    lock.lock(src, locked, "demo", "1.0.0", {}, [pkg], {})
    _unlock(locked)
    (locked / "a.json").write_text(json.dumps({"x": 2}), encoding="utf-8")
    with pytest.raises(lock.LockError, match="changed"):
        lock.verify(locked)
    (locked / "a.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    lock.verify(locked)
    (locked / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(lock.LockError, match="not locked"):
        lock.verify(locked)
