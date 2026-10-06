"""Locking: an immutable, checksummed snapshot of a pipeline artefact.

A lock directory holds the artefact's files plus `lock.json`, which records the SHA-256 of every file,
of the inputs it was derived from and of the code that produced it, the creation time and a free
description of its status. Files are made read-only. `load_locked` verifies every checksum before
anything is read, so a downstream stage can never run on an altered artefact.
"""

import datetime
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

LOCK_FILE = "lock.json"


class LockError(RuntimeError):
    pass


ALIASES = Path("data/manifest/protocol_aliases.json")


def resolve(path) -> Path:
    """A path a lock recorded, where it is now: unchanged when it exists, else renamed through the alias manifest
    (old -> new path prefixes, longest first; locks are never edited). Checksums still decide whether it is the same
    file."""
    p = Path(path)
    if p.exists() or not ALIASES.exists():
        return p
    s = str(p).replace("\\", "/")
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    for old in sorted(aliases, key=len, reverse=True):
        if s == old or s.startswith(old.rstrip("/") + "/"):
            return Path(aliases[old] + s[len(old):])
    return p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def code_fingerprint(packages: list[Path]) -> dict:
    """SHA-256 of every Python source file of the given packages, and one digest over all of them."""
    files = sorted(p for pkg in packages for p in Path(pkg).rglob("*.py"))
    digests = {p.as_posix(): sha256_file(p) for p in files}
    overall = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in digests.items()).encode()).hexdigest()
    return {"sha256": overall, "files": digests}


def lock(source_dir: Path, lock_dir: Path, kind: str, version: str, inputs: dict[str, Path],
         code_packages: list[Path], status: dict, files: list[str] | None = None) -> dict:
    """Copy `files` (default: every file) of `source_dir` into a new `lock_dir` and seal it. Refuses to
    overwrite an existing lock: a locked version is immutable."""
    source_dir, lock_dir = Path(source_dir), Path(lock_dir)
    if lock_dir.exists():
        raise LockError(f"{lock_dir} already exists; a locked version is never overwritten")
    names = files or sorted(p.name for p in source_dir.iterdir() if p.is_file())
    lock_dir.mkdir(parents=True)
    for name in names:
        shutil.copy2(source_dir / name, lock_dir / name)
    record = {
        "kind": kind, "version": version,
        "locked_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "files": {name: sha256_file(lock_dir / name) for name in names},
        "inputs": {label: {"path": Path(p).as_posix(), "sha256": sha256_file(Path(p))} for label, p in inputs.items()},
        "code": code_fingerprint(code_packages),
        "status": status,
    }
    (lock_dir / LOCK_FILE).write_text(json.dumps(record, indent=1), encoding="utf-8")
    for p in lock_dir.iterdir():
        os.chmod(p, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    return record


def verify(lock_dir: Path) -> dict:
    """The lock record, after checking that every file still has its recorded checksum."""
    lock_dir = Path(lock_dir)
    path = lock_dir / LOCK_FILE
    if not path.exists():
        raise LockError(f"{lock_dir} is not a locked artefact (no {LOCK_FILE})")
    record = json.loads(path.read_text(encoding="utf-8"))
    for name, digest in record["files"].items():
        if not (lock_dir / name).exists():
            raise LockError(f"{lock_dir / name} is missing")
        if sha256_file(lock_dir / name) != digest:
            raise LockError(f"{lock_dir / name} has changed since it was locked")
    extra = {p.name for p in lock_dir.iterdir()} - set(record["files"]) - {LOCK_FILE}
    if extra:
        raise LockError(f"{lock_dir} contains files that were not locked: {sorted(extra)}")
    return record


def load_locked(lock_dir: Path, name: str) -> dict:
    """Verify the lock, then read one JSON file from it."""
    verify(lock_dir)
    return json.loads((Path(lock_dir) / name).read_text(encoding="utf-8"))
