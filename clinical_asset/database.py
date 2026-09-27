"""Load clinical profiles into a local SQLite database shaped like the handbook's
``clinical_evidence_profile`` table (indexed columns plus JSON sections).

The same rows can later be loaded into PostgreSQL (Neon) once the output is accepted.
Holdout trials are refused even if their JSON exists.
"""

import json
import sqlite3
from pathlib import Path

SECTIONS = (
    "cancer", "treatment", "treatment_ontology", "patient_profile", "selection_context",
    "efficacy", "toxicity", "treatment_course", "comparisons", "mortality_observations", "source",
)


def load_database(
    asset_dir: Path = Path("data/clinical-asset"),
    database: Path = Path("data/clinical_asset.sqlite"),
    holdout: Path = Path("data/manifest/holdout_test_trials.json"),
    only: set[str] | None = None,
) -> dict:
    held = set(json.loads(holdout.read_text(encoding="utf-8"))["nct_ids"]) if holdout.exists() else set()
    temporary = database.with_suffix(".building")
    temporary.unlink(missing_ok=True)
    db = sqlite3.connect(temporary)
    db.execute(
        f"""CREATE TABLE clinical_evidence_profile (
            id INTEGER PRIMARY KEY,
            source_nct TEXT NOT NULL,
            profile_type TEXT,
            registry_group TEXT,
            disease TEXT, disease_cui TEXT, setting TEXT,
            primary_biomarker TEXT, primary_drug TEXT, drug_class TEXT,
            {", ".join(f"{s} TEXT" for s in SECTIONS)}
        )"""
    )
    trials = profiles = refused = 0
    for path in sorted(asset_dir.glob("NCT*.json")):
        nct = path.stem
        if nct in held:
            refused += 1
            continue
        if only is not None and nct not in only:
            continue
        asset = json.loads(path.read_text(encoding="utf-8"))
        trials += 1
        for profile in asset["clinical_profiles"]:
            cancer = profile.get("cancer", {})
            markers = cancer.get("biomarkers") or []
            db.execute(
                f"INSERT INTO clinical_evidence_profile (source_nct, profile_type, registry_group, disease, disease_cui, "
                f"setting, primary_biomarker, primary_drug, drug_class, {', '.join(SECTIONS)}) "
                f"VALUES ({', '.join('?' * (9 + len(SECTIONS)))})",
                (
                    nct,
                    profile.get("profile_type"),
                    profile.get("source", {}).get("registry_group"),
                    cancer.get("disease", {}).get("name"),
                    cancer.get("disease", {}).get("umls_cui"),
                    cancer.get("setting"),
                    f"{markers[0]['gene']} {markers[0]['variant']}" if markers else None,
                    profile.get("treatment", {}).get("drug"),
                    profile.get("treatment_ontology", {}).get("drug_class"),
                    *(json.dumps(profile[s], ensure_ascii=False) if s in profile else None for s in SECTIONS),
                ),
            )
            profiles += 1
    for column in ("source_nct", "disease_cui", "primary_drug", "primary_biomarker", "setting", "profile_type"):
        db.execute(f"CREATE INDEX idx_{column} ON clinical_evidence_profile({column})")
    db.commit()
    db.close()
    temporary.replace(database)
    return {"database": str(database), "trials": trials, "profiles": profiles, "holdout_refused": refused}
