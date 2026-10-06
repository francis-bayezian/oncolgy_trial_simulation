"""One layout for every test protocol, named by its NCT number (user direction 2026-10-06: no more blind / temporal /
testing labels). Moves the PDFs, compiled specs, locked stages and run outputs; never edits a lock file (a lock verifies
the files in its own directory, and its recorded inputs keep their old paths and checksums). Every move is recorded in
data/manifest/protocol_aliases.json so an old path in a lock's provenance still resolves. Writes the single registry
data/manifest/protocols.json.

Usage: .venv/Scripts/python.exe scripts/unify_protocol_layout.py [--apply]   (default: dry run)
"""

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

PROTOCOLS = [  # (NCT, old label, old PDF, old spec dir)
    ("NCT00392327", "ACNS0332", "protocols/Prot_SAP_000.pdf", "data/protocol_specs/ACNS0332"),
    ("NCT01391962", "NCT01391962", "protocols/NCT01391962.pdf", "data/protocol_specs/NCT01391962"),
    ("NCT01616875", "NCT01616875", "protocols/NCT01616875.pdf", "data/protocol_specs/NCT01616875"),
    ("NCT01625234", "NCT01625234", "protocols/NCT01625234.pdf", "data/protocol_specs/X396-CLI-101"),
    ("NCT02224599", "NCT02224599", "protocols/NCT02224599.pdf", "data/protocol_specs/KIROVAX-003"),
    ("NCT04003610", "BLIND_1", "protocols/blind/BLIND_1.pdf", "data/protocol_specs/INCB_54828-205"),
    ("NCT04205799", "BLIND_2", "protocols/blind/BLIND_2.pdf", "data/protocol_specs/CABOCOL-01"),
    ("NCT04083170", "BLIND_3", "protocols/blind/BLIND_3.pdf", "data/protocol_specs/1004070"),
    ("NCT03859427", "NCT03859427", "protocols/temporal/NCT03859427.pdf", "data/trial/temporal/NCT03859427_spec_v3"),
    ("NCT06604442", "NCT06604442", "protocols/testing/NCT06604442.pdf", "data/protocol_specs/NCT06604442"),
]
HISTORY_ROOTS = ["data/trial/unblinded", "data/trial/blind", "data/trial/temporal"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tracked(p: Path) -> bool:
    return subprocess.run(["git", "ls-files", "--error-unmatch", str(p)], capture_output=True).returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    moves: list[tuple[Path, Path]] = []
    for nct, label, pdf, spec in PROTOCOLS:
        moves.append((Path(pdf), Path(f"protocols/{nct}.pdf")))
        moves.append((Path(spec), Path(f"data/protocol_specs/{nct}")))
        moves.append((Path(f"data/locked/{label}"), Path(f"data/locked/{nct}")))
        moves.append((Path(f"data/trial/runs/{label}"), Path(f"data/trial/runs/{nct}")))
        for root in HISTORY_ROOTS:
            for old in (Path(root) / label, Path(root) / nct):
                if old.is_dir():
                    moves.append((old, Path(f"data/trial/runs/{nct}/history/{Path(root).name}")))
    plan = [(s, d) for s, d in dict.fromkeys(moves) if s.exists() and s.resolve() != d.resolve()]
    for s, d in plan:
        print(f"{'MOVE' if a.apply else 'would move'}  {s.as_posix()}  ->  {d.as_posix()}{'  (exists: merge)' if d.exists() else ''}")
    if not a.apply:
        return
    aliases = {}
    for s, d in plan:
        d.parent.mkdir(parents=True, exist_ok=True)
        if tracked(s):
            subprocess.run(["git", "mv", str(s), str(d)], check=True)
        elif d.exists() and s.is_dir():               # merge a directory into an existing one, never overwriting
            for item in s.iterdir():
                target = d / item.name
                if target.exists():
                    raise SystemExit(f"refusing to overwrite {target}")
                shutil.move(str(item), str(target))
            s.rmdir()
        else:
            shutil.move(str(s), str(d))
        aliases[s.as_posix()] = d.as_posix()
    registry = []
    for nct, label, pdf, spec in PROTOCOLS:
        new_pdf = Path(f"protocols/{nct}.pdf")
        registry.append({"nct_id": nct, "pdf": new_pdf.as_posix(), "pdf_sha256": sha(new_pdf), "spec_dir": f"data/protocol_specs/{nct}",
                         "locked": f"data/locked/{nct}", "runs": f"data/trial/runs/{nct}",
                         "former_label": label if label != nct else None, "former_pdf": pdf, "former_spec_dir": spec})
    Path("data/manifest/protocols.json").write_text(json.dumps({
        "purpose": "every test protocol, named by its NCT number; all are test data (none is a blind or temporal test)",
        "updated": date.today().isoformat(), "protocols": registry}, indent=1), encoding="utf-8")
    alias_file = Path("data/manifest/protocol_aliases.json")
    old = json.loads(alias_file.read_text(encoding="utf-8")) if alias_file.exists() else {}
    alias_file.write_text(json.dumps({**old, **aliases}, indent=1), encoding="utf-8")
    print(json.dumps({"moved": len(plan), "registry": "data/manifest/protocols.json", "aliases": alias_file.as_posix()}))


if __name__ == "__main__":
    main()
