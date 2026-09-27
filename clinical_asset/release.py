"""Package the cleaned clinical profiles as a versioned asset.

data/asset_v1/
  profiles.jsonl                  cleaned clinical profiles (frozen v1 schema)
  schema/clinical_profile.schema.json
  vocabularies/*.json             canonical vocabularies built from the corpus
  asset.sqlite                    indexed lookup layer + separate internal QA and repair tables
  parquet/*.parquet               analytical exports (when pyarrow is installed)
  manifest.json                   version, scope, counts, holdout, checksums
"""

import datetime
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .batch import load_ids
from .qa import SCHEMA_VERSION, check_profile, summarise
from .repair import repair_asset
from .terminology import UmlsTerminology
from .umls_index import UmlsIndex
from .vocab import build_vocabularies, group_counts

PROFILE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Clinical evidence profile",
    "version": SCHEMA_VERSION,
    "type": "object",
    "required": ["profile_id", "profile_type", "source"],
    "additionalProperties": False,
    "properties": {
        "profile_id": {"type": "string"},
        "profile_type": {"enum": ["randomized_arm", "study_arm", "result_group", "treatment_sequence", "reported_subgroup"]},
        "definition": {"type": "string"},
        "cancer": {"type": "object"},
        "treatment": {"type": "object"},
        "treatment_ontology": {"type": "object"},
        "patient_profile": {"type": "object"},
        "selection_context": {"type": "object"},
        "efficacy": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "object", "required": ["statistic", "value"]},
            },
        },
        "toxicity": {"type": "object"},
        "treatment_course": {"type": "object"},
        "comparisons": {"type": "array", "items": {"type": "object", "required": ["comparator", "outcome", "measure", "value"]}},
        "mortality_observations": {"type": "object"},
        "source": {"type": "object", "required": ["nct"]},
    },
}


