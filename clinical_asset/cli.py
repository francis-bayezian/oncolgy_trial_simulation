"""Read-only source retrieval and local clinical JSON extraction.

No command writes to a database. ``extract`` writes three local files:
the clinical asset, its extraction audit, and the raw registry record.
"""

import argparse
import json
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
    pa = commands.add_parser("build-planning-asset", help="Classify historical accrual date quality, excluding holdouts.")
    pa.add_argument("--manifest", type=Path, default=Path("data/manifest/subset_treatment_phase23_result_pub.json"))
    pa.add_argument("--holdout", type=Path, default=Path("data/manifest/holdout_test_trials.json"))
    pa.add_argument("--raw-dir", type=Path, default=Path("data/raw/ctgov"))
    pa.add_argument("--out", type=Path, default=Path("data/planning_asset_v1/accrual"))
    po = commands.add_parser("build-planning-operations", help="Extract screening and retention evidence from registry flow.")
    po.add_argument("--manifest", type=Path, default=Path("data/manifest/subset_treatment_phase23_result_pub.json"))
    po.add_argument("--holdout", type=Path, default=Path("data/manifest/holdout_test_trials.json"))
    po.add_argument("--raw-dir", type=Path, default=Path("data/raw/ctgov"))
    po.add_argument("--out", type=Path, default=Path("data/planning_asset_v1/operations"))
    pp = commands.add_parser("build-planning-report", help="Build one unified planning report from locked protocol inputs.")
    pp.add_argument("--studyspec", type=Path, required=True)
    pp.add_argument("--asset", type=Path, default=Path("data/planning_asset_v1/accrual"))
    pp.add_argument("--cohorts", type=Path)
    pp.add_argument("--eligibility", type=Path)
    pp.add_argument("--operations", type=Path, default=Path("data/planning_asset_v1/operations"))
    pp.add_argument("--results", type=Path, help="Optional locked binary or time-to-event simulation results")
    pp.add_argument("--outcomes", type=Path, help="Locked outcome model for a conditional event calendar")
    pp.add_argument("--event-threshold", type=int, action="append", default=[], help="Scenario event count; may be repeated")
    pp.add_argument("--scenario-results", type=Path, help="Optional scenario output directory to include in unified report")
    pp.add_argument("--out", type=Path, required=True)
    pp.add_argument("--draws", type=int, default=5000)
    ps = commands.add_parser("simulate-planning-scenarios", help="Compare explicit operational assumptions for one locked protocol.")
    ps.add_argument("--studyspec", type=Path, required=True)
    ps.add_argument("--scenarios", type=Path, required=True, help="JSON file with a scenarios array")
    ps.add_argument("--outcomes", type=Path, help="Locked outcome model, required for event thresholds")
    ps.add_argument("--out", type=Path, required=True)
    ps.add_argument("--draws", type=int, default=5000)
    commands.add_parser("build-parameters-v2", help="Milestone 2: hierarchical borrowing, survival, censored toxicity.")
    v3 = commands.add_parser("build-parameters-v3", help="Milestone 3: exact binomial calibration, survival fusion, baseline generator.")
    v3.add_argument("--workers", type=int, default=6)
    v3.add_argument("--resume", action="store_true", help="Reuse stored 3A fits and calibration.")
    cp = commands.add_parser("compile-protocol", help="Milestone 4: compile a protocol (+ SAP) PDF into an executable StudySpec.")
    cp.add_argument("--protocol", type=Path, required=True)
    cp.add_argument("--sap", type=Path, default=None)
    cp.add_argument("--out", type=Path, default=None)
    cp.add_argument("--workers", type=int, default=6)
    cp.add_argument("--effort", default="high", choices=["low", "medium", "high"])
    cp.add_argument("--verifier-votes", type=int, default=3, help="independent verifier votes per CRITICAL item (majority wins)")
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
    args = parser.parse_args(argv)

    try:
        if args.command == "build-planning-asset":
            from .planning.asset import build
            print(json.dumps(build(args.manifest, args.holdout, args.raw_dir, args.out), indent=1))
            return 0
        if args.command == "build-planning-operations":
            from .planning.operations import build
            print(json.dumps(build(args.manifest, args.holdout, args.raw_dir, args.out), indent=1))
            return 0
        if args.command == "build-planning-report":
            from .planning.report import build
            result = build(args.studyspec, args.asset, args.out, args.cohorts, args.eligibility,
                           args.draws, operations_dir=args.operations, results_dir=args.results,
                           outcomes_dir=args.outcomes, event_thresholds=args.event_threshold,
                           scenario_dir=args.scenario_results)
            print(json.dumps({"protocol_id": result["protocol_id"], "status": result["accrual"]["status"]}))
            return 0
        if args.command == "simulate-planning-scenarios":
            from .planning.scenarios import simulate
            result = simulate(args.studyspec, args.scenarios, args.out, args.outcomes, args.draws)
            print(json.dumps({"protocol_id": result["protocol_id"], "scenarios": len(result["scenarios"])}))
            return 0
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
            summary = build_eligibility(args.studyspec, args.population, args.out)
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
            result = ProtocolCompiler(model, terminology, workers=args.workers, critical_votes=args.verifier_votes).compile(args.protocol, args.sap, args.out)
            terminology.save()
            result["model_calls"], result["input_tokens"], result["output_tokens"] = model.calls, model.input_tokens, model.output_tokens
            print(json.dumps(result, indent=1, default=str))
            return 0
        if args.command == "build-parameters-v3":
            from .spa3.build import build as build_v3

            print(json.dumps(build_v3(workers=args.workers, resume=args.resume), indent=1, default=str))
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
