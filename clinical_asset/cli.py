"""Read-only source retrieval and local clinical JSON extraction.

No command writes to a database. ``extract`` writes three local files:
the clinical asset, its extraction audit, and the raw registry record.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from .abstract_evidence import Resources, extract_publication_evidence
from .ctgov import ClinicalTrialsClient, validate_nct_id
from .enrich import enrich_study
from .publications import PublicationClient
from .registry import parse_study
from .report import build_asset_and_reconciliation, build_audit
from .terminology import UmlsTerminology


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


class _LazyNLP:
    """Loads medspaCy (and optionally the scispaCy NER models) only when first needed."""

    def __init__(self, terminology: UmlsTerminology, use_ner_models: bool) -> None:
        self._terminology = terminology
        self._use_ner_models = use_ner_models
        self._nlp = None

    def __call__(self, text: str) -> list:
        if self._nlp is None:
            from .nlp import ClinicalNLP

            self._nlp = ClinicalNLP(self._terminology, self._use_ner_models)
        return self._nlp.mentions(text)


def extract_trial(
    nct_id: str,
    data_dir: Path,
    output: Path | None,
    use_publications: bool,
    use_model: bool,
    fuzzy: bool = False,
    ner_models: bool = False,
) -> dict:
    terminology = UmlsTerminology(cache_path=data_dir / "cache" / "umls_links.json", fuzzy=fuzzy)
    mentions = _LazyNLP(terminology, ner_models)
    model = None
    if use_model:
        from .llm import LunaClient

        model = LunaClient(cache_dir=data_dir / "cache" / "llm")
    try:
        result = process_trial(nct_id, data_dir, output, use_publications, terminology, model, mentions)
    finally:
        terminology.save()
    if model and "excluded" not in result:
        result.update(new_calls=model.calls, input_tokens=model.input_tokens, output_tokens=model.output_tokens)
    return result


def process_trial(
    nct_id: str,
    data_dir: Path,
    output: Path | None,
    use_publications: bool,
    terminology: UmlsTerminology,
    model: object | None,
    mentions: object,
    offline_registry: bool = False,
) -> dict:
    """One trial with shared, already-loaded resources (used by single runs and the batch)."""
    timings: dict[str, float] = {}
    start = time.perf_counter()
    raw_path = data_dir / "raw" / "ctgov" / f"{nct_id}.json"
    if offline_registry and raw_path.exists():
        # Reprocessing: the stored registry record is the source; nothing is refetched.
        study = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        with ClinicalTrialsClient() as registry:
            study = registry.get_study(nct_id)
    timings["registry_fetch_s"] = time.perf_counter() - start
    parsed = parse_study(study)
    if not parsed.eligible:
        return {"nct_id": parsed.nct_id, "excluded": parsed.exclusion_reason}
    misses_before = set(terminology.fuzzy_misses)

    step = time.perf_counter()
    enrichment = enrich_study(parsed, study, terminology, mentions, model)
    timings["normalisation_s"] = time.perf_counter() - step
    if not parsed.eligible:
        return {"nct_id": parsed.nct_id, "excluded": parsed.exclusion_reason}

    step = time.perf_counter()
    publications = []
    if use_publications:
        with PublicationClient(cache_dir=data_dir / "cache" / "publications") as publication_client:
            publications = [publication_client.retrieve(r) for r in parsed.result_references]
    timings["publication_fetch_s"] = time.perf_counter() - step

    step = time.perf_counter()
    evidence = extract_publication_evidence(parsed, publications, Resources(terminology, model, mentions))
    asset, _ = build_asset_and_reconciliation(parsed, publications, evidence)
    timings["publication_extraction_s"] = time.perf_counter() - step
    usage: dict = {"model": "gpt-5.6-luna" if model else None}
    timings["total_s"] = time.perf_counter() - start
    usage["timings"] = {k: round(v, 2) for k, v in timings.items()}
    usage["terms_without_exact_umls_match"] = sorted(terminology.fuzzy_misses - misses_before)
    output = output or data_dir / "clinical-asset" / f"{nct_id}.json"
    audit_path = data_dir / "audit" / f"{nct_id}.audit.json"
    raw_path = data_dir / "raw" / "ctgov" / f"{nct_id}.json"
    _write_json(raw_path, study)
    _write_json(audit_path, build_audit(parsed, publications, evidence, enrichment, usage))
    _write_json(output, asset)
    return {
        "nct_id": parsed.nct_id,
        "clinical_profiles": len(asset["clinical_profiles"]),
        "asset": str(output),
        "audit": str(audit_path),
        **usage,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clinical-asset")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Write one trial's clinical evidence to local JSON.")
    extract.add_argument("nct_id", type=validate_nct_id)
    extract.add_argument("--output", type=Path, help="Clinical asset JSON path.")
    extract.add_argument("--data-dir", type=Path, default=Path("data"))
    extract.add_argument("--skip-publications", action="store_true")
    extract.add_argument("--no-model", action="store_true", help="Do not call GPT-5.6 Luna.")
    extract.add_argument("--fuzzy", action="store_true", help="Load the slow UMLS fuzzy linker for unmatched terms.")
    extract.add_argument("--ner-models", action="store_true", help="Add scispaCy NER models (about 40 s to load).")
    commands.add_parser("build-index", help="Build the one-time UMLS SQLite alias index.")
    batch = commands.add_parser("build-database", help="Process a trial manifest (minus holdout) into the local database.")
    batch.add_argument("--manifest", type=Path, default=Path("data/manifest/subset_treatment_phase23_result_pub.json"))
    batch.add_argument("--holdout", type=Path, default=Path("data/manifest/holdout_test_trials.json"))
    batch.add_argument("--workers", type=int, default=4)
    batch.add_argument("--limit", type=int)
    batch.add_argument("--force", action="store_true", help="Reprocess trials that already have output.")
    commands.add_parser("load-database", help="Load clinical profiles into data/clinical_asset.sqlite.")
    commands.add_parser("build-parameters", help="Fit Simulation Parameter Asset V1 (milestone 1) from frozen Asset V1.")
    commands.add_parser("build-parameters-v2", help="Milestone 2: hierarchical borrowing, survival, censored toxicity.")
    v3 = commands.add_parser("build-parameters-v3", help="Milestone 3: exact binomial calibration, survival fusion, baseline generator.")
    v3.add_argument("--workers", type=int, default=6)
    v3.add_argument("--resume", action="store_true", help="Reuse stored 3A fits and calibration.")
    v3.add_argument("--out", type=Path, default=None, help="output directory (default data/simulation_parameters_v3)")
    v3.add_argument("--exclude", type=Path, default=None, help="holdout-format file of trials to exclude (evidence cut-off)")
    v3.add_argument("--raw-dir", type=Path, default=None, help="raw registry directory (default data/raw/ctgov)")
    cp = commands.add_parser("compile-protocol", help="Milestone 4: compile a protocol (+ SAP) PDF into an executable StudySpec.")
    cp.add_argument("--protocol", type=Path, required=True)
    cp.add_argument("--sap", type=Path, default=None)
    cp.add_argument("--out", type=Path, default=None)
    cp.add_argument("--workers", type=int, default=24)
    cp.add_argument("--effort", default="medium", choices=["low", "medium", "high"])
    cp.add_argument("--verifier-votes", type=int, default=1, help="independent verifier votes per item (majority wins)")
    cp.add_argument("--repair-rounds", type=int, default=3, help="repair rounds for items the verifier rejects")
    cp.add_argument("--verify-batch", type=int, default=15, help="items judged per verifier call")
    cp.add_argument("--max-calls", type=int, default=2000, help="budget of new (uncached) model calls for this compilation")
    fx = commands.add_parser("extract-facts", help="Quantitative protocol facts (population, accrual, historical outcomes) with quotes.")
    fx.add_argument("--protocol", type=Path, required=True)
    fx.add_argument("--out", type=Path, required=True)
    fx.add_argument("--workers", type=int, default=6)
    fx.add_argument("--votes", type=int, default=3)
    ls = commands.add_parser("lock-studyspec", help="Lock a compiled StudySpec (checksummed, read-only) for the simulation stages.")
    ls.add_argument("--spec", type=Path, required=True, help="compiled StudySpec directory")
    ls.add_argument("--protocol", type=Path, required=True, help="the protocol PDF it was compiled from")
    ls.add_argument("--out", type=Path, required=True, help="new lock directory (must not exist)")
    ls.add_argument("--version", default="1.0.0")
    lf = commands.add_parser("lock-facts", help="Lock extracted protocol facts (checksummed, read-only).")
    lf.add_argument("--facts", type=Path, required=True)
    lf.add_argument("--protocol", type=Path, required=True)
    lf.add_argument("--out", type=Path, required=True)
    lf.add_argument("--version", default="1.0.0")
    bp = commands.add_parser("build-population", help="Milestone 5: source population from the locked StudySpec, facts and V3.")
    bp.add_argument("--studyspec", type=Path, required=True, help="locked StudySpec directory")
    bp.add_argument("--facts", type=Path, required=True, help="locked protocol facts directory")
    bp.add_argument("--out", type=Path, required=True)
    bp.add_argument("--n", type=int, default=10000)
    bp.add_argument("--seed", type=int, default=20260927)
    be = commands.add_parser("build-eligibility", help="Milestone 6: eligibility and feasibility of the locked source population.")
    be.add_argument("--studyspec", type=Path, required=True)
    be.add_argument("--population", type=Path, required=True, help="locked population directory")
    be.add_argument("--out", type=Path, required=True)
    be.add_argument("--seed", type=int, default=20261005, help="seed of the calibration of criteria generated patients cannot decide (A16)")
    bc = commands.add_parser("build-cohorts", help="Milestones 7-8: recruitment, randomization and enrolled cohorts per accrual scenario.")
    bc.add_argument("--studyspec", type=Path, required=True)
    bc.add_argument("--population", type=Path, required=True)
    bc.add_argument("--eligibility", type=Path, required=True)
    bc.add_argument("--out", type=Path, required=True)
    bc.add_argument("--seed", type=int, default=20260927)
    bo = commands.add_parser("build-outcome-model", help="Milestone 11: outcome model (control EFS, effect grid, censoring, adverse events).")
    bo.add_argument("--studyspec", type=Path, required=True)
    bo.add_argument("--facts", type=Path, required=True)
    bo.add_argument("--out", type=Path, required=True)
    rt = commands.add_parser("run-trials", help="Milestones 9-16: simulated trials, registry-style results and success probability.")
    for name in ("studyspec", "population", "eligibility", "cohorts", "outcomes"):
        rt.add_argument(f"--{name}", type=Path, required=True, help=f"locked {name} directory")
    rt.add_argument("--out", type=Path, required=True)
    rt.add_argument("--replicates", type=int, default=1000)
    rt.add_argument("--seed", type=int, default=20260927)
    cr = commands.add_parser("compare-registry", help="Blind comparison of the locked simulation with the trial's registry results.")
    for name in ("results", "population", "cohorts", "outcomes"):
        cr.add_argument(f"--{name}", type=Path, required=True, help=f"locked {name} directory")
    cr.add_argument("--registry", type=Path, required=True, help="registry record JSON (fetched after the predictions were locked)")
    cr.add_argument("--fetched-at", required=True, help="ISO time the registry record was fetched")
    cr.add_argument("--out", type=Path, required=True)
    rb = commands.add_parser("run-binary", help="Milestones 9-16 for per-arm binary decision rules (exact curves, simulated trials).")
    rb.add_argument("--studyspec", type=Path, required=True)
    rb.add_argument("--facts", type=Path, required=True)
    rb.add_argument("--out", type=Path, required=True)
    rb.add_argument("--replicates", type=int, default=2000)
    aug = commands.add_parser("augment-population", help="Add evidence-based baseline variables (ECOG, weight, height) to a population.")
    aug.add_argument("--population", type=Path, required=True)
    aug.add_argument("--studyspec", type=Path, required=True)
    aug.add_argument("--condition-family", type=Path, required=True, help="output of map-protocol-conditions")
    aug.add_argument("--out", type=Path, required=True)
    rj = commands.add_parser("run-journey", help="Longitudinal patient journeys (visits, dosing, AEs, dose modifications, endpoints).")
    for name in ("studyspec", "protocol", "cohorts", "eligibility", "outputs", "safety", "outcomes", "out"):
        rj.add_argument(f"--{name}", type=Path, required=True)
    rj.add_argument("--facts", type=Path, default=None, help="locked protocol facts (a cited progression figure of the same regimen)")
    rj.add_argument("--seed", type=int, default=20260929)
    rni = commands.add_parser("run-ni-binary", help="Two-arm non-inferiority on a binary endpoint (synthesis method).")
    rni.add_argument("--studyspec", type=Path, required=True)
    rni.add_argument("--facts", type=Path, required=True)
    rni.add_argument("--out", type=Path, required=True)
    re_ = commands.add_parser("run-escalation", help="Milestones 9-16 for rule-based dose escalation (grid of hypothetical DLT truths).")
    re_.add_argument("--studyspec", type=Path, required=True)
    re_.add_argument("--out", type=Path, required=True)
    re_.add_argument("--replicates", type=int, default=5000)
    cb = commands.add_parser("compare-registry-binary", help="Blind comparison of locked binary-rule predictions with the registry results.")
    cb.add_argument("--results", type=Path, required=True)
    cb.add_argument("--registry", type=Path, required=True)
    cb.add_argument("--fetched-at", required=True)
    cb.add_argument("--out", type=Path, required=True)
    cu = commands.add_parser("compare-registry-unresolved", help="Record registry results next to a locked but unresolved primary prediction.")
    cu.add_argument("--results", type=Path, required=True)
    cu.add_argument("--results-file", required=True)
    cu.add_argument("--registry", type=Path, required=True)
    cu.add_argument("--fetched-at", required=True)
    cu.add_argument("--out", type=Path, required=True)
    rs = commands.add_parser("run-safety", help="Simulated adverse-event counts per arm from the locked outcome model (any design).")
    rs.add_argument("--outcomes", type=Path, required=True, help="locked outcome model directory")
    rs.add_argument("--cohorts", type=Path, required=True, help="locked cohorts directory")
    rs.add_argument("--out", type=Path, required=True)
    rs.add_argument("--safety-asset", type=Path, help="safety asset V3 directory (default: the outcome model's V2 class-signature rates)")
    rs.add_argument("--seed", type=int, default=20260927)
    xd = commands.add_parser("extend-drug-classes", help="Classify protocol agents missing from the drug-class map (same mapper; base map unchanged).")
    xd.add_argument("--studyspec", type=Path, action="append", required=True)
    xd.add_argument("--created", required=True)
    mc = commands.add_parser("map-protocol-conditions", help="Map protocol condition texts to disease families (the evidence build's mapper; cached).")
    mc.add_argument("--studyspec", type=Path, action="append", required=True)
    bt = commands.add_parser("build-trial-outputs", help="Datasets, registry-style tables and feasibility analyses from the simulated patients.")
    for name in ("studyspec", "eligibility", "cohorts", "outcomes", "safety", "planning"):
        bt.add_argument(f"--{name}", type=Path, required=True, help=f"locked {name} directory")
    bt.add_argument("--results", type=Path)
    bt.add_argument("--accrual-asset", type=Path, default=None, help="default: the asset profile's operational asset")
    bt.add_argument("--seed", type=int, default=20260927)
    bt.add_argument("--out", type=Path, required=True)
    cbl = commands.add_parser("compare-registry-baseline", help="Registry baseline table against the evidence model's 90% predictive intervals.")
    cbl.add_argument("--studyspec", type=Path, required=True)
    cbl.add_argument("--registry", type=Path, required=True)
    cbl.add_argument("--fetched-at", required=True)
    cbl.add_argument("--locked-at", required=True, help="when the protocol's predictions were locked")
    cbl.add_argument("--out", type=Path, required=True)
    cmd = commands.add_parser("compare-registry-medians", help="Registry median time-to-event against the locked control-arm prediction.")
    cmd.add_argument("--outcomes", type=Path, required=True)
    cmd.add_argument("--safety", type=Path, help="locked safety directory (arm agents to identify the control group)")
    cmd.add_argument("--registry", type=Path, required=True)
    cmd.add_argument("--fetched-at", required=True)
    cmd.add_argument("--out", type=Path, required=True)
    cs = commands.add_parser("compare-registry-safety", help="Blind comparison of locked adverse-event predictions with the registry.")
    cs.add_argument("--results", type=Path, required=True, help="locked safety results directory")
    cs.add_argument("--registry", type=Path, required=True)
    cs.add_argument("--fetched-at", required=True)
    cs.add_argument("--out", type=Path, required=True)
    ce = commands.add_parser("compare-registry-escalation", help="Compare locked dose-ladder escalation results with the registry dose result.")
    ce.add_argument("--results", type=Path, required=True)
    ce.add_argument("--registry", type=Path, required=True)
    ce.add_argument("--fetched-at", required=True)
    ce.add_argument("--out", type=Path, required=True)
    cp = commands.add_parser("compare-registry-planning", help="Blind comparison of a locked planning report with the registry timeline.")
    cp.add_argument("--planning", type=Path, required=True, help="locked planning report directory")
    cp.add_argument("--registry", type=Path, required=True)
    cp.add_argument("--fetched-at", required=True)
    cp.add_argument("--out", type=Path, required=True)
    cr = commands.add_parser("compare-registry-ratio-ni", help="Blind comparison of locked ratio-noninferiority predictions with the registry.")
    cr.add_argument("--results", type=Path, required=True, help="locked results directory holding ratio_ni_results.json")
    cr.add_argument("--registry", type=Path, required=True)
    cr.add_argument("--fetched-at", required=True)
    cr.add_argument("--out", type=Path, required=True)
    fz = commands.add_parser("build-feasibility", help="Protocol feasibility from a locked run (funnel, subgroups, evaluability, burden, scenarios).")
    fz.add_argument("--id", required=True)
    fz.add_argument("--version", required=True)
    fz.add_argument("--out", type=Path, required=True)
    pce = commands.add_parser("predict-control-external", help="Hidden-control prediction of a trial outside the corpus, scored against its posted control arm.")
    pce.add_argument("--registry", type=Path, required=True)
    pce.add_argument("--safety", type=Path, required=True, help="locked safety stage (control arm drug classes and family)")
    pce.add_argument("--adsl", type=Path, required=True, help="locked simulated ADSL (protocol-only population)")
    pce.add_argument("--control-arm", required=True)
    pce.add_argument("--experimental-arm", required=True)
    pce.add_argument("--out", type=Path, required=True)
    ba = commands.add_parser("build-accrual-asset",help="Planning asset 1: historical accrual evidence and model (holdouts excluded).")
    ba.add_argument("--raw-dir", type=Path, default=Path("data/raw/ctgov"))
    ba.add_argument("--holdout", type=Path, default=Path("data/manifest/holdout_test_trials.json"))
    ba.add_argument("--family-map", type=Path, default=Path("data/simulation_parameters_v2/hierarchy/disease_family_map.parquet"))
    ba.add_argument("--out", type=Path, default=Path("data/planning_asset_v1/accrual"))
    ba.add_argument("--created", required=True, help="build date (ISO) recorded in the manifest")
    fo = commands.add_parser("fetch-operational-corpus", help="Operational asset V2: registry corpus incl. terminated/withdrawn trials (light fields).")
    fo.add_argument("--out", type=Path, default=Path("data/raw/ctgov_operational"))
    fo.add_argument("--retrieved", required=True, help="retrieval date (ISO) recorded in the manifest")
    bo2 = commands.add_parser("build-operational-asset", help="Operational asset V2: failure model and accrual-rate model (holdouts excluded).")
    bo2.add_argument("--corpus", type=Path, default=Path("data/raw/ctgov_operational"))
    bo2.add_argument("--v1-windows", type=Path, default=Path("data/planning_asset_v1/accrual/windows.json"))
    bo2.add_argument("--holdout", type=Path, default=Path("data/manifest/holdout_test_trials.json"))
    bo2.add_argument("--family-map", type=Path, default=Path("data/simulation_parameters_v2/hierarchy/disease_family_map.parquet"))
    bo2.add_argument("--out", type=Path, default=Path("data/planning_asset_v2/operational"))
    bo2.add_argument("--created", required=True)
    bs3 = commands.add_parser("build-safety-asset-v3", help="Safety asset V3: regimen, dose, phase, age and disease specific adverse-event models.")
    bs3.add_argument("--out", type=Path, default=None, help="default: the asset profile's safety build directory")
    bs3.add_argument("--created", required=True)
    bs3.add_argument("--workers", type=int, default=6)
    bpr = commands.add_parser("build-planning-report", help="Unified trial planning report from locked artefacts.")
    bpr.add_argument("--studyspec", type=Path, required=True)
    bpr.add_argument("--cohorts", type=Path, required=True)
    bpr.add_argument("--eligibility", type=Path, required=True)
    bpr.add_argument("--results", type=Path)
    bpr.add_argument("--outcomes", type=Path)
    bpr.add_argument("--accrual-asset", type=Path)
    bpr.add_argument("--out", type=Path, required=True)
    bpr.add_argument("--blind", action="store_true", help="the trial's registry timeline has not been read")
    lk = commands.add_parser("lock-stage", help="Lock a simulation stage's outputs (checksummed, read-only), chained to its inputs.")
    lk.add_argument("--stage", type=Path, required=True, help="stage output directory")
    lk.add_argument("--out", type=Path, required=True, help="new lock directory (must not exist)")
    lk.add_argument("--kind", required=True)
    lk.add_argument("--version", default="1.0.0")
    lk.add_argument("--input", action="append", default=[], help="label=path of an input file (e.g. an upstream lock.json)")
    lk.add_argument("--code", action="append", default=["clinical_asset/trial"], help="code package to fingerprint")
    release = commands.add_parser("release", help="Repair, check and package the versioned clinical asset.")
    release.add_argument("--version", default="1.0.0")
    discover = commands.add_parser("discover", help="List candidate studies for one condition.")
    discover.add_argument("--condition", required=True)
    discover.add_argument("--limit", type=int, default=20)
    arl = commands.add_parser("build-analysis-results", help="SDTM TU/TR/RS, ADaM ADRS/ADTTE, efficacy and FDA standard safety tables.")
    for name in ("studyspec", "journey", "safety", "eligibility", "outcomes", "out"):
        arl.add_argument(f"--{name}", type=Path, required=True)
    arl.add_argument("--facts", type=Path, default=None)
    arl.add_argument("--seed", type=int, default=20261006)
    rco = commands.add_parser("run-continuous", help="Continuous primary comparison (paired or two-group) from the stated design.")
    rco.add_argument("--studyspec", type=Path, required=True)
    rco.add_argument("--out", type=Path, required=True)
    rsv = commands.add_parser("resolve-protocol", help="Agentic, targeted resolution of a compiled StudySpec's failing items only.")
    rsv.add_argument("--spec", type=Path, required=True, help="compiled StudySpec directory (updated in place)")
    rsv.add_argument("--protocol", type=Path, required=True)
    rsv.add_argument("--votes", type=int, default=3)
    rsv.add_argument("--reverify-all", action="store_true", help="judge every item again before resolving the failures")
    ren = commands.add_parser("run-endpoints", help="Every endpoint of the protocol, computed from the simulated patients (journey).")
    for name in ("studyspec", "journey", "safety", "out"):
        ren.add_argument(f"--{name}", type=Path, required=True)
    ren.add_argument("--facts", type=Path, default=None)
    ren.add_argument("--seed", type=int, default=20261005)
    rni = commands.add_parser("run-ratio-ni", help="Primary engine: geometric-mean-ratio noninferiority (any protocol stating it).")
    rni.add_argument("--studyspec", type=Path, required=True)
    rni.add_argument("--out", type=Path, required=True)
    rv = commands.add_parser("review-run", help="Self-review of a finished run: ask, answer from evidence, correct or ask the human.")
    rv.add_argument("--id", required=True)
    rv.add_argument("--version", required=True)
    aud = commands.add_parser("audit-run", help="Completeness audit of one protocol run: anything undetermined, unresolved or missing.")
    aud.add_argument("--id", required=True)
    aud.add_argument("--version", required=True)
    aud.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "build-analysis-results":
            from .trial.analysis_results import run as run_analysis

            r = run_analysis(args.studyspec, args.journey, args.safety, args.eligibility, args.outcomes, args.out, args.facts, seed=args.seed)
            eff = r["efficacy"] if r["efficacy"].get("status") else {k: v["objective_response"] for k, v in r["efficacy"].items()}
            print(json.dumps({"efficacy": eff, "tables": len(r["safety_tables"])}, indent=1, default=str))
            return 0
        if args.command == "run-continuous":
            from .trial.continuous import run as run_continuous

            r = run_continuous(args.studyspec, args.out)
            print(json.dumps({k: r.get(k) for k in ("status", "reason", "simulated_power_at_design_effect", "design_check")}, indent=1, default=str))
            return 0 if r["status"] == "RESOLVED" else 3
        if args.command == "resolve-protocol":
            from .llm import LunaClient
            from .protocol.resolver import resolve
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM
            from .terminology import UmlsTerminology

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=600, effort="high", max_output_tokens=32000,
                               system=PROTOCOL_SYSTEM, timeout=900)
            terminology = UmlsTerminology()
            r = resolve(args.spec, args.protocol, model, terminology, votes=args.votes, reverify_all=args.reverify_all)
            terminology.save()
            print(json.dumps({"rounds": r["rounds"], "model_calls": r["model_calls"], "remaining": [(x["item"], x["verdict"], x["note"]) for x in r["remaining"]]},
                             indent=1, ensure_ascii=False))
            return 0
        if args.command == "run-endpoints":
            from .trial.endpoints import run as run_endpoints

            doc = run_endpoints(args.studyspec, args.journey, args.safety, args.out, args.facts, seed=args.seed)
            print(json.dumps(doc["counts"]))
            return 0
        if args.command == "run-ratio-ni":
            from .trial.ratio_ni import run as run_ratio_ni

            doc = run_ratio_ni(args.studyspec, args.out)
            print(json.dumps({"status": doc["status"]}, indent=1))
            return 0
        if args.command == "review-run":
            from .trial.review import review_run
            from .trial.studyspec import load_studyspec

            spec, _ = load_studyspec(Path(f"data/locked/{args.id}/studyspec_v{args.version}"))
            doc = review_run(Path(f"data/trial/runs/{args.id}/v{args.version}"), spec)
            print(json.dumps({k: doc[k] for k in ("questions_asked", "problems", "corrections_applied", "rerun_needed", "model_calls")}
                             | {"questions_for_human": len(doc["questions_for_human"])}, indent=1, default=str))
            return 0 if not doc["rerun_needed"] else 10
        if args.command == "audit-run":
            from .trial.audit import audit

            doc = audit(args.id, args.version, args.out)
            print(json.dumps(doc["summary"], indent=1))
            return 0 if doc["summary"]["complete"] else 3
        if args.command == "discover":
            if args.limit < 1:
                parser.error("--limit must be positive.")
            count = 0
            with ClinicalTrialsClient() as registry:
                for candidate in registry.discover(args.condition):
                    nct_id = candidate.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                    if nct_id:
                        print(json.dumps({"nct_id": nct_id}))
                        count += 1
                    if count >= args.limit:
                        break
            return 0
        if args.command == "build-index":
            from .umls_index import build_index

            print(json.dumps(build_index()))
            return 0
        if args.command == "build-database":
            from .batch import build, load_ids
            from .database import load_database

            summary = build(args.manifest, args.holdout, workers=args.workers, limit=args.limit, force=args.force)
            print(json.dumps(summary))
            manifest_ids, _ = load_ids(args.manifest, args.holdout)
            print(json.dumps(load_database(holdout=args.holdout, only=set(manifest_ids))))
            return 0
        if args.command == "extract-facts":
            from .llm import LunaClient
            from .protocol.facts import FactExtractor
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=3000, effort="high",
                               max_output_tokens=32000, system=PROTOCOL_SYSTEM, timeout=900)
            summary = FactExtractor(model, workers=args.workers, votes=args.votes).run(args.protocol, args.out)
            summary["model_calls"] = model.calls
            print(json.dumps(summary, indent=1))
            return 0
        if args.command == "build-population":
            from .llm import LunaClient
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM
            from .trial.population import build_population

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=2000, effort="high",
                               max_output_tokens=32000, system=PROTOCOL_SYSTEM, timeout=900)
            summary = build_population(model, args.studyspec, args.facts, args.out, args.n, args.seed)
            summary["model_calls"] = model.calls
            print(json.dumps(summary, indent=1, default=str))
            return 0
        if args.command == "build-eligibility":
            from .trial.eligibility import build_eligibility
            summary = build_eligibility(args.studyspec, args.population, args.out, args.seed)
            print(json.dumps({k: summary[k] for k in ("patients", "status_counts", "proven_eligible_share", "not_proven_ineligible_share",
                                                      "decisive_exclusions")}, indent=1))
            return 0
        if args.command == "build-cohorts":
            from .trial.recruitment import build_cohorts
            print(json.dumps(build_cohorts(args.studyspec, args.population, args.eligibility, args.out, args.seed), indent=1))
            return 0
        if args.command == "build-outcome-model":
            from .llm import LunaClient
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM
            from .trial.outcomes import build_outcome_model

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=2000, effort="high",
                               max_output_tokens=32000, system=PROTOCOL_SYSTEM, timeout=900)
            summary = build_outcome_model(model, args.studyspec, args.facts, args.out)
            summary["model_calls"] = model.calls
            print(json.dumps(summary, indent=1, default=str))
            return 0
        if args.command == "run-trials":
            from .trial.results import run_results
            summary = run_results(args.studyspec, args.population, args.eligibility, args.cohorts, args.outcomes, args.out,
                                  args.replicates, args.seed)
            print(json.dumps(summary, indent=1, default=str))
            return 0
        if args.command == "compare-registry":
            from .trial.compare import run_compare
            doc = run_compare(args.results, args.population, args.cohorts, args.outcomes, args.registry, args.fetched_at, args.out)
            print(json.dumps({"order_verified": doc["order_verified"], "items": len(doc["items"])}, indent=1))
            return 0
        if args.command == "augment-population":
            from .trial.baseline_extra import augment
            from .trial.studyspec import load_studyspec

            spec, _ = load_studyspec(args.studyspec)
            fam = next(iter(json.loads(args.condition_family.read_text(encoding="utf-8")).values()))["family"][0]
            from .trial.journey_evidence import registry_phase
            phase = registry_phase(spec)
            from .llm import LunaClient

            model = LunaClient(cache_dir=Path("data/cache/llm_subgroups"), max_calls=600, effort="medium", max_output_tokens=16000, timeout=600)
            own = re.search(r"NCT\d{8}", str(args.studyspec))
            print(json.dumps(augment(args.population, fam, phase, args.out, spec=spec, model=model, own_nct=own.group(0) if own else None),
                             indent=1, default=str)[:2000])
            return 0
        if args.command == "run-journey":
            from .llm import LunaClient
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM
            from .trial import schedule_facts
            from .trial.journey import run as run_journey
            from .trial.studyspec import load_studyspec

            spec, _ = load_studyspec(args.studyspec)
            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=60, effort="high", max_output_tokens=16000,
                               system=PROTOCOL_SYSTEM, timeout=900)
            schedule_facts.run(model, args.protocol, spec, args.out)
            doc = run_journey(args.studyspec, args.cohorts, args.eligibility, args.outputs, args.safety, args.outcomes,
                              args.out / "schedule_facts.json", args.out, facts_lock=args.facts, seed=args.seed)
            print(json.dumps(doc["summary"], indent=1, default=str))
            return 0
        if args.command == "run-ni-binary":
            from .trial.noninferiority import run as run_ni

            r = run_ni(args.studyspec, args.facts, None, args.out)
            print(json.dumps({k: r.get(k) for k in ("design", "power_at_protocol_assumption", "p_success_curve", "predicted_response")},
                             indent=1, default=str))
            return 0
        if args.command == "run-binary":
            from .llm import LunaClient
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM
            from .trial.binary import run_binary

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=500, effort="high",
                               max_output_tokens=32000, system=PROTOCOL_SYSTEM, timeout=900)
            summary = run_binary(model, args.studyspec, args.facts, args.out, args.replicates)
            summary["model_calls"] = model.calls
            print(json.dumps(summary, indent=1, default=str))
            return 0
        if args.command == "run-escalation":
            from .trial.escalation import run as run_escalation
            print(json.dumps(run_escalation(args.studyspec, args.out, args.replicates), indent=1))
            return 0
        if args.command == "compare-registry-binary":
            from .trial.compare import run_compare_binary
            doc = run_compare_binary(args.results, args.registry, args.fetched_at, args.out)
            print(json.dumps({"order_verified": doc["order_verified"], "items": len(doc["items"])}, indent=1))
            return 0
        if args.command == "compare-registry-unresolved":
            from .trial.compare import run_compare_unresolved
            doc = run_compare_unresolved(args.results, args.results_file, args.registry, args.fetched_at, args.out)
            print(json.dumps({"order_verified": doc["order_verified"], "measures": len(doc["registry_measures"])}, indent=1))
            return 0
        if args.command == "run-safety":
            from .trial.safety import run_safety
            doc = run_safety(args.outcomes, args.cohorts, args.out, safety_asset=args.safety_asset, seed=args.seed)
            print(json.dumps({"status": doc["status"], "arms": {a["arm_id"]: len(a["events"]) for a in doc["arms"]}}, indent=1))
            return 0
        if args.command == "extend-drug-classes":
            from .llm import LunaClient
            from .trial.safety import extend_class_map

            model = LunaClient(cache_dir=Path("data/cache/llm"), max_calls=50)
            print(json.dumps(extend_class_map(model, args.studyspec, args.created), indent=1))
            return 0
        if args.command == "map-protocol-conditions":
            from .llm import LunaClient
            from .planning.operational import condition_family
            from .trial.studyspec import load_studyspec

            model = LunaClient(cache_dir=Path("data/cache/llm"), max_calls=50)
            out = {}
            for lock in args.studyspec:
                spec, _ = load_studyspec(lock)
                cond = spec["metadata"].get("condition")
                cond = " ".join(((cond.get("text") if isinstance(cond, dict) else cond) or "").split())
                out[str(lock)] = {"condition": cond, "family": condition_family(cond, model)}
            print(json.dumps(out, indent=1))
            return 0
        if args.command == "build-trial-outputs":
            from .trial.outputs import build as build_outputs
            doc = build_outputs(args.studyspec, args.eligibility, args.cohorts, args.outcomes, args.safety, args.planning, args.results,
                                args.out, accrual_asset=args.accrual_asset or __import__('clinical_asset.assets', fromlist=['path']).path('operational'),
                                seed=args.seed)
            print(json.dumps({"datasets": doc["datasets"], "out": str(args.out)}, indent=1))
            return 0
        if args.command == "compare-registry-baseline":
            from .trial.outputs import compare_baseline
            doc = compare_baseline(args.studyspec, args.registry, args.fetched_at, args.locked_at, args.out)
            print(json.dumps(doc.get("summary") or doc.get("status"), indent=1, default=str))
            return 0
        if args.command == "compare-registry-medians":
            from .trial.compare_medians import run as run_medians
            doc = run_medians(args.outcomes, args.registry, args.fetched_at, args.out, args.safety)
            print(json.dumps({"order_verified": doc["order_verified"], "measures": len(doc["items"])}, indent=1))
            return 0
        if args.command == "compare-registry-safety":
            from .trial.safety import run_compare_safety
            doc = run_compare_safety(args.results, args.registry, args.fetched_at, args.out)
            print(json.dumps({k: doc[k] for k in ("order_verified", "registry_at_risk", "matched_terms", "matched_inside_90")}, indent=1))
            return 0
        if args.command == "compare-registry-escalation":
            from .trial.escalation import run_compare as run_escalation_compare
            doc = run_escalation_compare(args.results, args.registry, args.fetched_at, args.out)
            print(json.dumps({"order_verified": doc["order_verified"], "items": [i["status"] for i in doc["items"]]}, indent=1))
            return 0
        if args.command == "compare-registry-ratio-ni":
            from .trial.ratio_ni_compare import compare as compare_ratio_ni

            doc = compare_ratio_ni(args.results, args.registry, args.fetched_at, args.out)
            print(json.dumps({"order_verified": doc["order_verified"], "items": [(i["analysis_id"], i["status"], i.get("conclusion_agrees"))
                                                                               for i in doc["items"]]}, indent=1))
            return 0
        if args.command == "build-feasibility":
            from .trial.feasibility import build as build_feasibility

            doc = build_feasibility(args.id, args.version, args.out)
            print(json.dumps({"eligibility_yield": round(doc["eligibility_yield"], 3), "scenarios": len(doc["scenarios"])}))
            return 0
        if args.command == "predict-control-external":
            from .trial.control_benchmark import external

            doc = external(args.registry, args.safety, args.adsl, args.control_arm, args.experimental_arm, args.out)
            print(json.dumps([(r["outcome"], r["population"], r["method"], round(r["predicted"], 3), r["covered"]) for r in doc["rows"]]))
            return 0
        if args.command == "compare-registry-planning":
            from .llm import LunaClient
            from .planning.validate import run as run_planning_compare
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=200, effort="high",
                               max_output_tokens=32000, system=PROTOCOL_SYSTEM, timeout=900)
            doc = run_planning_compare(args.planning, args.registry, args.fetched_at, args.out, model)
            print(json.dumps({"order_verified": doc["order_verified"], "historical_model": doc["historical_model"]["status"]}, indent=1))
            return 0
        if args.command == "build-accrual-asset":
            from .llm import LunaClient
            from .planning.accrual import build as build_accrual
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=1000, effort="high",
                               max_output_tokens=32000, system=PROTOCOL_SYSTEM, timeout=900)
            manifest = build_accrual(model, args.raw_dir, args.holdout, args.family_map, args.out, args.created)
            manifest["model_calls"] = model.calls
            print(json.dumps({k: v for k, v in manifest.items() if k != "model"}, indent=1, default=str))
            return 0
        if args.command == "fetch-operational-corpus":
            from .planning.operational import fetch_corpus
            print(json.dumps(fetch_corpus(args.out, args.retrieved), indent=1))
            return 0
        if args.command == "build-operational-asset":
            from .llm import LunaClient
            from .planning.operational import build as build_operational
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=2000, effort="high",
                               max_output_tokens=32000, system=PROTOCOL_SYSTEM, timeout=900)
            manifest = build_operational(model, args.corpus, args.v1_windows, args.holdout, args.family_map, args.out, args.created)
            manifest["model_calls"] = model.calls
            print(json.dumps(manifest, indent=1, default=str))
            return 0
        if args.command == "build-safety-asset-v3":
            from .safety3 import build as build_safety3
            from . import assets

            manifest = build_safety3(assets.path("raw_ctgov"), Path("data/manifest/holdout_test_trials.json"), assets.family_map(),
                                     Path("data/spa_work/drug_classes.json"),
                                     assets.path("params_v2") / "toxicity" / "censored_toxicity_parameters.parquet",
                                     args.out or assets.path("safety_build"), args.created, args.workers)
            print(json.dumps(manifest, indent=1))
            return 0
        if args.command == "build-planning-report":
            from .planning.report import build as build_plan
            r = build_plan(args.studyspec, args.cohorts, args.eligibility, args.results, args.outcomes, args.out, args.blind, args.accrual_asset)
            print(json.dumps({"protocol_id": r["protocol_id"], "blind": r["blind"], "out": str(args.out)}, indent=1))
            return 0
        if args.command == "lock-stage":
            from .trial import lock as stage_lock
            inputs = dict(item.split("=", 1) for item in args.input)
            summary_path = next((p for p in sorted(Path(args.stage).glob("*.json")) if "summary" in p.name or "model" in p.name), None)
            status = {"summary": json.loads(summary_path.read_text(encoding="utf-8")).get("summary")} if summary_path else {}
            record = stage_lock.lock(args.stage, args.out, args.kind, args.version, {k: Path(v) for k, v in inputs.items()},
                                     [Path(p) for p in dict.fromkeys(args.code)], status)
            print(json.dumps({"locked": str(args.out), "files": record["files"], "inputs": list(record["inputs"])}, indent=1))
            return 0
        if args.command == "lock-facts":
            from .trial.studyspec import lock_facts
            record = lock_facts(args.facts, args.out, args.protocol, args.version)
            print(json.dumps({"locked": str(args.out), "files": record["files"], "usable": record["status"]["usable"]}, indent=1))
            return 0
        if args.command == "lock-studyspec":
            from .trial.studyspec import lock_studyspec
            record = lock_studyspec(args.spec, args.out, args.protocol, args.version)
            print(json.dumps({"locked": str(args.out), "files": record["files"], "gate": record["status"]["gate"],
                              "not_executable": len(record["status"]["not_executable"])}, indent=1))
            return 0
        if args.command == "compile-protocol":
            from .llm import LunaClient
            from .protocol.compiler import ProtocolCompiler
            from .protocol.schemas import SYSTEM as PROTOCOL_SYSTEM
            from .terminology import UmlsTerminology

            model = LunaClient(cache_dir=Path("data/cache/llm_protocol"), max_calls=args.max_calls, effort=args.effort,
                               max_output_tokens=32000, system=PROTOCOL_SYSTEM, timeout=900)
            terminology = UmlsTerminology()
            started = time.monotonic()
            result = ProtocolCompiler(model, terminology, workers=args.workers, critical_votes=args.verifier_votes,
                                      repair_rounds=args.repair_rounds, verify_batch=args.verify_batch).compile(args.protocol, args.sap, args.out)
            result["seconds"] = round(time.monotonic() - started)
            terminology.save()
            result["model_calls"], result["input_tokens"], result["output_tokens"] = model.calls, model.input_tokens, model.output_tokens
            print(json.dumps(result, indent=1, default=str))
            return 0
        if args.command == "build-parameters-v3":
            from .spa3.build import build as build_v3

            print(json.dumps(build_v3(workers=args.workers, resume=args.resume, out_dir=args.out, exclude_file=args.exclude,
                                      raw_dir=args.raw_dir), indent=1, default=str))
            return 0
        if args.command == "build-parameters-v2":
            from .spa2.build import build

            print(json.dumps(build(), indent=1, default=str))
            return 0
        if args.command == "build-parameters":
            from .spa.fit import build_parameter_asset

            print(json.dumps(build_parameter_asset(), indent=1, default=str))
            return 0
        if args.command == "release":
            from .release import build_release

            print(json.dumps(build_release(args.version), indent=1, default=str))
            return 0
        if args.command == "load-database":
            from .database import load_database

            print(json.dumps(load_database()))
            return 0
        result = extract_trial(
            args.nct_id, args.data_dir, args.output, not args.skip_publications, not args.no_model,
            args.fuzzy, args.ner_models,
        )
        print(json.dumps(result))
        return 2 if "excluded" in result else 0
    except Exception as error:  # noqa: BLE001
        print(f"clinical-asset failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