def _evidence_level(profile: dict) -> str:
    """What kind of statistical evidence the profile carries (for the synthesis layer)."""
    return "subgroup" if profile["profile_type"] == "reported_subgroup" else "marginal"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _sqlite(path: Path, profiles: list[dict], vocab: dict, issues: list[dict], repairs: list[dict], meta: dict) -> None:
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE profile (profile_id TEXT PRIMARY KEY, source_nct TEXT, profile_type TEXT, evidence_level TEXT,
            registry_group TEXT, disease TEXT, disease_cui TEXT, setting TEXT, biomarkers TEXT, regimen TEXT,
            drug TEXT, drug_cui TEXT, arm_type TEXT, n INTEGER, publications TEXT, profile_json TEXT);
        CREATE TABLE observation (profile_id TEXT, outcome_key TEXT, umls_cui TEXT, statistic TEXT, value REAL,
            unit TEXT, rate REAL, n_denominator INTEGER, ci_low REAL, ci_high REAL, ci_level REAL, category TEXT,
            class TEXT, population TEXT, population_scope TEXT, time_frame TEXT, measure TEXT, sources TEXT,
            evidence_level TEXT);
        CREATE TABLE toxicity_event (profile_id TEXT, event_key TEXT, umls_cui TEXT, kind TEXT, n INTEGER,
            n_denominator INTEGER, rate REAL, source TEXT);
        CREATE TABLE comparison (profile_id TEXT, comparator TEXT, comparator_group TEXT, outcome TEXT, measure TEXT,
            value REAL, ci_low REAL, ci_high REAL, p_value REAL, population TEXT, sources TEXT);
        CREATE TABLE vocabulary (vocabulary TEXT, key TEXT, name TEXT, umls_cui TEXT, trials INTEGER, entry_json TEXT);
        CREATE TABLE qa_issue (source_nct TEXT, code TEXT, severity TEXT, action TEXT, path TEXT, detail TEXT);
        CREATE TABLE repair_log (profile_id TEXT, repair TEXT, path TEXT, detail TEXT);
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    for p in profiles:
        cancer, treatment, ontology = p.get("cancer", {}), p.get("treatment", {}), p.get("treatment_ontology", {})
        db.execute(
            "INSERT INTO profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p["profile_id"], p["source"]["nct"], p["profile_type"], _evidence_level(p), p["source"].get("registry_group"),
             cancer.get("disease", {}).get("name"), cancer.get("disease", {}).get("umls_cui"), cancer.get("setting"),
             json.dumps([f"{m['gene']} {m['variant']}" for m in cancer.get("biomarkers", [])]) if cancer.get("biomarkers") else None,
             treatment.get("regimen"), treatment.get("drug"), ontology.get("umls_cui"), treatment.get("arm_type"),
             p.get("patient_profile", {}).get("n"), json.dumps(p["source"].get("publications", [])),
             json.dumps(p, ensure_ascii=False)),
        )
        for key, observations in p.get("efficacy", {}).items():
            for o in observations:
                interval = o.get("ci") or [None, None]
                db.execute(
                    "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p["profile_id"], key, o.get("umls_cui"), o.get("statistic"),
                     o["value"] if isinstance(o.get("value"), (int, float)) else None, o.get("unit"), o.get("rate"),
                     o.get("N"), interval[0], interval[1], o.get("ci_level"), o.get("category"), o.get("class"),
                     o.get("population"), o.get("population_scope"), o.get("time_frame"), o.get("measure"),
                     json.dumps(o.get("sources") or ([o["source"]] if o.get("source") else ["registry"])), _evidence_level(p)),
                )
        tox = p.get("toxicity", {})
        for kind in ("key_events", "key_serious_events"):
            for key, e in tox.get(kind, {}).items():
                db.execute("INSERT INTO toxicity_event VALUES (?,?,?,?,?,?,?,?)",
                           (p["profile_id"], key, e.get("umls_cui"), kind, e.get("n"), e.get("N") or tox.get("N"),
                            e.get("rate"), "registry"))
        for kind, block in tox.items():
            if kind.startswith("key_grade_3") and isinstance(block, dict):
                for key, e in block.get("events", {}).items():
                    db.execute("INSERT INTO toxicity_event VALUES (?,?,?,?,?,?,?,?)",
                               (p["profile_id"], key, e.get("umls_cui"), kind, e.get("n"), block.get("N"), e.get("rate"), block.get("source")))
        for c in p.get("comparisons", []):
            interval = c.get("ci95") or c.get("ci") or [None, None]
            db.execute("INSERT INTO comparison VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (p["profile_id"], c.get("comparator"), c.get("comparator_group"), c.get("outcome"), c.get("measure"),
                        c.get("value"), interval[0], interval[1], c.get("p_value"), c.get("population"),
                        json.dumps(c.get("sources") or ([c["source"]] if c.get("source") else ["registry"]))))
    for name, rows in vocab.items():
        for row in rows:
            db.execute("INSERT INTO vocabulary VALUES (?,?,?,?,?,?)",
                       (name, str(row.get("key")), row.get("name"), row.get("umls_cui"), row.get("trials"),
                        json.dumps(row, ensure_ascii=False, default=list)))
    for issue in issues:
        db.execute("INSERT INTO qa_issue VALUES (?,?,?,?,?,?)",
                   (issue["source_nct"], issue["code"], issue["severity"], issue["action"], issue["path"],
                    json.dumps(issue.get("detail"), default=str) if "detail" in issue else None))
    for entry in repairs:
        db.execute("INSERT INTO repair_log VALUES (?,?,?,?)",
                   (entry["profile_id"], entry["repair"], entry["path"], json.dumps(entry.get("detail"), default=str)))
    for key, value in meta.items():
        db.execute("INSERT INTO metadata VALUES (?,?)", (key, json.dumps(value, default=str)))
    for table, column in (("profile", "source_nct"), ("profile", "disease_cui"), ("profile", "regimen"), ("profile", "drug"),
                          ("profile", "setting"), ("profile", "profile_type"), ("observation", "profile_id"),
                          ("observation", "outcome_key"), ("observation", "umls_cui"), ("toxicity_event", "profile_id"),
                          ("toxicity_event", "event_key"), ("comparison", "profile_id"), ("comparison", "outcome"),
                          ("vocabulary", "vocabulary"), ("qa_issue", "source_nct"), ("qa_issue", "code")):
        db.execute(f"CREATE INDEX idx_{table}_{column} ON {table}({column})")
    db.commit()
    db.close()


