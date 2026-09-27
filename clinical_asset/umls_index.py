"""One-time SQLite index over the local UMLS 2022AB knowledge base.

Exact alias lookup in this index takes milliseconds and needs no model loading, so most
terms never touch the slow fuzzy linker. Built once with ``clinical-asset build-index``.
"""

import json
import re
import sqlite3
import time
from pathlib import Path

DEFAULT_KB = Path("terminology-private/scispacy-umls-2022ab/umls_2022_ab_cat0129.jsonl")
DEFAULT_INDEX = Path("terminology-private/umls_2022ab_index.sqlite")


def normalise_alias(text: str) -> str:
    """Case, whitespace, hyphen and trailing-parenthetical insensitive form."""
    t = text.casefold().replace("–", "-").replace("—", "-")
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)
    t = re.sub(r"[\s\-_/,]+", " ", t)
    return t.strip()


def build_index(kb_path: Path = DEFAULT_KB, index_path: Path = DEFAULT_INDEX) -> dict:
    start = time.perf_counter()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_suffix(".building")
    temporary.unlink(missing_ok=True)
    db = sqlite3.connect(temporary)
    db.executescript(
        """
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE entity (cui TEXT PRIMARY KEY, name TEXT, types TEXT, definition TEXT, aliases TEXT);
        CREATE TABLE alias (norm TEXT, cui TEXT, canonical INTEGER);
        """
    )
    entities = aliases = 0
    batch_e, batch_a = [], []
    with open(kb_path, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            cui, name = row["concept_id"], row["canonical_name"]
            names = [name, *row.get("aliases", [])]
            batch_e.append((cui, name, json.dumps(row.get("types", [])), row.get("definition"), json.dumps(names[:60])))
            seen = set()
            for position, alias in enumerate(names):
                norm = normalise_alias(alias)
                if norm and norm not in seen and len(norm) <= 120:
                    seen.add(norm)
                    batch_a.append((norm, cui, 1 if position == 0 else 0))
            if len(batch_e) >= 50000:
                db.executemany("INSERT INTO entity VALUES (?,?,?,?,?)", batch_e)
                db.executemany("INSERT INTO alias VALUES (?,?,?)", batch_a)
                entities += len(batch_e)
                aliases += len(batch_a)
                batch_e, batch_a = [], []
    db.executemany("INSERT INTO entity VALUES (?,?,?,?,?)", batch_e)
    db.executemany("INSERT INTO alias VALUES (?,?,?)", batch_a)
    entities += len(batch_e)
    aliases += len(batch_a)
    db.execute("CREATE INDEX alias_norm ON alias(norm)")
    db.commit()
    db.close()
    temporary.replace(index_path)
    return {"entities": entities, "aliases": aliases, "seconds": round(time.perf_counter() - start, 1)}


class UmlsIndex:
    def __init__(self, index_path: Path = DEFAULT_INDEX) -> None:
        if not index_path.exists():
            raise FileNotFoundError(f"UMLS index missing; run 'clinical-asset build-index' ({index_path}).")
        self._db = sqlite3.connect(f"file:{index_path.as_posix()}?mode=ro", uri=True, check_same_thread=False)

    def exact(self, text: str) -> list[tuple[str, bool]]:
        """CUIs whose alias matches exactly after normalisation; (cui, is_canonical_name)."""
        rows = self._db.execute("SELECT cui, canonical FROM alias WHERE norm = ?", (normalise_alias(text),)).fetchall()
        return [(cui, bool(canonical)) for cui, canonical in rows]

    def entity(self, cui: str) -> dict | None:
        row = self._db.execute("SELECT name, types, definition, aliases FROM entity WHERE cui = ?", (cui,)).fetchone()
        if row is None:
            return None
        return {"name": row[0], "types": json.loads(row[1]), "definition": row[2], "aliases": json.loads(row[3])}