def _parquet(directory: Path, database: Path) -> list[str]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    db = sqlite3.connect(database)
    for table in ("profile", "observation", "toxicity_event", "comparison", "vocabulary"):
        cursor = db.execute(f"SELECT * FROM {table}")
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
        data = {c: [r[i] for r in rows] for i, c in enumerate(columns)}
        pq.write_table(pa.table(data), directory / f"{table}.parquet")
        written.append(f"parquet/{table}.parquet")
    db.close()
    return written


def build_release(
    version: str = "1.0.0",
    manifest: Path = Path("data/manifest/subset_treatment_phase23_result_pub.json"),
    holdout: Path = Path("data/manifest/holdout_test_trials.json"),
    data_dir: Path = Path("data"),
    out_dir: Path | None = None,
) -> dict:
    out_dir = out_dir or data_dir / f"asset_v{version.split('.')[0]}"
    ids, held = load_ids(manifest, holdout)
    index = UmlsIndex()
    terminology = UmlsTerminology(cache_path=data_dir / "cache" / "umls_links.json")
    type_cache: dict[str, list[str]] = {}

    def types_of(cui: str) -> list[str]:
        if cui not in type_cache:
            entity = index.entity(cui)
            type_cache[cui] = entity["types"] if entity else []
        return type_cache[cui]

    profiles: list[dict] = []
    repairs: list[dict] = []
    issues: list[dict] = []
    excluded: list[str] = []
    per_trial: dict[str, list[dict]] = {}
    for nct in ids:
        if nct in held:
            continue
        path = data_dir / "clinical-asset" / f"{nct}.json"
        if not path.exists():
            excluded.append(nct)
            continue
        asset = json.loads(path.read_text(encoding="utf-8"))
        raw_path = data_dir / "raw" / "ctgov" / f"{nct}.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else None
        repaired, log = repair_asset(asset, nct, types_of, terminology)
        repairs.extend(log)
        trial_issues = []
        for i, profile in enumerate(repaired["clinical_profiles"]):
            for issue in check_profile(profile, i, raw, types_of):
                if issue["code"] == "SCHEMA_UNKNOWN_SECTION" and issue.get("detail") == ["profile_id"]:
                    continue
                trial_issues.append({**issue, "source_nct": nct})
            profiles.append(profile)
        per_trial[nct] = trial_issues
        issues.extend(trial_issues)
    terminology.save()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "schema").mkdir(exist_ok=True)
    (out_dir / "schema" / "clinical_profile.schema.json").write_text(json.dumps(PROFILE_SCHEMA, indent=1), encoding="utf-8")
    try:
        import jsonschema

        validator = jsonschema.Draft202012Validator(PROFILE_SCHEMA)
        schema_errors = sum(1 for p in profiles for _ in validator.iter_errors(p))
    except ImportError:
        schema_errors = None
    with open(out_dir / "profiles.jsonl", "w", encoding="utf-8") as handle:
        for profile in profiles:
            handle.write(json.dumps(profile, ensure_ascii=False) + "\n")
    vocab = build_vocabularies(profiles)
    (out_dir / "vocabularies").mkdir(exist_ok=True)
    for name, rows in vocab.items():
        (out_dir / "vocabularies" / f"{name}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False, default=list), encoding="utf-8")
    qa_summary = summarise(per_trial)
    qa_summary.pop("reprocess_ids")
    meta = {
        "asset_version": version,
        "schema_version": SCHEMA_VERSION,
        "created": datetime.datetime.now(datetime.UTC).date().isoformat(),
        "scope": json.loads(manifest.read_text(encoding="utf-8")).get("query"),
        "trials": len(per_trial),
        "profiles": len(profiles),
        "profile_types": group_counts(profiles),
        "holdout_trials": sorted(held),
        "excluded_non_oncology_trials": sorted(excluded),
        "qa": qa_summary,
        "repairs": len(repairs),
        "schema_validation_errors": schema_errors,
    }
    database = out_dir / "asset.sqlite"
    _sqlite(database, profiles, vocab, issues, repairs, meta)
    parquet = _parquet(out_dir / "parquet", database)
    files = ["profiles.jsonl", "asset.sqlite", "schema/clinical_profile.schema.json",
             *(f"vocabularies/{n}.json" for n in vocab), *parquet]
    meta["files"] = {f: _sha256(out_dir / f) for f in files}
    (out_dir / "manifest.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    return {k: v for k, v in meta.items() if k not in {"files", "scope", "holdout_trials", "excluded_non_oncology_trials"}}
