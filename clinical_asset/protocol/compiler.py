"""Protocol compiler: protocol PDF (+ optional SAP PDF) -> StudySpec + audit + review list.

Pipeline
  1. ingest     pages, lines, tables, numbered section hierarchy (ingest.py)
  2. classify   every section heading -> controlled section types (one model call)
  3. extract    per component, section by section in bounded chunks (schemas.py), in parallel
  4. normalise  quotes -> typed rules; every quote verified against the PDF with page provenance;
                variables linked to UMLS; numbers/operators/units parsed deterministically
  5. assemble   StudySpec components, merged across chunks
  6. validate   structure, cross-references, completeness, executability (every EXECUTABLE rule
                is evaluated on synthetic patients); anything unresolved is REVIEW_REQUIRED

Outputs (data/protocol_specs/<id>/): studyspec.json, audit.json, review_required.json,
validation_report.json, extraction_raw.json.
"""

import datetime
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import qualifiers
from . import design_rules as drules
from . import expressions as ex
from . import ir, render, report, typecheck
from . import schemas as sc
from .ingest import Document, Section, extract, normalise
from .normalise import (
    Provenance,
    Source,
    Variables,
    build_tree,
    canonical_label,
    compile_tree,
    dose_basis,
    parse_days,
    parse_quantity,
)

COMPILER_VERSION = "protocol-compiler-1.1.0"
OUT = Path("data/protocol_specs")
CHUNK_CHARS = 80000  # one coherent read per component where it fits; split only very long protocols

TASKS = {
    "eligibility": ({"eligibility"}, sc.ELIGIBILITY, sc.ELIGIBILITY_INSTRUCTIONS),
    "stratification": ({"randomization", "stratification"}, sc.STRATIFICATION, sc.STRATIFICATION_INSTRUCTIONS),
    "treatment": ({"treatment_plan", "radiation_plan", "supportive_care"}, sc.TREATMENT, sc.TREATMENT_INSTRUCTIONS),
    "dose_modification": ({"dose_modification"}, sc.DOSE_MODIFICATION, sc.DOSE_MODIFICATION_INSTRUCTIONS),
    "discontinuation": ({"discontinuation"}, sc.DISCONTINUATION, sc.DISCONTINUATION_INSTRUCTIONS),
    "statistics": ({"statistics", "sample_size", "interim_analysis", "endpoints"}, sc.STATISTICS, sc.STATISTICS_INSTRUCTIONS),
    "design_rules": ({"statistics", "sample_size", "interim_analysis", "schema_design", "treatment_plan"}, drules.DESIGN_RULES,
                     drules.DESIGN_RULES_INSTRUCTIONS),
    "response": ({"response_criteria"}, sc.RESPONSE, sc.RESPONSE_INSTRUCTIONS),
    "definitions": ({"definitions_scale", "definitions_staging", "definitions_grading"}, sc.DEFINITIONS, sc.DEFINITIONS_INSTRUCTIONS),
}

# Components whose critical items can be re-extracted one at a time, and the task that extracts them.
REPAIRABLE = {"eligibility": "eligibility", "dose_modification": "dose_modification", "stratification": "stratification",
              "treatment": "treatment", "radiotherapy": "treatment", "endpoints": "statistics", "analyses": "statistics",
              "decision_rules": "design_rules"}

# ----------------------------------------------------------------------------- helpers


REPAIR_ROUNDS = 5  # automatic repair rounds for every failing item (L030)

def _raw_treatment_gaps(treatment: list[dict], dose_rules: list[dict]) -> list[str]:
    """Treatment gaps in raw extraction outputs (see typecheck.treatment_gaps); phases are identified by name."""
    phases: dict[str, str] = {}
    administered: set[str] = set()
    agents: set[str] = set()
    for r in treatment:
        o = r["output"]
        local = {p["phase_id"]: _key(p["name_quote"]) for p in o["phases"]}
        for p in o["phases"]:
            phases.setdefault(_key(p["name_quote"]), p["name_quote"])
        for it in o["interventions"]:
            administered.add(local.get(it["phase_id"], ""))
            agents |= {canonical_label(it["canonical_agent"]) or "", _key(it["agent_quote"])}
        for c in o.get("radiotherapy") or []:
            administered.add(local.get(c["phase_id"], ""))
            agents |= {canonical_label(t["canonical_target"]) or "" for t in c["targets"]}
    dose_agents = {canonical_label(m["canonical_agent"]) or _key(m["agent_quote"]) for r in dose_rules for m in r["output"]["rules"]}
    return typecheck.treatment_gaps(list(phases.items()), administered, agents, dose_agents)


def _section_payload(sections: list[Section]) -> dict:
    return {"sections": [{"number": s.number, "title": s.title, "text": s.text(),
                          "tables": [{"page": t.page, "rows": t.rows} for t in s.tables]} for s in sections]}


def _chunks(sections: list[Section], limit: int = CHUNK_CHARS) -> list[list[Section]]:
    """Group consecutive sections, keeping a level-2 subtree together where it fits."""
    groups: list[list[Section]] = []
    current: list[Section] = []
    size = 0
    for s in sections:
        n = len(s.text()) + sum(len(json.dumps(t.rows)) for t in s.tables) + 100
        top2 = ".".join(s.number.split(".")[:2])
        same_subtree = current and ".".join(current[-1].number.split(".")[:2]) == top2
        if current and size + n > limit and not (same_subtree and size + n <= 2 * limit):
            groups.append(current)
            current, size = [], 0
        current.append(s)
        size += n
    if current:
        groups.append(current)
    return groups


def _key(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalise(text or "")).strip()


# ----------------------------------------------------------------------------- compiler


class ProtocolCompiler:
    def __init__(self, model: Any, terminology: Any | None = None, workers: int = 6, critical_votes: int = 3) -> None:
        self.model = model
        self.terminology = terminology
        self.workers = workers
        self.critical_votes = max(1, critical_votes)  # independent verifier votes per CRITICAL item

    # ---------------------------------------------------------------- stages
    def classify(self, doc: Document) -> dict[str, list[str]]:
        headings = [{"number": s.number, "title": s.title, "preview": re.sub(r"\s+", " ", s.text())[:160]}
                    for s in doc.sections]
        out = self.model.extract("protocol_section_types", sc.CLASSIFY,
                                 {"instructions": sc.CLASSIFY_INSTRUCTIONS, "headings": headings})
        known = {s.number for s in doc.sections}
        types = {a["number"]: sorted(set(a["types"])) for a in out["assignments"] if a["number"] in known}
        for s in doc.sections:
            types.setdefault(s.number, ["other"])
        return types

    def _call(self, task: str, schema: dict, instructions: str, sections: list[Section], extra: dict | None = None) -> dict:
        payload = {"instructions": instructions, **_section_payload(sections), **(extra or {})}
        return self.model.extract(f"protocol_{task}", schema, payload)

    def complete_treatment(self, by_doc: dict[str, Document], raw_results: list[dict]) -> dict:
        """Completeness pass. The verifier judges only what was extracted, so an administration the
        extraction left out would never be reported. Gaps are computed from the raw outputs (phases with
        no administration, agents with dose rules but no administration) and each treatment chunk is
        extracted once more with the gaps named. Its results are merged by the normal builder."""
        treatment = [r for r in raw_results if r["task"] == "treatment" and "output" in r]
        gaps = _raw_treatment_gaps(treatment, [r for r in raw_results if r["task"] == "dose_modification" and "output" in r])
        self._completion = {"gaps_before": gaps, "results": []}
        if not gaps or not treatment:
            return self._completion
        _, schema, instructions = TASKS["treatment"]
        compiled = [{"phase": p["name_quote"], "arms": p["arm_label_quotes"],
                     "interventions": [f"{i['agent_quote']} {i['dose_quote']} {i['dose_unit_quote']}".strip()
                                       for i in r["output"]["interventions"] if i["phase_id"] == p["phase_id"]]}
                    for r in treatment for p in r["output"]["phases"]]

        def run(r):
            doc = by_doc[r["document"]]
            sections = [doc.section(n) for n in r["sections"] if doc.section(n)]
            try:
                out = self._call("treatment", schema, sc.COMPLETE_PREFIX + instructions, sections,
                                 {"completeness": {"missing": gaps, "already_compiled": compiled}})
                return {"task": "treatment", "sections": r["sections"], "document": r["document"], "output": out, "completion": True}
            except Exception as exc:  # noqa: BLE001 - the gaps then stay and fail the gate
                return {"task": "treatment", "sections": r["sections"], "document": r["document"], "error": repr(exc)}
        with ThreadPoolExecutor(self.workers) as pool:
            self._completion["results"] = list(pool.map(run, treatment))
        return self._completion

    def extract_components(self, doc: Document, types: dict[str, list[str]]) -> list[dict]:
        jobs = []
        front = Section("front", "Front matter", 0, 1, doc.sections[0].page_start if doc.sections else 1, 0.0, doc.front_matter, [])
        jobs.append(("metadata", [front], sc.METADATA, sc.METADATA_INSTRUCTIONS, None))
        for task, (wanted, schema, instructions) in TASKS.items():
            chosen = [s for s in doc.sections if set(types.get(s.number, [])) & wanted and (s.lines or s.tables)]
            for group in _chunks(chosen):
                jobs.append((task, group, schema, instructions, None))
        for s in doc.sections:
            if set(types.get(s.number, [])) & {"assessments", "follow_up"}:
                for i, table in enumerate(s.tables):
                    jobs.append(("assessments", [s], sc.ASSESSMENTS, sc.ASSESSMENTS_INSTRUCTIONS,
                                 {"table": {"page": table.page, "rows": table.rows}, "table_index": i}))

        def run(job):
            task, group, schema, instructions, extra = job
            try:
                return {"task": task, "sections": [s.number for s in group], "extra": extra,
                        "output": self._call(task, schema, instructions, group, extra)}
            except Exception as exc:  # noqa: BLE001 - recorded and surfaced as a REVIEW_REQUIRED gap
                return {"task": task, "sections": [s.number for s in group], "extra": extra, "error": repr(exc)}
        with ThreadPoolExecutor(self.workers) as pool:
            return list(pool.map(run, jobs))

    # ---------------------------------------------------------------- assembly
    def compile(self, protocol: Path, sap: Path | None = None, out_dir: Path | None = None) -> dict:
        doc = extract(protocol)
        docs = [doc]
        if sap is not None:
            docs.append(extract(sap))
        started = datetime.datetime.now(datetime.UTC).isoformat()
        all_types: dict[str, dict[str, list[str]]] = {}
        raw_results: list[dict] = []
        for d in docs:
            types = self.classify(d)
            all_types[d.doc_id] = types
            self._types = all_types
            for r in self.extract_components(d, types):
                r["document"] = d.doc_id
                raw_results.append(r)
        by_doc = {d.doc_id: d for d in docs}
        completion = self.complete_treatment(by_doc, raw_results)
        raw_results += completion["results"]
        prov = Provenance(doc, COMPILER_VERSION)
        variables = Variables(self.terminology)
        review: list[dict] = []
        spec: dict[str, Any] = {"spec_version": "1.1.0", "compiler_version": COMPILER_VERSION}

        def source_of(r: dict) -> Source:
            d = by_doc[r["document"]]
            prov.doc = d
            if r["sections"] == ["front"]:
                return Source.of([Section("front", "Front matter", 0, 1, 1, 0.0, d.front_matter, [])])
            return Source.of([d.section(n) for n in r["sections"] if d.section(n)])

        def flag(component: str, item_id: str, reason: str, provenance: str | None = None, text: str | None = None) -> None:
            review.append({"component": component, "item": item_id, "reason": reason, "provenance": provenance, "text": text})

        for r in raw_results:
            if "error" in r:
                flag(r["task"], ",".join(r["sections"]), f"extraction failed: {r['error']}")
        results = [r for r in raw_results if "output" in r]

        def of(task: str) -> list[dict]:
            return [r for r in results if r["task"] == task]

        spec["metadata"], spec["arms"], spec["amendment_history"] = self._metadata(of("metadata"), source_of, prov, flag)
        spec["eligibility"] = self._eligibility(of("eligibility"), source_of, prov, variables, flag)
        spec["randomization"], spec["stratification"] = self._stratification(of("stratification"), source_of, prov, variables, flag)
        spec["treatment_phases"], spec["interventions"], spec["radiotherapy"] = self._treatment(
            of("treatment"), source_of, prov, variables, flag)
        spec["dose_modifications"] = self._dose_mods(of("dose_modification"), source_of, prov, variables, flag)
        spec["assessments"] = self._assessments(of("assessments"), source_of, prov, flag)
        spec["discontinuation_rules"] = self._discontinuation(of("discontinuation"), source_of, prov, flag)
        spec.update(self._statistics(of("statistics"), source_of, prov, flag))
        spec["decision_rules"] = self._decision_rules(of("design_rules"), source_of, prov, spec["arms"])
        spec["response_criteria"] = self._response(of("response"), source_of, prov, flag)
        spec["grade_definitions"], spec["definitions"] = self._definitions(of("definitions"), source_of, prov, variables, flag)
        self._link_grades(spec)
        spec["resolutions"] = self._resolve(spec, docs, prov, flag)
        qualifiers.enrich(spec, docs)                    # qualifiers the structure lost, from the verified quotes (L030)
        spec["variables"] = sorted(variables.registry.values(), key=lambda v: v["key"])
        self._runtime_and_criticality(spec)
        static, global_static = typecheck.check(spec)
        self._apply_static(spec, static, flag)
        spec["static_issues"] = global_static
        for g in global_static:
            flag("static_check", "spec", g)
        self.verify(spec, docs, flag)
        repaired: list[str] = []
        failing_before = None
        for _round in range(REPAIR_ROUNDS):              # resolve loop (L030): stop when all faithful or no progress
            failing = sorted(_item_id(i) for _, i, _ in self._items(spec) if i.get("semantic_status") in {"INCOMPLETE", "INCORRECT", "UNVERIFIED"})
            if not failing or failing == failing_before:
                break
            failing_before = failing
            fixed = self.repair(spec, docs, prov, variables, review, flag)
            unverified = {_item_id(i) for _, i, _ in self._items(spec) if i.get("semantic_status") == "UNVERIFIED"}
            if not fixed and not unverified:
                break
            repaired += [i for i in fixed if i not in repaired]
            qualifiers.enrich(spec, docs)
            spec["variables"] = sorted(variables.registry.values(), key=lambda v: v["key"])
            self._runtime_and_criticality(spec)
            static, global_static = typecheck.check(spec)
            self._apply_static(spec, {k: v for k, v in static.items() if k in set(repaired)}, lambda *a, **k: None)
            for component, item, _ in self._items(spec):
                if _item_id(item) in set(repaired):
                    for issue in item["static_issues"]:
                        flag("static_check", _item_id(item), issue)
            spec["static_issues"] = global_static
            self.verify(spec, docs, flag, only=set(fixed) | unverified)     # repaired items and items never judged
        spec["repaired_items"] = repaired
        spec["unresolved_extraction"] = _classify_residual(spec, self._items(spec))
        spec["treatment_completion"] = {"gaps_before": completion["gaps_before"],
                                        "passes": len([r for r in completion["results"] if "output" in r]),
                                        "gaps_after": [g for g in spec["static_issues"] if g.startswith("treatment incomplete")]}
        for x in review:
            x.pop("_after_repair", None)
        self._finalise_status(spec)
        validation = self.validate(spec, prov, review)
        spec["gate"] = validation["gate"]
        spec["status"] = validation["gate"]["result"]
        protocol_id = (spec["metadata"].get("protocol_id") or {}).get("text") or doc.doc_id[:12]
        target = out_dir or OUT / re.sub(r"[^A-Za-z0-9_.-]+", "_", protocol_id)
        target.mkdir(parents=True, exist_ok=True)
        audit = {"compiler_version": COMPILER_VERSION, "started": started,
                 "finished": datetime.datetime.now(datetime.UTC).isoformat(),
                 "documents": [{"path": d.path, "sha256": d.doc_id, "pages": d.pages, "sections": len(d.sections),
                                "extractor_version": d.extractor_version, "removed_running_lines": d.removed_running_lines}
                               for d in docs],
                 "model": {"name": getattr(self.model, "__class__", type(self.model)).__name__,
                           "effort": getattr(self.model, "effort", None), "calls": getattr(self.model, "calls", None)},
                 "section_types": all_types, "provenance": prov.records}
        (target / "studyspec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
        (target / "audit.json").write_text(json.dumps(audit, indent=1, ensure_ascii=False), encoding="utf-8")
        (target / "review_required.json").write_text(json.dumps(review, indent=1, ensure_ascii=False), encoding="utf-8")
        (target / "validation_report.json").write_text(json.dumps(validation, indent=1, ensure_ascii=False), encoding="utf-8")
        (target / "extraction_raw.json").write_text(json.dumps(raw_results, indent=1, ensure_ascii=False), encoding="utf-8")
        (target / "studyspec_review.md").write_text(report.build(spec, audit, review, validation), encoding="utf-8")
        (target / "unresolved_extraction.json").write_text(json.dumps(spec["unresolved_extraction"], indent=1, ensure_ascii=False), encoding="utf-8")
        _to_agent_backlog(protocol_id, spec["unresolved_extraction"])
        return {"output": str(target), "status": spec["status"], "review_items": len(review), **validation["summary"]}

    # ---------------------------------------------------------------- components
    def _q(self, prov: Provenance, source: Source, quote: str | None, component: str, field_name: str) -> dict | None:
        if not quote:
            return None
        # Evidence, labels and descriptions document where something came from; nothing is parsed from
        # them, so a quote stitched from verified fragments is acceptable there (and labelled as such).
        documentary = field_name in {"evidence", "label", "description", "definition", "condition", "start", "instruction"}
        rec = prov.add(source, quote, component, field_name, allow_fragments=documentary)
        return {"text": quote, "provenance": rec["id"], "verified": rec["verified"]}

    def _quantity(self, prov, src, value_quote, unit_quote, component, field_name) -> dict | None:
        parsed = parse_quantity(value_quote, unit_quote or None)
        quote = self._q(prov, src, value_quote, component, field_name)
        if unit_quote:
            self._q(prov, src, unit_quote, component, field_name + "_unit")
        return _with_q(parsed, quote)

    def _metadata(self, results, source_of, prov, flag):
        meta: dict[str, Any] = {}
        arms: dict[str, dict] = {}
        history = []
        for r in results:
            src, o = source_of(r), r["output"]
            for f in ("protocol_id", "title", "phase", "sponsor", "version_date", "amendment", "activation_date",
                      "closure_date", "condition", "population", "design_summary"):
                q = self._q(prov, src, o.get(f + "_quote"), "metadata", f)
                if q:
                    meta[f] = q
            for a in o["arms"]:
                label = self._q(prov, src, a["label_quote"], "arms", "label")
                if not label:
                    continue
                arms[_key(a["label_quote"])] = {"arm_id": f"ARM{len(arms) + 1}", "label": label,
                                                "canonical_arm": canonical_label(a["canonical_arm"]) or canonical_label(a["label_quote"]),
                                                "description": self._q(prov, src, a["description_quote"], "arms", "description"),
                                                "status": a["status"], "status_evidence": self._q(prov, src, a["status_quote"], "arms", "status")}
                if a["status"] == "unclear":
                    flag("arms", a["label_quote"], "arm status (open/closed) not stated clearly")
            for note in o["amendment_notes"]:
                history.append({"amendment": self._q(prov, src, note["amendment_quote"], "amendment_history", "amendment"),
                                "change": self._q(prov, src, note["change_quote"], "amendment_history", "change"),
                                "date": self._q(prov, src, note["date_quote"], "amendment_history", "date"),
                                "use": "provenance only; this StudySpec compiles the current version"})
        return meta, list(arms.values()), history

    def _logic(self, nodes, src, prov, variables, component, item, flag):
        if not nodes:
            return None, "EXECUTABLE"
        tree_raw, structure = build_tree(nodes)
        issues: list[str] = list(structure)
        tree = compile_tree(tree_raw, src, prov, variables, component, issues)
        for leaf in ex.leaves(tree):
            if leaf.get("status") != "EXECUTABLE":
                flag(component, item, "; ".join(leaf.get("issues") or ["not executable"]), leaf.get("provenance"), leaf.get("text"))
        for i in structure:
            flag(component, item, i)
        return tree, ("EXECUTABLE" if not structure and ex.status_of(tree) == "EXECUTABLE" else "REVIEW_REQUIRED")

    def _eligibility(self, results, source_of, prov, variables, flag):
        criteria = []
        seen = set()
        for r in results:
            src = source_of(r)
            for c in r["output"]["criteria"]:
                sig = (c["kind"], _key(c["evidence_quote"]))
                if sig in seen:
                    continue
                seen.add(sig)
                cid = f"EL{len(criteria) + 1:03d}"
                entry = {"criterion_id": cid, "kind": c["kind"], "modality": c["modality"],
                         "label": self._q(prov, src, c["label_quote"], "eligibility", "label"),
                         "evidence": self._q(prov, src, c["evidence_quote"], "eligibility", "evidence"), "sections": r["sections"], "document": r["document"]}
                if c["kind"] in {"inclusion", "exclusion", "timing"} and c["nodes"]:
                    entry["logic"], entry["compile_status"] = self._logic(c["nodes"], src, prov, variables, "eligibility", cid, flag)
                criteria.append(entry)
        return criteria

    def _stratification(self, results, source_of, prov, variables, flag):
        randomization: dict[str, Any] = {}
        strata, factors = [], []
        for r in results:
            src, o = source_of(r), r["output"]
            rz = o["randomization"]
            for f in ("method", "timing", "ratio"):
                q = self._q(prov, src, rz[f + "_quote"], "randomization", f)
                if q and f not in randomization:
                    randomization[f] = q
            if rz["arm_label_quotes"]:
                randomization["arms"] = [self._q(prov, src, a, "randomization", "arm") for a in rz["arm_label_quotes"]]
            for f in o["factors"]:
                q = self._q(prov, src, f["factor_quote"], "stratification", "factor")
                if q and _key(q["text"]) not in {_key(x["text"]) for x in factors}:
                    factors.append({**q, "canonical_factor": canonical_label(f["canonical_factor"])})
            for s in o["strata"]:
                if _key(s["label_quote"]) in {_key(x["label"]["text"]) for x in strata if x.get("label")}:
                    continue
                sid = f"ST{len(strata) + 1}"
                logic, status = self._logic(s["nodes"], src, prov, variables, "stratification", sid, flag)
                strata.append({"stratum_id": sid, "label": self._q(prov, src, s["label_quote"], "stratification", "label"),
                               "logic": logic, "compile_status": status, "sections": r["sections"], "document": r["document"]})
        if randomization.get("ratio"):
            randomization["allocation"] = _ratio(randomization["ratio"]["text"])
        return randomization, {"factors": factors, "strata": strata}

    def _treatment(self, results, source_of, prov, variables, flag):
        phases: dict[str, dict] = {}
        interventions, courses = [], []
        seen = set()
        before_completion: tuple[set, bool] | None = None
        for r in results:
            src, o = source_of(r), r["output"]
            local: dict[str, str] = {}
            if r.get("completion") and before_completion is None:
                # what the ordinary extraction already administered; a completeness pass only fills gaps
                before_completion = ({it["phase_id"] for it in interventions} | {c["phase_id"] for c in courses},
                                     any(c["phase_id"] is None for c in courses))
            for p in o["phases"]:
                name_key = _key(p["name_quote"]) + "|" + "|".join(sorted(_key(a) for a in p["arm_label_quotes"]))
                if r.get("completion"):  # a completeness pass adds to the phases already compiled, matched by name
                    name_key = next((k for k in phases if k.split("|")[0] == _key(p["name_quote"])), name_key)
                if name_key not in phases:
                    pid = f"PH{len(phases) + 1}"
                    start_logic, start_status = self._logic(p["start_nodes"], src, prov, variables, "treatment_phases", pid, flag)
                    phases[name_key] = {
                        "phase_id": pid, "name": self._q(prov, src, p["name_quote"], "treatment_phases", "name"),
                        "canonical_phase": canonical_label(p["canonical_phase"]) or canonical_label(p["name_quote"]),
                        "arms": [self._q(prov, src, a, "treatment_phases", "arm") for a in p["arm_label_quotes"]],
                        "sequence_number": p["sequence_number"],
                        "duration": self._quantity(prov, src, p["duration_quote"], "", "treatment_phases", "duration"),
                        "cycle_length": self._quantity(prov, src, p["cycle_length_quote"], "", "treatment_phases", "cycle_length"),
                        "cycle_count": _with_q({"value": ex.parse_number(p["cycle_count_quote"])} if ex.parse_number(p["cycle_count_quote"]) is not None else None,
                                               self._q(prov, src, p["cycle_count_quote"], "treatment_phases", "cycle_count")),
                        "cycle_start_day": _with_q({"value": ex.parse_number(p["cycle_start_day_quote"])} if ex.parse_number(p["cycle_start_day_quote"]) is not None else None,
                                                   self._q(prov, src, p["cycle_start_day_quote"], "treatment_phases", "cycle_start_day")),
                        "max_delay": self._quantity(prov, src, p["max_delay_quote"], "", "treatment_phases", "max_delay"),
                        "start_condition": {"logic": start_logic, "compile_status": start_status,
                                            "text": self._q(prov, src, p["start_quote"], "treatment_phases", "start")} if (start_logic or p["start_quote"]) else None,
                        "evidence": self._q(prov, src, p["evidence_quote"], "treatment_phases", "evidence"), "sections": r["sections"], "document": r["document"]}
                local[p["phase_id"]] = phases[name_key]["phase_id"]
            for it in o["interventions"]:
                sig = (_key(it["agent_quote"]), _key(it["dose_quote"]), _key(it["dose_unit_quote"]),
                       tuple(sorted(_key(a) for a in it["arm_label_quotes"])), local.get(it["phase_id"], it["phase_id"]))
                if sig in seen:
                    continue
                seen.add(sig)
                iid = f"TX{len(interventions) + 1:03d}"
                dose = ex.parse_number(it["dose_quote"])
                unit = ex.parse_unit(it["dose_unit_quote"])
                entry = {
                    "intervention_id": iid, "phase_id": local.get(it["phase_id"]), "category": it["category"],
                    "modality": it["modality"], "canonical_agent": canonical_label(it["canonical_agent"]) or canonical_label(it["agent_quote"]),
                    "agent": self._q(prov, src, it["agent_quote"], "interventions", "agent"),
                    "arms": [self._q(prov, src, a, "interventions", "arm") for a in it["arm_label_quotes"]],
                    "dose": {"value": dose, "unit": unit, "basis": dose_basis(unit),
                             "quote": self._q(prov, src, it["dose_quote"], "interventions", "dose"),
                             "unit_quote": self._q(prov, src, it["dose_unit_quote"], "interventions", "dose_unit")},
                    "administration_options": [
                        {"route": self._q(prov, src, a["route_quote"], "interventions", "route"),
                         "canonical_route": canonical_label(a["canonical_route"]) or canonical_label(a["route_quote"]),
                         "duration": self._quantity(prov, src, a["duration_quote"], "", "interventions", "administration_duration"),
                         "institutional_policy": self._q(prov, src, a["policy_quote"], "interventions", "policy")}
                        for a in it["administration_options"]],
                    "alternative_to": self._q(prov, src, it["alternative_to_quote"], "interventions", "alternative_to"),
                    "schedule": {"days": parse_days(it["day_quote"]) if _mentions(it["day_quote"], "day") else None,
                                 "weeks": parse_days(it["week_quote"] or (it["day_quote"] if _mentions(it["day_quote"], "week") else ""))
                                 if _mentions(it["week_quote"] or it["day_quote"], "week") else None,
                                 "day_text": self._q(prov, src, it["day_quote"], "interventions", "days"),
                                 "week_text": self._q(prov, src, it["week_quote"], "interventions", "weeks"),
                                 "frequency": self._q(prov, src, it["frequency_quote"], "interventions", "frequency"),
                                 "dose_count": ex.parse_number(it["dose_count_quote"]),
                                 "dose_count_text": self._q(prov, src, it["dose_count_quote"], "interventions", "dose_count")},
                    "max_dose": self._quantity(prov, src, it["max_dose_quote"], "", "interventions", "max_dose"),
                    "rounding": self._quantity(prov, src, it["rounding_quote"], "", "interventions", "rounding"),
                    "linked_events": [],
                    "schedule_rules": [],
                    "min_duration": self._quantity(prov, src, it["min_duration_quote"], "", "interventions", "min_duration"),
                    "evidence": self._q(prov, src, it["evidence_quote"], "interventions", "evidence"), "sections": r["sections"], "document": r["document"],
                }
                for link in it["linked_events"]:
                    unit_q = link["offset_unit_quote"]
                    entry["linked_events"].append({
                        "relation": link["relation"],
                        "prerequisite": self._q(prov, src, link["prerequisite_quote"], "interventions", "prerequisite"),
                        "canonical_prerequisite": canonical_label(link["canonical_prerequisite"]) or canonical_label(link["prerequisite_quote"]),
                        "min_offset": self._quantity(prov, src, link["min_offset_quote"], unit_q, "interventions", "min_offset"),
                        "max_offset": self._quantity(prov, src, link["max_offset_quote"], unit_q, "interventions", "max_offset"),
                        "if_prerequisite_not_given": link["if_prerequisite_not_given"],
                        "not_given_circumstance": self._q(prov, src, link["not_given_circumstance_quote"], "interventions", "not_given_circumstance"),
                        "applies_to_days": parse_days(link["applies_to_days_quote"]) if _mentions(link["applies_to_days_quote"], "day") else None,
                        "applies_to_days_text": self._q(prov, src, link["applies_to_days_quote"], "interventions", "applies_to_days"),
                        "evidence": self._q(prov, src, link["evidence_quote"], "interventions", "evidence")})
                for k, rule in enumerate(it["schedule_rules"]):
                    logic, status = self._logic(rule["condition_nodes"], src, prov, variables, "interventions", f"{iid}.S{k + 1}", flag)
                    days_q = self._q(prov, src, rule["administer_days_quote"], "interventions", "administer_days")
                    entry["schedule_rules"].append({
                        "condition": logic, "compile_status": status, "administer_days": days_q,
                        "weekdays": _weekdays(rule["administer_days_quote"]),
                        "timing": self._q(prov, src, rule["timing_quote"], "interventions", "timing"),
                        "evidence": self._q(prov, src, rule["evidence_quote"], "interventions", "evidence")})
                for part, nodes, quote in (("condition", it["condition_nodes"], it["condition_quote"]),
                                           ("stop_condition", it["stop_nodes"], it["stop_quote"])):
                    if nodes:
                        logic, status = self._logic(nodes, src, prov, variables, "interventions", iid, flag)
                        entry[part] = {"logic": logic, "compile_status": status,
                                       "text": self._q(prov, src, quote, "interventions", "condition")}
                issues = []
                if it["category"] in {"anticancer_drug", "growth_factor"} and dose is None:
                    issues.append("no dose number")
                if dose is not None and not unit:
                    issues.append("dose without unit")
                if entry["phase_id"] is None:
                    issues.append("intervention not linked to a compiled phase")
                if entry["dose"]["quote"] and not entry["dose"]["quote"]["verified"]:
                    issues.append("dose quote not found in source")
                entry["compile_issues"] = issues
                for i in issues:
                    flag("interventions", iid, i, (entry["evidence"] or {}).get("provenance"), it["agent_quote"])
                interventions.append(entry)
            for rc in o["radiotherapy"]:
                if r.get("completion") and before_completion is not None:
                    pid = local.get(rc["phase_id"])
                    administered, unassigned = before_completion
                    if unassigned or pid in administered or any(c["phase_id"] == pid for c in courses):
                        continue  # a course already compiled (possibly without a phase) is not repeated
                cid = f"RT{len(courses) + 1}"
                course = {"course_id": cid, "phase_id": local.get(rc["phase_id"]),
                          "arms": [self._q(prov, src, a, "radiotherapy", "arm") for a in rc["arm_label_quotes"]],
                          "overall_fraction_count": ex.parse_number(rc["overall_fraction_count_quote"]),
                          "overall_fraction_count_text": self._q(prov, src, rc["overall_fraction_count_quote"], "radiotherapy", "fraction_count"),
                          "fraction_dose": self._quantity(prov, src, rc["fraction_dose_quote"], rc["fraction_unit_quote"], "radiotherapy", "fraction_dose"),
                          "fractions_per_week": ex.parse_number(rc["fractions_per_week_quote"]),
                          "evidence": self._q(prov, src, rc["evidence_quote"], "radiotherapy", "evidence"), "targets": []}
                for k, t in enumerate(rc["targets"]):
                    tid = f"{cid}.T{k + 1}"
                    logic, status = self._logic(t["condition_nodes"], src, prov, variables, "radiotherapy", tid, flag)
                    course["targets"].append({
                        "target_id": tid, "course_id": cid, "name": self._q(prov, src, t["name_quote"], "radiotherapy", "target"),
                        "canonical_target": canonical_label(t["canonical_target"]) or canonical_label(t["name_quote"]),
                        "role": t["role"], "total_dose": self._quantity(prov, src, t["total_dose_quote"], t["dose_unit_quote"], "radiotherapy", "total_dose"),
                        "cumulative": {"yes": True, "no": False}.get(t["dose_is_cumulative"]),
                        "fraction_dose": self._quantity(prov, src, t["fraction_dose_quote"], t["dose_unit_quote"], "radiotherapy", "target_fraction_dose"),
                        "boost_dose": self._quantity(prov, src, t["boost_dose_quote"], t["dose_unit_quote"], "radiotherapy", "boost_dose"),
                        "fraction_count": ex.parse_number(t["fraction_count_quote"]),
                        "fraction_count_text": self._q(prov, src, t["fraction_count_quote"], "radiotherapy", "target_fraction_count"),
                        "allowed_volumes": [self._q(prov, src, v, "radiotherapy", "volume") for v in t["allowed_volume_quotes"]],
                        "condition": logic, "compile_status": status,
                        "evidence": self._q(prov, src, t["evidence_quote"], "radiotherapy", "evidence"), "sections": r["sections"], "document": r["document"]})
                courses.append(course)
        used = {it["phase_id"] for it in interventions} | {c["phase_id"] for c in courses}
        names: dict[str, list[dict]] = {}
        for p in phases.values():
            names.setdefault(_key(render._q(p.get("name"))), []).append(p)
        for same in names.values():
            if len(same) > 1:
                for p in same:
                    if not p["arms"] and p["phase_id"] not in used:
                        phases = {k: v for k, v in phases.items() if v is not p}
        ordered = sorted(phases.values(), key=lambda p: (p["sequence_number"], p["phase_id"]))
        return ordered, interventions, courses

    def _dose_mods(self, results, source_of, prov, variables, flag):
        rules = []
        seen = set()
        for r in results:
            src = source_of(r)
            for m in r["output"]["rules"]:
                sig = (_key(m["agent_quote"]), _key(m["evidence_quote"]))
                if sig in seen:
                    continue
                seen.add(sig)
                rid = f"DM{len(rules) + 1:03d}"
                trigger, tstatus = self._logic(m["trigger_nodes"], src, prov, variables, "dose_modifications", rid, flag)
                steps = []
                for s in sorted(m["steps"], key=lambda x: x["order"]):
                    cond, cstatus = self._logic(s["condition_nodes"], src, prov, variables, "dose_modifications", rid, flag)
                    value_q = s["action_value_quote"]
                    steps.append({
                        "order": s["order"], "step_type": s["step_type"], "modality": s["modality"],
                        "condition": cond, "compile_status": cstatus,
                        "action": {"type": s["action"], "value": ex.parse_number(value_q),
                                   "unit": ex.parse_unit(s["action_unit_quote"]) or ("%" if "%" in (value_q or "") else None),
                                   "reduction_percent": ex.parse_number(s["reduction_percent_quote"]),
                                   "text": self._q(prov, src, value_q, "dose_modifications", "action_value"),
                                   "max_dose": self._quantity(prov, src, s["max_dose_quote"], "", "dose_modifications", "max_dose")},
                        "assessment": self._q(prov, src, s["assessment_quote"], "dose_modifications", "assessment"),
                        "frequency": self._q(prov, src, s["frequency_quote"], "dose_modifications", "frequency"),
                        "duration": self._quantity(prov, src, s["duration_quote"], "", "dose_modifications", "duration"),
                        "scope": self._q(prov, src, s["scope_quote"], "dose_modifications", "scope"),
                        "instruction": self._q(prov, src, s["instruction_quote"], "dose_modifications", "instruction"),
                        "evidence": self._q(prov, src, s["evidence_quote"], "dose_modifications", "evidence")})
                compile_ok = tstatus == "EXECUTABLE" and all(s["compile_status"] == "EXECUTABLE" for s in steps)
                rules.append({"rule_id": rid, "agent": self._q(prov, src, m["agent_quote"], "dose_modifications", "agent"),
                              "canonical_agent": canonical_label(m["canonical_agent"]) or canonical_label(m["agent_quote"]),
                              "phase": self._q(prov, src, m["phase_quote"], "dose_modifications", "phase"),
                              "category": self._q(prov, src, m["category_quote"], "dose_modifications", "category"),
                              "modality": m["modality"], "trigger": trigger, "steps": steps,
                              "compile_status": "EXECUTABLE" if compile_ok else "REVIEW_REQUIRED",
                              "evidence": self._q(prov, src, m["evidence_quote"], "dose_modifications", "evidence"), "sections": r["sections"], "document": r["document"]})
        return rules

    def _assessments(self, results, source_of, prov, flag):
        schedules = []
        for r in results:
            src, o = source_of(r), r["output"]
            table = r["extra"]["table"]
            src.cells.extend((table["page"], normalise(c)) for row in table["rows"] for c in row if c)
            sid = f"AS{len(schedules) + 1:02d}"
            items = []
            for a in o["assessments"]:
                points = []
                for tp in a["timepoints"]:
                    header = tp["header_quote"]
                    parsed = parse_timepoint(header)
                    point = {"header": self._q(prov, src, header, "assessments", "header"),
                             "cell": self._q(prov, src, tp["cell_quote"], "assessments", "cell"),
                             "frequency": self._q(prov, src, tp["frequency_quote"], "assessments", "frequency"),
                             "condition": self._q(prov, src, tp["condition_quote"], "assessments", "condition"),
                             "time": parsed}
                    if parsed.get("kind") == "unparsed":
                        flag("assessments", sid, f"time point not parsed: {header!r}", point["header"]["provenance"] if point["header"] else None, header)
                    points.append(point)
                items.append({"assessment": self._q(prov, src, a["assessment_quote"], "assessments", "assessment"), "timepoints": points})
            schedules.append({"schedule_id": sid, "section": r["sections"][0], "table_page": table["page"],
                              "anchor": self._q(prov, src, o["anchor_quote"], "assessments", "anchor"),
                              "canonical_anchor": canonical_label(o["canonical_anchor"]),
                              "arms": [self._q(prov, src, a, "assessments", "arm") for a in o["arm_label_quotes"]],
                              "footnotes": [{"symbol": f["symbol_quote"], "text": self._q(prov, src, f["text_quote"], "assessments", "footnote")}
                                            for f in o["footnotes"]],
                              "assessments": items})
        return schedules

    def _discontinuation(self, results, source_of, prov, flag):
        rules = []
        seen = set()
        for r in results:
            src = source_of(r)
            for c in r["output"]["criteria"]:
                sig = (c["scope"], _key(c["criterion_quote"]))
                if sig in seen:
                    continue
                seen.add(sig)
                value = ex.parse_number(c["time_value_quote"])
                unit = ex.parse_unit(c["time_unit_quote"])
                rules.append({"rule_id": f"DC{len(rules) + 1:02d}", "scope": c["scope"], "trigger": c["trigger"],
                              "criterion": self._q(prov, src, c["criterion_quote"], "discontinuation", "criterion"),
                              "time_limit": {"value": value, "unit": unit, "days": ex.to_days(value, unit),
                                             "anchor": self._q(prov, src, c["anchor_quote"], "discontinuation", "anchor"),
                                             "canonical_anchor": canonical_label(c["canonical_anchor"])}
                              if c["trigger"] == "time_limit" else None})
                if c["trigger"] == "time_limit" and (value is None or not unit):
                    flag("discontinuation", rules[-1]["rule_id"], "time limit without parsable value or unit", None, c["criterion_quote"])
        return rules

    def _decision_rules(self, results, source_of, prov, arms):
        self._arms = arms  # the rebuild of a repaired rule is matched against the same arms

        def q(src, quote, field):
            return self._q(prov, src, quote, "decision_rules", field)
        return drules.build(results, source_of, q, arms)

    def _statistics(self, results, source_of, prov, flag):
        design: dict[str, Any] = {}
        endpoints, analyses, sample, interim, populations, subgroups, missing = [], [], [], [], [], [], []
        seen: dict[str, set] = {k: set() for k in ("ep", "an", "ss", "im", "po", "sg", "md")}
        for r in results:
            src, o = source_of(r), r["output"]
            d = o["design"]
            for f in ("phase", "design", "allocation_ratio", "blinding"):
                if d[f + "_quote"] and f not in design:
                    design[f] = self._q(prov, src, d[f + "_quote"], "design", f)
            if d["design_type"] != "other" and "type" not in design:
                design["type"] = d["design_type"]
            for e in o["endpoints"]:
                k = (canonical_label(e["canonical_endpoint"]) or _key(e["name_quote"])) + e["role"]
                if k in seen["ep"]:
                    continue
                seen["ep"].add(k)
                endpoints.append({"endpoint_id": f"EP{len(endpoints) + 1}", "name": self._q(prov, src, e["name_quote"], "endpoints", "name"),
                                  "canonical_endpoint": canonical_label(e["canonical_endpoint"]), "role": e["role"], "type": e["type"],
                                  "events": [self._q(prov, src, q, "endpoints", "event") for q in e["event_quotes"]],
                                  "time_origin": self._q(prov, src, e["time_origin_quote"], "endpoints", "time_origin"),
                                  "canonical_origin_event": canonical_label(e["canonical_origin_event"]) if e["time_origin_quote"] else None,
                                  "censoring": [self._q(prov, src, q, "endpoints", "censoring") for q in e["censoring_quotes"]],
                                  "population": self._q(prov, src, e["population_quote"], "endpoints", "population"),
                                  "evidence": self._q(prov, src, e["evidence_quote"], "endpoints", "evidence"), "sections": r["sections"], "document": r["document"]})
            for a in o["analyses"]:
                k = "|".join([_key(a["endpoint_name_quote"]), a["test_family"], a["sidedness"], _key(a["alpha_quote"]),
                              _key(a["power_quote"])])
                if k in seen["an"]:
                    continue
                seen["an"].add(k)
                analyses.append({"analysis_id": f"AN{len(analyses) + 1}", "primary": a["is_primary"],
                                 "endpoint": self._q(prov, src, a["endpoint_name_quote"], "analyses", "endpoint"),
                                 "method": self._q(prov, src, a["method_quote"], "analyses", "method"), "test_family": a["test_family"],
                                 "sidedness": a["sidedness"],
                                 "alpha": {"value": _as_fraction(ex.parse_number(a["alpha_quote"]), a["alpha_quote"]),
                                           "text": self._q(prov, src, a["alpha_quote"], "analyses", "alpha")},
                                 "power": {"value": _as_fraction(ex.parse_number(a["power_quote"]), a["power_quote"]),
                                           "text": self._q(prov, src, a["power_quote"], "analyses", "power")},
                                 "effects": [self._q(prov, src, q, "analyses", "effect") for q in a["effect_quotes"]],
                                 "scenarios": [{"effect": self._q(prov, src, sc_["effect_quote"], "analyses", "scenario_effect"),
                                                "power": _as_fraction(ex.parse_number(sc_["power_quote"]), sc_["power_quote"]),
                                                "power_text": self._q(prov, src, sc_["power_quote"], "analyses", "scenario_power"),
                                                "assumption": self._q(prov, src, sc_["assumption_quote"], "analyses", "scenario_assumption")}
                                               for sc_ in a["scenarios"]],
                                 "stratification": [self._q(prov, src, q, "analyses", "stratification") for q in a["stratification_quotes"]],
                                 "population": self._q(prov, src, a["population_quote"], "analyses", "population"),
                                 "multiplicity": self._q(prov, src, a["multiplicity_quote"], "analyses", "multiplicity"),
                                 "evidence": self._q(prov, src, a["evidence_quote"], "analyses", "evidence"),
                                 "sections": r["sections"], "document": r.get("document")})
            for s in o["sample_size"]:
                k = s["quantity"] + _key(s["evidence_quote"])
                if k in seen["ss"]:
                    continue
                seen["ss"].add(k)
                sample.append({"quantity": s["quantity"], "value": ex.parse_number(s["value_quote"]), "unit": _unit_or_text(s["unit_quote"]),
                               "text": self._q(prov, src, s["value_quote"], "sample_size", "value"),
                               "evidence": self._q(prov, src, s["evidence_quote"], "sample_size", "evidence")})
            for i in o["interim"]:
                k = i["purpose"] + _key(i["evidence_quote"])
                if k in seen["im"]:
                    continue
                seen["im"].add(k)
                mid = f"IM{len(interim) + 1}"
                entry = {"interim_id": mid, "purpose": i["purpose"], "status": i["status"],
                         "method_family": i["method_family"], "spending_family": i["spending_family"],
                         "status_evidence": self._q(prov, src, i["status_quote"], "interim", "status"),
                         **{f: self._q(prov, src, i[f + "_quote"], "interim", f) for f in
                            ("endpoint", "method", "alpha", "spending_parameter", "information", "prior", "threshold",
                             "posterior_cutoff", "futility_cutoff", "boundary", "schedule", "evidence")}}
                entry["monitor"] = _monitor(i)
                interim.append(entry)
                if i["status"] == "unclear":
                    flag("interim", mid, "interim rule status in this version unclear", None, i["evidence_quote"])
            for p in o["populations"]:
                if _key(p["name_quote"]) not in seen["po"]:
                    seen["po"].add(_key(p["name_quote"]))
                    populations.append({"name": self._q(prov, src, p["name_quote"], "populations", "name"),
                                        "definition": self._q(prov, src, p["definition_quote"], "populations", "definition")})
            for g in o["subgroups"]:
                if _key(g["subgroup_quote"]) not in seen["sg"]:
                    seen["sg"].add(_key(g["subgroup_quote"]))
                    subgroups.append({"subgroup": self._q(prov, src, g["subgroup_quote"], "subgroups", "subgroup"),
                                      "analysis": self._q(prov, src, g["analysis_quote"], "subgroups", "analysis")})
            for m in o["missing_data"]:
                if _key(m["method_quote"]) not in seen["md"]:
                    seen["md"].add(_key(m["method_quote"]))
                    missing.append(self._q(prov, src, m["method_quote"], "missing_data", "method"))
        if design.get("allocation_ratio"):
            design["allocation"] = _ratio(design["allocation_ratio"]["text"])
        return {"design": design, "endpoints": endpoints, "analyses": analyses, "sample_size": sample,
                "interim_analyses": interim, "analysis_populations": populations, "subgroups": subgroups,
                "missing_data": missing}

    def _response(self, results, source_of, prov, flag):
        out: dict[str, Any] = {"categories": [], "overall_rules": []}
        for r in results:
            src, o = source_of(r), r["output"]
            out.setdefault("framework", self._q(prov, src, o["framework_quote"], "response", "framework"))
            out.setdefault("measurement", self._q(prov, src, o["measurement_quote"], "response", "measurement"))
            for c in o["categories"]:
                value = ex.parse_number(c["threshold_value_quote"])
                out["categories"].append({"level": c["level"], "variant": self._q(prov, src, c["variant_quote"], "response", "variant"),
                                          "category": self._q(prov, src, c["category_quote"], "response", "category"),
                                          "definition": self._q(prov, src, c["definition_quote"], "response", "definition"),
                                          "threshold": {"value": value, "unit": "%" if "%" in (c["threshold_value_quote"] or "") else None,
                                                        "direction": c["direction"],
                                                        "reference": self._q(prov, src, c["reference_quote"], "response", "reference")}})
            for row in o["overall_rules"]:
                out["overall_rules"].append({k: self._q(prov, src, row[k + "_quote"], "response", k)
                                             for k in ("target", "non_target", "new_lesion", "overall")})
        return out

    def _definitions(self, results, source_of, prov, variables, flag):
        grades, scales = [], []
        for r in results:
            src = source_of(r)
            for s in r["output"]["scales"]:
                sid = f"GD{len(grades) + len(scales) + 1}"
                levels = []
                for lv in s["levels"]:
                    logic, status = self._logic(lv["criteria_nodes"], src, prov, variables, "grades", sid, flag) \
                        if lv["criteria_nodes"] else (None, None)
                    levels.append({"level": self._q(prov, src, lv["level_quote"], "definitions", "level"),
                                   "definition": self._q(prov, src, lv["definition_quote"], "definitions", "definition"),
                                   "criteria": logic, "compile_status": status})
                item = {"scale_id": sid, "kind": s["kind"],
                        "system": self._q(prov, src, s["variable_quote"], "definitions", "system"),
                        "canonical_concept": canonical_label(s["canonical_concept"]),
                        "applies_to": self._q(prov, src, s["applies_quote"], "definitions", "applies"), "levels": levels}
                (grades if s["kind"] == "grading" and any(lv["criteria"] for lv in levels) else scales).append(item)
        return grades, scales

    def _link_grades(self, spec: dict) -> None:
        """A rule that tests '<event>_grade' is linked to the protocol's own grading definition of it, so
        the simulator derives the grade from measurements instead of assuming it."""
        by_concept = {g["canonical_concept"]: g["scale_id"] for g in spec["grade_definitions"] if g["canonical_concept"]}
        for _, _, tree in typecheck._trees(spec):
            for leaf in ex.leaves(tree):
                label = leaf.get("canonical") or ""
                for concept, sid in by_concept.items():
                    if label and (label == concept or label.replace("_grade", "") == concept.replace("_grade", "")):
                        leaf["derived_from_definition"] = sid

    # ---------------------------------------------------------------- resolution from the PDF itself
    def _resolve(self, spec: dict, docs: list[Document], prov: Provenance, flag) -> list[dict]:
        """Facts a simulator needs that were not found where they are usually stated (time origin and
        censoring of time-to-event endpoints, allocation ratio) are asked of the whole protocol text.
        STATED and IMPLIED_BY_TEXT answers carry quoted evidence; NOT_STATED is left unresolved."""
        questions = []
        for e in spec["endpoints"]:
            if e["type"] != "time_to_event" or e["role"] not in {"primary", "secondary"}:
                continue
            name = render._q(e.get("name"))
            if not e.get("time_origin"):
                questions.append({"question_id": f"{e['endpoint_id']}.origin",
                                  "question": f"From what event is time measured for the endpoint '{name}' (time zero)?"})
            if not any(e.get("censoring") or []):
                questions.append({"question_id": f"{e['endpoint_id']}.censoring",
                                  "question": f"How are patients without an event handled (censored) for the endpoint '{name}'?"})
        open_arms = [render._q(a["label"]) for a in spec["arms"] if a["status"] == "open"]
        if len(open_arms) >= 2 and not spec["randomization"].get("allocation") and not spec["design"].get("allocation"):
            questions.append({"question_id": "randomization.allocation",
                              "question": f"In what ratio are patients allocated between {', '.join(open_arms)}?"})
        if not questions:
            return []
        wanted = {"statistics", "sample_size", "interim_analysis", "endpoints", "randomization", "stratification",
                  "schema_design", "objectives", "enrollment_procedures", "discontinuation", "follow_up", "metadata"}
        parts, sections = [], []
        for d in docs:
            front = Section("front", "Front matter", 0, 1, 1, 0.0, d.front_matter, [])
            sections.append(front)
            parts.append("\n".join(line.text for line in d.front_matter))
            for s in d.sections:
                if set(self._types.get(d.doc_id, {}).get(s.number, [])) & wanted:
                    sections.append(s)
                    parts.append(f"{s.number} {s.title}\n{s.text()}")
        text = "\n".join(parts)[:150000]
        try:
            out = self.model.extract("protocol_resolve", sc.RESOLVE,
                                     {"instructions": sc.RESOLVE_INSTRUCTIONS, "questions": questions, "text": text})
        except Exception as exc:  # noqa: BLE001 - unresolved questions stay unresolved and are reported
            flag("resolve", "all", f"resolution call failed: {exc!r}")
            out = {"answers": []}
        src = Source.of(sections)
        answers = {a["question_id"]: a for a in out.get("answers", [])}
        resolved = []
        for q in questions:
            a = answers.get(q["question_id"], {"status": "NOT_STATED", "answer_quote": "", "evidence_quote": "", "canonical_value": ""})
            answer = self._q(prov, src, a["answer_quote"], "resolve", "answer")
            evidence = self._q(prov, src, a["evidence_quote"], "resolve", "evidence")
            status = a["status"]
            if status == "STATED" and not (answer and answer["verified"]):
                status = "NOT_STATED"
            if status == "IMPLIED_BY_TEXT" and not (evidence and evidence["verified"] and a["canonical_value"]):
                status = "NOT_STATED"
            record = {**q, "status": status, "answer": answer, "evidence": evidence,
                      "canonical_value": a["canonical_value"] or None, "source": "protocol PDF only"}
            resolved.append(record)
            target, _, what = q["question_id"].partition(".")
            if target.startswith("EP"):
                e = next(x for x in spec["endpoints"] if x["endpoint_id"] == target)
                if status == "NOT_STATED":
                    e[f"{'time_origin' if what == 'origin' else 'censoring'}_unresolved_in_source"] = True
                elif what == "origin":
                    e["time_origin"] = answer or evidence
                    e["time_origin_derivation"] = status
                    e["canonical_origin_event"] = canonical_label(a["canonical_value"]) or None
                else:
                    e["censoring"] = [answer or evidence]
                    e["censoring_derivation"] = status
            elif q["question_id"] == "randomization.allocation":
                if status == "NOT_STATED":
                    spec["randomization"]["allocation_unresolved_in_source"] = True
                else:
                    ratio = _ratio(a["canonical_value"] or (answer or {}).get("text") or "")
                    if ratio:
                        spec["randomization"]["allocation"] = {**ratio, "derivation": status, "evidence": answer or evidence}
                    else:
                        spec["randomization"]["allocation_unresolved_in_source"] = True
        return resolved

    # ---------------------------------------------------------------- statuses
    def _items(self, spec: dict):
        """(component, item, trees) for every item that carries statuses."""
        for c in spec["eligibility"]:
            yield "eligibility", c, [c.get("logic")]
        for s in spec["stratification"]["strata"]:
            yield "stratification", s, [s.get("logic")]
        for p in spec["treatment_phases"]:
            yield "treatment", p, [(p.get("start_condition") or {}).get("logic")]
        for it in spec["interventions"]:
            yield "treatment", it, [(it.get(k) or {}).get("logic") for k in ("condition", "stop_condition")] + \
                [r.get("condition") for r in it["schedule_rules"]]
        for course in spec["radiotherapy"]:
            for t in course["targets"]:
                yield "radiotherapy", t, [t.get("condition")]
        for m in spec["dose_modifications"]:
            yield "dose_modification", m, [m.get("trigger")] + [s.get("condition") for s in m["steps"]]
        for e in spec["endpoints"]:
            yield "endpoints", e, []
        for a in spec["analyses"]:
            yield "analyses", a, []
        for i in spec["interim_analyses"]:
            yield "interim", i, []
        for r in spec.get("decision_rules") or []:
            yield "decision_rules", r, []

    def _runtime_and_criticality(self, spec: dict) -> None:
        for component, item, trees in self._items(spec):
            category = item.get("category") if "intervention_id" in item else None  # a class label only on interventions
            item["criticality"] = ir.criticality(component, {**item, "modality_class": "supportive" if category in {"supportive", "premedication"} else ""})
            leaves = [leaf for t in trees if t for leaf in ex.leaves(t)]
            modality = item.get("modality", "REQUIRED")
            if component == "eligibility" and item["kind"] not in {"inclusion", "exclusion", "timing"}:
                item["runtime_status"] = "NON_EXECUTABLE_INFORMATIONAL"
            elif component == "eligibility" and item.get("logic") is None:
                item["runtime_status"] = "UNSUPPORTED_RULE_TYPE"
            elif component == "endpoints":
                unresolved = item.get("time_origin_unresolved_in_source") or item.get("censoring_unresolved_in_source")
                complete = item["type"] != "time_to_event" or (item.get("time_origin") and any(item.get("events") or [])
                                                               and any(item.get("censoring") or []))
                item["runtime_status"] = "EXECUTABLE_NOW" if complete else ("UNRESOLVED_IN_SOURCE" if unresolved else "UNSUPPORTED_RULE_TYPE")
            elif component == "analyses":
                decided = any(r.get("role") == "primary" and not r.get("compile_issues") for r in spec.get("decision_rules") or [])
                item["runtime_status"] = "EXECUTABLE_NOW" if item["test_family"] != "other" or decided else "UNSUPPORTED_RULE_TYPE"
            elif component == "decision_rules":
                item["runtime_status"] = "UNSUPPORTED_RULE_TYPE" if item.get("compile_issues") else "EXECUTABLE_NOW"
            elif component == "interim":
                item["runtime_status"] = item["monitor"]["runtime_status"] if item["status"] == "active" else "NON_EXECUTABLE_INFORMATIONAL"
            elif component == "dose_modification":
                step_modalities = {s["modality"] for s in item["steps"]}
                if modality not in ir.DETERMINISTIC_MODALITIES or not (step_modalities & ir.DETERMINISTIC_MODALITIES):
                    item["runtime_status"] = "OPTIONAL_POLICY"
                else:
                    item["runtime_status"] = ir.runtime_from_leaves(leaves, "REQUIRED") if leaves else \
                        ("EXECUTABLE_NOW" if item["compile_status"] == "EXECUTABLE" else "UNSUPPORTED_RULE_TYPE")
            elif component == "treatment" and "intervention_id" in item:
                base = ir.runtime_from_leaves(leaves, modality) if leaves else ("OPTIONAL_POLICY" if modality not in ir.DETERMINISTIC_MODALITIES else "EXECUTABLE_NOW")
                item["runtime_status"] = "UNSUPPORTED_RULE_TYPE" if item["compile_issues"] and base != "OPTIONAL_POLICY" else base
            else:
                item["runtime_status"] = ir.runtime_from_leaves(leaves, modality) if leaves else "EXECUTABLE_NOW"

    def _apply_static(self, spec: dict, static: dict[str, list[str]], flag) -> None:
        for component, item, _ in self._items(spec):
            iid = _item_id(item)
            found = static.get(iid, [])
            item["static_issues"] = found
            item["static_status"] = "FAIL" if found else "PASS"
            for issue in found:
                flag("static_check", iid, issue)
            del component

    def _dedupe_escalation(self, spec: dict) -> None:
        """One rule per escalation table: repair rebuilds rules one at a time, so compiles of the same table can coexist.
        The verified, then the most complete, compile is kept; the others are recorded as merged."""
        rules = spec.get("decision_rules") or []
        keep, merged = {}, []
        for r in rules:
            if r["kind"] != "dose_escalation":
                continue
            sig = repr([(x["action"], x["dlt"], x["comparator"], x["patients"]) for x in r["rule"]["rules"]])
            rank = (r.get("semantic_status") == "FAITHFUL", *drules._completeness(r))
            if sig not in keep or rank > keep[sig][0]:
                if sig in keep:
                    merged.append(keep[sig][1]["decision_rule_id"])
                keep[sig] = (rank, r)
            else:
                merged.append(r["decision_rule_id"])
        if merged:
            spec["decision_rules"] = [r for r in rules if r["decision_rule_id"] not in merged]
            spec.setdefault("resolutions", []).append({"kind": "merged_duplicate_escalation_compiles", "removed": merged})

    def _finalise_status(self, spec: dict) -> None:
        """Summary status per item from its semantic, static and runtime axes."""
        self._dedupe_escalation(spec)
        for component, item, _ in self._items(spec):
            if item.get("criticality_before_repair"):  # the verifier has now judged the repaired item
                item["criticality"] = ir.criticality(component, item)
            semantic = item.get("semantic_status", "UNVERIFIED")
            runtime = item.get("runtime_status")
            if semantic in {"INCOMPLETE", "INCORRECT"}:  # a rendering the verifier rejected is never reported as settled
                item["status"] = "REVIEW_REQUIRED"
            elif semantic == "NOT_A_RULE":               # the verifiers found no rule in the text (L031)
                item["status"] = "NON_EXECUTABLE_INFORMATIONAL"
            elif runtime in {"NON_EXECUTABLE_INFORMATIONAL", "OPTIONAL_POLICY", "UNRESOLVED_IN_SOURCE"}:
                item["status"] = runtime
            elif semantic == "FAITHFUL" and item.get("static_status") == "PASS" and ir.executable(runtime):
                item["status"] = "EXECUTABLE"
            else:
                item["status"] = "REVIEW_REQUIRED"

    # ---------------------------------------------------------------- automatic repair
    def repair(self, spec: dict, docs: list[Document], prov: Provenance, variables: Variables, review: list[dict], flag,
               only: set[str] | None = None) -> list[str]:
        """One automatic repair round. Every CRITICAL item that the verifier judged INCOMPLETE or
        INCORRECT, that failed a static check, or that could not be expressed, is re-extracted from its
        own source sections with the reason attached, rebuilt by the normal builders (so every quote is
        verified again), and replaces the original under the same id. Returns the repaired ids."""
        by_doc = {d.doc_id: d for d in docs}
        jobs = []
        for component, item, _ in self._items(spec):
            # every item with a failure, whatever its criticality (lessons L028, L030: the target is every rule faithful)
            if component not in REPAIRABLE or item.get("status") in {"NON_EXECUTABLE_INFORMATIONAL"} or not item.get("sections"):
                continue
            if only is not None and _item_id(item) not in only:      # a targeted resolution touches its own items only (L033)
                continue
            failed = item.get("semantic_status") in {"INCOMPLETE", "INCORRECT"} or item.get("static_status") == "FAIL" \
                or item.get("runtime_status") == "UNSUPPORTED_RULE_TYPE"
            if not failed:
                continue
            doc = by_doc.get(item.get("document"))
            sections = [doc.section(n) for n in item["sections"] if doc and doc.section(n)]
            if not sections:
                continue
            task = REPAIRABLE[component]
            _, schema, instructions = TASKS[task]
            v = item.get("verification") or {}
            problem = {"compiled_item": item.get("rendering") or "", "evidence": render._q(item.get("evidence")),
                       "verifier_verdict": v.get("verdict"), "verifier_note": v.get("reviewer_note"),
                       "all_reviewer_notes": v.get("vote_notes") or [v.get("reviewer_note")],
                       "protocol_wording_misrepresented": v.get("problem_quote"),
                       "static_issues": item.get("static_issues") or [],
                       "investigation": item.get("investigation"),        # the targeted resolver's finding (L033)
                       "unresolved_parts": [leaf.get("text") for t in self._trees_of(item) for leaf in ex.leaves(t)
                                            if leaf.get("status") != "EXECUTABLE"]}
            jobs.append((component, item, task, schema, sc.REPAIR_PREFIX + instructions, sections, problem))
        if not jobs:
            return []

        def run(job):
            _component, _item, task, schema, instructions, sections, problem = job
            try:
                out = self.model.extract(f"protocol_{task}", schema, {"instructions": instructions, **_section_payload(sections),
                                                                      "repair": problem})
                return job, out
            except Exception as exc:  # noqa: BLE001 - an item that cannot be repaired keeps its original compilation
                return job, {"error": repr(exc)}
        with ThreadPoolExecutor(self.workers) as pool:
            outcomes = list(pool.map(run, jobs))
        repaired = []
        for (component, item, task, _schema, _ins, sections, problem), out in outcomes:
            iid = _item_id(item)
            if "error" in out:
                flag(component, iid, f"automatic repair failed: {out['error']}")
                continue
            r = {"task": task, "sections": item["sections"], "document": item["document"], "output": out}
            src_doc = by_doc[item["document"]]

            def source_of(_r, d=src_doc, secs=sections):
                prov.doc = d
                return Source.of(secs)

            def local_flag(c, _item, reason, provenance=None, text=None, _iid=iid):
                flag(c, _iid, reason, provenance, text)

            new = self._rebuilt(component, item, r, source_of, prov, variables, local_flag)
            if new is None:
                flag(component, iid, "automatic repair returned no matching item")
                continue
            review[:] = [x for x in review if not (x["item"] == iid or str(x["item"]).startswith(iid + ".")) or x.get("_after_repair")]
            new["repair"] = {"previous_rendering": problem["compiled_item"], "previous_verdict": problem["verifier_verdict"],
                             "previous_note": problem["verifier_note"], "previous_static_issues": problem["static_issues"]}
            keep = {"criticality": item["criticality"], "criticality_before_repair": item["criticality"]}
            item.clear()
            item.update({**new, **keep})
            repaired.append(iid)
        for x in review:
            x["_after_repair"] = True
        return repaired

    def _trees_of(self, item: dict) -> list[dict]:
        trees = [item.get(k) for k in ("logic", "trigger", "condition")]
        trees += [(item.get(k) or {}).get("logic") for k in ("start_condition", "stop_condition")]
        if isinstance(item.get("condition"), dict) and "logic" in item["condition"]:
            trees.append(item["condition"]["logic"])
        trees += [s.get("condition") for s in item.get("steps") or []]
        trees += [s.get("condition") for s in item.get("schedule_rules") or []]
        return [t for t in trees if isinstance(t, dict) and t.get("node")]

    def _rebuilt(self, component: str, old: dict, r: dict, source_of, prov, variables, flag) -> dict | None:
        """Run the normal builder on a repair output and pick the item that replaces `old`."""
        if component == "eligibility":
            built = self._eligibility([r], source_of, prov, variables, flag)
            items = [c for c in built if c.get("logic") is not None]
            notes = [c for c in built if c["kind"] not in {"inclusion", "exclusion", "timing"}]
            new = items[0] if items else None
            if new is None and len(notes) == 1 and old["kind"] in {"inclusion", "exclusion", "timing"}:
                # The repair judged the text not to be a patient requirement. Accepted only if the
                # independent verifier agrees; until then the item keeps the criticality of a rule.
                new = {**notes[0], "reclassified_from": old["kind"]}
            key = "criterion_id"
        elif component == "dose_modification":
            items = self._dose_mods([r], source_of, prov, variables, flag)
            agent = old.get("canonical_agent")
            new = next((m for m in items if m.get("canonical_agent") == agent), items[0] if items else None)
            key = "rule_id"
        elif component == "stratification":
            _, strat = self._stratification([r], source_of, prov, variables, flag)
            new = strat["strata"][0] if strat["strata"] else None
            key = "stratum_id"
        elif component == "endpoints":
            stats = self._statistics([r], source_of, prov, flag)
            new = next((e for e in stats["endpoints"] if e["role"] == old["role"]), stats["endpoints"][0] if stats["endpoints"] else None)
            if new is not None:  # what the resolver established from the whole protocol still holds
                for k in ("time_origin", "time_origin_derivation", "canonical_origin_event", "time_origin_unresolved_in_source",
                          "censoring", "censoring_derivation", "censoring_unresolved_in_source"):
                    if old.get(k) and not (new.get(k) and any(new[k] if isinstance(new[k], list) else [new[k]])):
                        new[k] = old[k]
            key = "endpoint_id"
        elif component == "decision_rules":
            rules = self._decision_rules([r], source_of, prov, self._arms)
            same = [x for x in rules if x["kind"] == old["kind"] and set(x["arms"]) == set(old["arms"])]
            new = same[0] if same else (rules[0] if len(rules) == 1 else None)
            key = "decision_rule_id"
        elif component == "analyses":
            stats = self._statistics([r], source_of, prov, flag)
            new = next((a for a in stats["analyses"] if a.get("primary")), stats["analyses"][0] if stats["analyses"] else None)
            key = "analysis_id"
        elif component == "treatment" and "intervention_id" not in old:
            phases, _, _ = self._treatment([r], source_of, prov, variables, flag)
            name = _key(render._q(old.get("name")))
            new = next((p for p in phases if p.get("canonical_phase") == old.get("canonical_phase")),
                       next((p for p in phases if _key(render._q(p.get("name"))) == name), phases[0] if len(phases) == 1 else None))
            if new is not None:
                new["sequence_number"] = old["sequence_number"]
            key = "phase_id"
        elif component == "treatment":
            _, interventions, _ = self._treatment([r], source_of, prov, variables, flag)
            agent = old.get("canonical_agent")
            new = next((x for x in interventions if x.get("canonical_agent") == agent), None)
            if new is not None:
                new["phase_id"] = old["phase_id"]  # the phase structure is not re-derived by an item repair
                new["compile_issues"] = [i for i in new["compile_issues"] if "phase" not in i]
            key = "intervention_id"
        elif component == "radiotherapy":
            _, _, courses = self._treatment([r], source_of, prov, variables, flag)
            targets = [t for c in courses for t in c["targets"]]
            new = next((t for t in targets if t.get("canonical_target") == old.get("canonical_target")),
                       next((t for t in targets if t["role"] == old["role"]), None))
            if new is not None:
                new["course_id"] = old["course_id"]
            key = "target_id"
        else:
            return None
        if new is None:
            return None
        new[key] = old[key]
        return new

    # ---------------------------------------------------------------- independent verification
    def verify(self, spec: dict, docs: list[Document], flag, batch: int = 1, only: set[str] | None = None) -> None:
        """Second, independent model pass: each compiled item is rendered in plain language and judged
        against the protocol wording, with its related items as context. The verdict sets the item's
        semantic_status; nothing is corrected automatically. CRITICAL items are judged by
        `critical_votes` independent calls and take the majority verdict (see `_majority`), so the gate
        does not depend on a single model judgement."""
        labels = {v["key"]: v["label"] for v in spec["variables"]}
        phase_names = {p["phase_id"]: render._q(p.get("name")) for p in spec["treatment_phases"]}
        groups: dict[str, list[tuple[dict, str, str]]] = {}
        for c in spec["eligibility"]:
            if c.get("logic") is not None or c.get("reclassified_from"):
                groups.setdefault("eligibility", []).append((c, render.criterion(c, labels), _evidence(c, c.get("logic"))))
        for s in spec["stratification"]["strata"]:
            groups.setdefault("stratification", []).append((s, render.rule(s.get("logic"), labels), _evidence(s, s.get("logic"), "label")))
        for p in spec["treatment_phases"]:
            groups.setdefault("treatment", []).append((p, render.phase(p, labels), _evidence(p, (p.get("start_condition") or {}).get("logic"))))
        for it in spec["interventions"]:
            groups.setdefault("treatment", []).append((it, render.intervention(it, phase_names, labels), _evidence(it, (it.get("condition") or {}).get("logic"))))
        for course in spec["radiotherapy"]:
            for t in course["targets"]:
                groups.setdefault("radiotherapy", []).append((t, render.radiotherapy_target(course, t, labels), _evidence(t, t.get("condition"))))
        for m in spec["dose_modifications"]:
            groups.setdefault("dose_modification", []).append((m, render.dose_modification(m, labels), _evidence(m, m.get("trigger"))))
        for e in spec["endpoints"]:
            groups.setdefault("statistics", []).append((e, render.endpoint(e), _evidence(e, None)))
        for a in spec["analyses"]:                 # every analysis, not only the primary one (L030)
            groups.setdefault("statistics", []).append((a, render.analysis(a), _evidence(a, None)))
        for k, q in enumerate(spec.get("sample_size") or [], 1):
            q.setdefault("sample_size_id", f"SS{k:02d}")
            groups.setdefault("statistics", []).append((q, _render_quantity(q), _evidence(q, None)))
        for d in spec.get("discontinuation_rules") or []:
            groups.setdefault("discontinuation", []).append((d, _render_discontinuation(d), _evidence(d, None, "criterion")))
        for r in spec.get("decision_rules") or []:
            groups.setdefault("design_rules", []).append((r, drules.render_rule(r), " | ".join(
                dict.fromkeys(x for x in [render._q(r.get("evidence"))] + _verified_quotes(r) if x))))  # a rule is built from several passages
        renderings = {_item_id(it): r for items in groups.values() for it, r, _ in items}
        evidence_of = {_item_id(it): ev for items in groups.values() for it, _, ev in items}
        rt_renderings = {c["course_id"]: render.radiotherapy_course(c) for c in spec["radiotherapy"]}

        def related(component: str, it: dict) -> list[str]:
            """Other compiled items that together with this one express the same protocol text."""
            iid = _item_id(it)
            if component in {"eligibility", "stratification", "statistics", "design_rules"}:
                ids = [_item_id(x) for x, _, _ in groups[component]]
                extra = []
            elif component == "radiotherapy":
                ids = [x["target_id"] for c in spec["radiotherapy"] if c["course_id"] == it["course_id"] for x in c["targets"]]
                extra = [f"{it['course_id']}: {rt_renderings[it['course_id']]}"]
            elif "intervention_id" in it:
                same_agent = it.get("canonical_agent") or _key(render._q(it.get("agent")))   # same agent in other phases (L030)
                ids = [x["intervention_id"] for x in spec["interventions"] if x["phase_id"] == it["phase_id"]
                       or (x.get("canonical_agent") or _key(render._q(x.get("agent")))) == same_agent] + \
                      [p["phase_id"] for p in spec["treatment_phases"] if p["phase_id"] == it["phase_id"]]
                extra = [f"{c['course_id']}: {rt_renderings[c['course_id']]}" for c in spec["radiotherapy"] if c["phase_id"] == it["phase_id"]]
            elif "phase_id" in it and "rule_id" not in it:
                ids = [p["phase_id"] for p in spec["treatment_phases"]] + \
                      [x["intervention_id"] for x in spec["interventions"] if x["phase_id"] == iid]
                extra = [f"{c['course_id']}: {rt_renderings[c['course_id']]}" for c in spec["radiotherapy"] if c["phase_id"] == iid]
            else:
                agent = it.get("canonical_agent") or _key(render._q(it.get("agent")))
                ids = [m["rule_id"] for m in spec["dose_modifications"] if (m.get("canonical_agent") or _key(render._q(m.get("agent")))) == agent]
                extra = []
            return ([f"{i}: {renderings[i]}" for i in ids if i != iid and i in renderings] + extra)[:40]

        jobs = []
        for component, items in groups.items():
            text = self._component_text(docs, component)
            selected = [x for x in items if only is None or _item_id(x[0]) in only]
            for start in range(0, len(selected), batch):
                chunk = selected[start:start + batch]
                votes = self.critical_votes                # every rule item, whatever its criticality (L030)
                for vote in range(votes):
                    jobs.append((component, [(it, r, e, related(component, it)) for it, r, e in chunk], text, vote, votes))

        def run(job):
            _component, items, text, vote, votes = job
            extra = [doc.section(n) for it, _, _, _ in items for n in (it.get("investigation") or {}).get("sections") or []
                     for doc in docs if doc.section(n)]            # sections the targeted resolver found decisive (L033)
            if extra:
                unique = list({x.number: x for x in extra}.values())
                text = text + "\n" + "\n".join(f"{x.number} {x.title}\n{x.text()}" for x in unique)
            payload = {"instructions": sc.VERIFY_INSTRUCTIONS + (drules.DESIGN_RULES_VERIFY_NOTE if _component == "design_rules" else ""), "text": text,
                       "items": [{"item_id": _item_id(it), "rendering": rendering, "evidence": evidence, "related": rel}
                                 for it, rendering, evidence, rel in items]}
            if vote:  # a distinct request, so each vote is a separate judgement (the first stays cache-compatible)
                payload["independent_review"] = f"review {vote + 1} of {votes}: judge from scratch"
            try:
                return job, self.model.extract("protocol_verify", sc.VERIFY, payload)
            except Exception as exc:  # noqa: BLE001 - a failed review leaves items unverified (flagged below)
                return job, {"error": repr(exc)}
        with ThreadPoolExecutor(self.workers) as pool:
            outcomes = list(pool.map(run, jobs))
        ballots: dict[str, dict] = {}
        for (component, items, _, _vote, votes), out in outcomes:
            out = out if isinstance(out, dict) else {"error": "malformed verification response"}
            verdicts = {v["item_id"]: v for v in out.get("verdicts", [])}
            for it, rendering, _, _ in items:
                box = ballots.setdefault(_item_id(it), {"component": component, "item": it, "rendering": rendering,
                                                        "votes": votes, "cast": [], "errors": []})
                v = verdicts.get(_item_id(it))
                if v is None or v.get("verdict") not in VERDICTS:
                    box["errors"].append(out.get("error", "no verdict returned"))
                else:
                    box["cast"].append(v)
        for iid, box in ballots.items():
            component, it = box["component"], box["item"]
            it["rendering"] = box["rendering"]
            v = _majority(box["cast"], box["votes"])
            if v is None:
                it["verification"] = {"verdict": "NOT_REVIEWED", "reason": "; ".join(dict.fromkeys(box["errors"])) or "no majority",
                                      "votes": [x["verdict"] for x in box["cast"]]}
                it["semantic_status"] = "UNVERIFIED"
                flag(component, iid, "independent verification did not return a majority verdict")
                continue
            it["verification"] = {k: v[k] for k in ("verdict", "problem", "problem_quote", "reviewer_note")}
            if box["votes"] > 1:
                it["verification"]["votes"] = [x["verdict"] for x in box["cast"]]
                it["verification"]["vote_notes"] = [x["reviewer_note"] for x in box["cast"]
                                                    if x["verdict"] != "FAITHFUL" and x.get("reviewer_note")]
            # every judged item gets its semantic status, whether one vote (IMPORTANT) or a majority (CRITICAL) decided it
            it["semantic_status"] = {"FAITHFUL": "FAITHFUL", "INCOMPLETE": "INCOMPLETE", "INCORRECT": "INCORRECT",
                                     "NOT_A_RULE": "NOT_A_RULE"}.get(v["verdict"], "UNVERIFIED")
            if v["verdict"] == "NOT_A_RULE":                    # the verifiers say the text states no rule (L031)
                it["status"], it["not_a_rule"] = "NON_EXECUTABLE_INFORMATIONAL", v.get("reviewer_note")
            if v["verdict"] not in {"FAITHFUL", "NOT_A_RULE"}:
                flag(component, iid, f"independent verification: {v['verdict']} ({v['problem']}) - {v['reviewer_note']}",
                     None, v["problem_quote"] or None)
        self._materiality(ballots, evidence_of, flag)

    def _materiality(self, ballots: dict, evidence_of: dict, flag, batch: int = 10) -> None:
        """Rejected items whose named problems would not change anything a simulation executes (site scope, wording,
        rationale, documentation) are accepted (user decision 2026-09-28). Independent votes (as many as for a CRITICAL
        item) judge, from the reviewers' own notes, whether each problem changes execution; a strict majority saying
        it does not is required, and unsure counts as 'changes'."""
        todo = [(iid, box) for iid, box in ballots.items() if box["item"].get("semantic_status") in {"INCOMPLETE", "INCORRECT"}]
        if not todo:
            return
        votes = self.critical_votes
        jobs = [(todo[i:i + batch], v) for i in range(0, len(todo), batch) for v in range(votes)]

        def run(job):
            chunk, vote = job
            payload = {"instructions": sc.MATERIALITY_INSTRUCTIONS,
                       "items": [{"item_id": iid, "rendering": box["rendering"], "evidence": evidence_of.get(iid, ""),
                                  "reviewer_notes": [x.get("reviewer_note") for x in box["cast"] if x["verdict"] != "FAITHFUL"]} for iid, box in chunk]}
            if vote:
                payload["independent_review"] = f"review {vote + 1} of {votes}: judge from scratch"
            try:
                return self.model.extract("protocol_materiality", sc.MATERIALITY, payload).get("verdicts", [])
            except Exception:  # noqa: BLE001 - a failed call is no vote (and so never an acceptance)
                return []
        with ThreadPoolExecutor(self.workers) as pool:
            results = [v for vs in pool.map(run, jobs) for v in vs]
        cast: dict[str, list] = {}
        for v in results:
            cast.setdefault(v.get("item_id"), []).append(v)
        for iid, box in todo:
            ballots_i = cast.get(iid, [])
            harmless = [v for v in ballots_i if v.get("changes_execution") is False]
            if len(harmless) * 2 > votes:
                it = box["item"]
                it["semantic_status"] = "FAITHFUL"
                it["verification"]["accepted_non_operational"] = {
                    "materiality_votes": [v.get("changes_execution") for v in ballots_i], "reasons": [v.get("reason") for v in harmless],
                    "policy": "accepted: every problem the reviewers named leaves the executed rule unchanged (user decision 2026-09-28)"}
                flag(box["component"], iid, "accepted: the reviewers' objections were judged not to change execution (majority)")

    def _component_text(self, docs: list[Document], component: str) -> str:
        wanted = TASKS[component][0] if component in TASKS else set()
        if component == "radiotherapy":
            wanted = TASKS["treatment"][0]
        parts = []
        for d in docs:
            for s in d.sections:
                if set(self._types.get(d.doc_id, {}).get(s.number, [])) & wanted:
                    parts.append(f"{s.number} {s.title}\n{s.text()}")
                    parts.extend("TABLE: " + json.dumps(t.rows, ensure_ascii=False) for t in s.tables)
        return "\n".join(parts)[:120000]

    # ---------------------------------------------------------------- validation and acceptance gate
    def validate(self, spec: dict, prov: Provenance, review: list[dict]) -> dict:
        checks = []

        def check(name: str, ok: bool, detail: Any = None, critical: bool = True) -> None:
            checks.append({"check": name, "pass": bool(ok), "critical": critical, "detail": detail})
            if not ok:
                review.append({"component": "validation", "item": name, "reason": f"check failed: {detail}", "provenance": None, "text": None})

        verified = [p for p in prov.records if p["quote"]]
        unverified = [p for p in verified if not p["verified"]]
        executable_provenance = {leaf.get("provenance") for _, it, trees in self._items(spec) if ir.executable(it.get("runtime_status", ""))
                                 for t in trees if t for leaf in ex.leaves(t)}
        unsupported_provenance = [p for p in unverified if p["id"] in executable_provenance]
        check("every executable rule's source wording is in the PDF", not unsupported_provenance,
              {"quotes": len(verified), "not_found": len(unverified), "behind_executable_rules": len(unsupported_provenance)})
        for p in unverified:
            review.append({"component": p["component"], "item": p["id"], "reason": f"{p['field']} quote not found in source",
                           "provenance": p["id"], "text": p["quote"]})
        check("treatment arms identified", len(spec["arms"]) >= 1, len(spec["arms"]))
        check("treatment phases identified", len(spec["treatment_phases"]) >= 1, len(spec["treatment_phases"]))
        check("interventions identified", len(spec["interventions"]) >= 1, len(spec["interventions"]))
        check("eligibility criteria identified", any(c["kind"] in {"inclusion", "exclusion"} for c in spec["eligibility"]),
              sum(c["kind"] in {"inclusion", "exclusion"} for c in spec["eligibility"]))
        primary = [e for e in spec["endpoints"] if e["role"] == "primary"]
        check("primary endpoint identified", len(primary) >= 1, [e["name"]["text"] for e in primary if e.get("name")])
        check("analysis population identified", bool(spec["analysis_populations"]) or any(a.get("population") for a in spec["analyses"]),
              len(spec["analysis_populations"]))
        open_arms = [a for a in spec["arms"] if a["status"] == "open"]
        check("at least one open arm in this version", bool(open_arms), [a["label"]["text"] for a in open_arms])
        arm_keys = {_key(a["label"]["text"]) for a in spec["arms"]}
        dangling = sorted({a["text"] for it in spec["interventions"] for a in it["arms"] if a and not _matches_any(a["text"], arm_keys)})
        check("intervention arms match declared arms", not dangling, dangling, critical=False)
        # Executability: every rule tree evaluates without error on empty and on synthetic patients.
        failures = []
        trees = [(_item_id(it), t) for _, it, ts in self._items(spec) for t in ts if t]
        for rid, tree in trees:
            for patient in _synthetic_patients(tree):
                try:
                    ex.evaluate(tree, patient)
                except Exception as exc:  # noqa: BLE001 - any failure is reported by the check
                    failures.append({"rule": rid, "error": repr(exc)})
                    break
        check("rules evaluate on synthetic patients", not failures, failures)
        leaves = [leaf for _, tree in trees for leaf in ex.leaves(tree)]
        executable_leaves = [leaf for leaf in leaves if leaf.get("status") == "EXECUTABLE"]
        unsupported = [leaf for leaf in executable_leaves if leaf.get("kind") not in {"compare", "range", "category", "flag", "table", "window"}]
        check("no unsupported executable rules", not unsupported, len(unsupported))

        # ---- Milestone 4 acceptance gate (fully automatic)
        items = list(self._items(spec))
        critical = [(c, it) for c, it, _ in items if it.get("criticality") == "CRITICAL"]
        verifier_failures = [_item_id(it) for c, it in critical if it.get("semantic_status") in {"INCOMPLETE", "INCORRECT"}]
        unverified_items = [_item_id(it) for c, it in critical if it.get("semantic_status", "UNVERIFIED") == "UNVERIFIED"
                            and c not in {"analyses", "interim"}]
        static_failures = [_item_id(it) for c, it in critical if it.get("static_status") == "FAIL"]
        unresolved = [_item_id(it) for c, it in critical if it.get("runtime_status") == "UNSUPPORTED_RULE_TYPE"]
        source_gaps = [_item_id(it) for c, it, _ in items if it.get("runtime_status") == "UNRESOLVED_IN_SOURCE"]
        source_gaps += ["randomization.allocation"] if spec["randomization"].get("allocation_unresolved_in_source") else []
        tte = [e for e in spec["endpoints"] if e["type"] == "time_to_event" and e["role"] == "primary"]
        tte_incomplete = [e["endpoint_id"] for e in tte if not (
            (e.get("time_origin") or e.get("time_origin_unresolved_in_source")) and any(e.get("events") or [])
            and (any(e.get("censoring") or []) or e.get("censoring_unresolved_in_source")))]
        conditions = {
            "zero_critical_verifier_failures": verifier_failures,
            "zero_critical_unverified": unverified_items,
            "zero_critical_static_failures": static_failures,
            "zero_critical_unresolved_rules": unresolved,
            "zero_unsupported_executable_rules": [leaf.get("provenance") for leaf in unsupported],
            "primary_time_to_event_endpoints_complete": tte_incomplete,
            "zero_spec_level_static_issues": spec.get("static_issues", []),
        }
        failed = {k: v for k, v in conditions.items() if v}
        result = "FAIL" if failed else ("PASS_WITH_SOURCE_GAPS" if source_gaps else "PASS")
        gate = {"result": result, "failed_conditions": failed, "source_gaps": source_gaps,
                "critical_items": len(critical),
                "critical_executable_and_faithful": sum(1 for c, it in critical if it.get("status") == "EXECUTABLE"),
                "rule": "PASS requires every CRITICAL item FAITHFUL, statically valid and executable, no unsupported "
                        "executable rules and complete primary time-to-event endpoints; facts the protocol PDF does not "
                        "state are reported as source gaps (PASS_WITH_SOURCE_GAPS), never invented"}
        by = {}
        for component, it, _ in items:
            key = f"{component}:{it.get('criticality')}"
            b = by.setdefault(key, {"items": 0, "EXECUTABLE": 0})
            b["items"] += 1
            b[it.get("status", "?")] = b.get(it.get("status", "?"), 0) + 1
        summary = {
            "gate": result, "quotes": len(verified), "quotes_not_found": len(unverified),
            "arms": len(spec["arms"]), "open_arms": len(open_arms), "phases": len(spec["treatment_phases"]),
            "interventions": len(spec["interventions"]), "radiotherapy_targets": sum(len(c["targets"]) for c in spec["radiotherapy"]),
            "eligibility_criteria": len(spec["eligibility"]),
            "dose_modification_rules": len(spec["dose_modifications"]), "grade_definitions": len(spec["grade_definitions"]),
            "assessment_schedules": len(spec["assessments"]), "endpoints": len(spec["endpoints"]),
            "primary_endpoints": len(primary), "analyses": len(spec["analyses"]), "interim_rules": len(spec["interim_analyses"]),
            "strata": len(spec["stratification"]["strata"]), "rule_leaves": len(leaves), "executable_leaves": len(executable_leaves),
            "variables": len(spec["variables"]), "critical_items": len(critical),
            "critical_executable_and_faithful": gate["critical_executable_and_faithful"],
            "status_by_component_and_criticality": by,
        }
        return {"summary": summary, "checks": checks, "gate": gate,
                "accuracy_against_gold": "not measured: no gold-standard StudySpec exists for this protocol yet"}


# ----------------------------------------------------------------------------- utilities


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _weekdays(text: str | None) -> list[str] | None:
    """Day names written in an administration rule ('Friday, Saturday, and Sunday'; 'Mon., Tues.')."""
    found = []
    for word in re.findall(r"[a-z]+", (text or "").casefold()):
        for day in WEEKDAYS:
            if len(word) >= 3 and day.startswith(word) and day not in found:
                found.append(day)
    return found or None


def _ratio(text: str | None) -> dict | None:
    """'1:1', '2:1', 'equal allocation' -> {'ratio': [..], 'text': ...}."""
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*[:]\s*(\d+(?:\.\d+)?)(?:\s*[:]\s*(\d+(?:\.\d+)?))?", text)
    if m:
        return {"ratio": [float(x) for x in m.groups() if x], "text": text}
    if re.search(r"\b(equal|equally|1 to 1|one to one)\b", text.casefold().replace("_", " ")):
        return {"ratio": [1.0, 1.0], "text": text}
    return None


def _monitor(i: dict) -> dict:
    """Executable parameters of an interim or safety monitoring rule, parsed from quotes only."""
    missing: list[str] = []

    def frac(q: str) -> float | None:
        return _as_fraction(ex.parse_number(q), q) if q else None

    if i["method_family"] == "BAYESIAN_POSTERIOR":
        prior = ex.numbers(i["prior_quote"])
        params = {"type": "bayesian_posterior", "prior": {"family": "beta", "a": prior[0], "b": prior[1]} if len(prior) >= 2 else None,
                  "threshold": frac(i["threshold_quote"]), "posterior_cutoff": frac(i["posterior_cutoff_quote"])}
        missing = [k for k in ("prior", "threshold", "posterior_cutoff") if params[k] is None]
    elif i["method_family"] == "CONDITIONAL_POWER":
        params = {"type": "conditional_power", "futility_cutoff": frac(i["futility_cutoff_quote"])}
        missing = [k for k in ("futility_cutoff",) if params[k] is None]
    elif i["method_family"] == "ALPHA_SPENDING":
        # the exponent of a power-family spending function is written glued to t ('αt2', 't^2', 't**3')
        exponent = re.search(r"t\s*(?:\^|\*\*)?\s*(\d+(?:\.\d+)?)", i["spending_parameter_quote"] or "")
        rho = float(exponent.group(1)) if (exponent and i["spending_family"] == "POWER_FAMILY") else None
        info = ex.parse_number(i["information_quote"])
        params = {"type": "alpha_spending", "family": i["spending_family"], "alpha": frac(i["alpha_quote"]),
                  "rho": rho, "full_information": info}
        missing = [k for k in ("alpha", "full_information") if params[k] is None]
        if i["spending_family"] == "POWER_FAMILY" and rho is None:
            missing.append("rho")
    else:
        params = {"type": "other"}
        missing = ["method"]
    params["missing"] = missing
    params["runtime_status"] = "EXECUTABLE_NOW" if not missing else "UNSUPPORTED_RULE_TYPE"
    return params


VERDICTS = ("INCORRECT", "INCOMPLETE", "NOT_A_RULE", "FAITHFUL")  # most severe first


def _majority(cast: list[dict], votes: int) -> dict | None:
    """The verdict of a strict majority of the votes requested (a failed call counts as no vote), or
    None when there is no majority. A majority that rejects the item but disagrees on how is reported
    as its most severe rejection. With a single vote this is that vote. The returned verdict carries
    the note of the first vote that cast it."""
    for verdict in VERDICTS:
        agreeing = [v for v in cast if v["verdict"] == verdict]
        if len(agreeing) * 2 > votes:
            return agreeing[0]
    rejecting = [v for v in cast if v["verdict"] in {"INCORRECT", "INCOMPLETE"}]
    if len(rejecting) * 2 > votes:
        return min(rejecting, key=lambda v: VERDICTS.index(v["verdict"]))
    return None


def _evidence(item: dict, tree: dict | None, field: str = "evidence") -> str:
    """All protocol wording an item was compiled from: its evidence quote plus every leaf quote. When
    the evidence quote itself could not be located, every verified quote of the item stands in."""
    parts = [render._q(item.get(field))] + [leaf.get("text") or "" for leaf in ex.leaves(tree)]
    if not render._q(item.get(field)):
        parts += _verified_quotes(item)
    return " | ".join(dict.fromkeys(x.strip() for x in parts if x and x.strip()))


def _verified_quotes(obj: Any, skip: frozenset = frozenset({"verification", "rendering", "repair"})) -> list[str]:
    """Every verified protocol quote inside a compiled item, in order."""
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str) and obj.get("verified") is True and "provenance" in obj:
            return [obj["text"]]
        return [q for k, v in obj.items() if k not in skip for q in _verified_quotes(v, skip)]
    if isinstance(obj, list):
        return [q for v in obj for q in _verified_quotes(v, skip)]
    return []


def _unit_or_text(text: str | None) -> str | None:
    """A recognised unit in canonical form; otherwise the wording as written (whitespace tidied)."""
    unit = ex.parse_unit(text)
    if unit in ex.TIME_TO_DAYS or (unit and re.fullmatch(r"[a-z%/0-9.]{1,12}", unit) and " " not in (text or "").strip()):
        return unit
    return re.sub(r"\s+", " ", text or "").strip() or None


def _mentions(text: str | None, word: str) -> bool:
    return bool(text) and bool(re.search(r"\b" + word + r"s?\b", text.casefold()))


RESIDUAL_CLASSES = {
    "renderer_or_ir_gap": "the verified quotes hold the missing detail but the structure or its rendering cannot carry it",
    "extraction_error": "the extracted value or logic contradicts the protocol wording",
    "unverified": "no majority verdict was returned",
}


def _classify_residual(spec: dict, items) -> list[dict]:
    """Every item still not faithful after the resolve loop, with a root-cause class for the improvement agent."""
    out = []
    for component, it, _ in items:
        v = it.get("semantic_status")
        if v not in {"INCOMPLETE", "INCORRECT", "UNVERIFIED"}:
            continue
        ver = it.get("verification") or {}
        quote = " ".join((ver.get("problem_quote") or "").split()).casefold()
        held = bool(quote) and quote[:40] in " ".join(json.dumps(it, ensure_ascii=False).split()).casefold()
        cls = "unverified" if v == "UNVERIFIED" else "renderer_or_ir_gap" if v == "INCOMPLETE" and held else "extraction_error"
        out.append({"component": component, "item": _item_id(it), "verdict": v, "class": cls, "why": RESIDUAL_CLASSES[cls],
                    "note": ver.get("reviewer_note"), "protocol_wording": ver.get("problem_quote"), "rendering": it.get("rendering")})
    return out


def _to_agent_backlog(protocol_id: str, residual: list[dict]) -> None:
    """Append residual extraction failures to the improvement agent's backlog (data/agent/extraction_backlog.jsonl)."""
    if not residual:
        return
    path = Path("data/agent/extraction_backlog.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).isoformat()
    with open(path, "a", encoding="utf-8") as fh:
        for r in residual:
            fh.write(json.dumps({"recorded": stamp, "protocol": protocol_id, **r}, ensure_ascii=False) + "\n")


def _render_quantity(q: dict) -> str:
    """A sample-size statement in plain words (quantity, value, unit, and the stated text)."""
    t = render._q(q.get("text")) or ""
    return f"{(q.get('quantity') or '').replace('_', ' ')}: {q.get('value')} {q.get('unit') or ''}".strip() + (f" (stated as '{t}')" if t else "")


def _render_discontinuation(d: dict) -> str:
    """A discontinuation rule in plain words: scope, trigger, criterion and any time limit."""
    tl = d.get("time_limit") or {}
    limit = f"; time limit {tl.get('days')} days from {tl.get('canonical_anchor')}" if tl.get("days") else ""
    return (f"{(d.get('scope') or '').replace('_', ' ')} when {(d.get('trigger') or '').replace('_', ' ')}: "
            f"'{render._q(d.get('criterion')) or ''}'{limit}")


def _item_id(item: dict) -> str:
    # most specific first: an intervention also carries the phase_id of its phase
    for k in ("intervention_id", "target_id", "criterion_id", "stratum_id", "rule_id", "decision_rule_id", "endpoint_id", "analysis_id",
              "interim_id", "scale_id", "sample_size_id", "phase_id"):
        if k in item:
            return item[k]
    return "?"


def _with_q(parsed: dict | None, quote: dict | None) -> dict | None:
    if parsed is None and quote is None:
        return None
    return {**(parsed or {}), "text": quote}


_SIDEDNESS = re.compile(r"\b(?:one|two|1|2)[\s-]*(?:sided|tailed)\b", re.IGNORECASE)
_STAT_NUMBER = re.compile(r"(?<![A-Za-z\d.])(\d+(?:\.\d+)?)\s*(%|percent)?", re.IGNORECASE)   # 'p0', 'H1' are names


def _as_fraction(value: float | None, text: str | None) -> float | None:
    """A statistical parameter (alpha, power) as a fraction, read from its quote. Sidedness ('one-sided', '2-sided')
    is not the parameter: it is removed before the first remaining number is read; a number marked % (or above 1) is a
    percentage. Without a quote the parsed value is used as before."""
    if text:
        m = _STAT_NUMBER.search(_SIDEDNESS.sub(" ", text))
        if m:
            v = float(m.group(1))
            return v / 100 if m.group(2) or v > 1 else v
    if value is None:
        return None
    return value / 100 if "%" in (text or "") or value > 1 else value


def _matches_any(text: str, keys: set[str]) -> bool:
    k = _key(text)
    return any(k == other or k in other or other in k for other in keys if other)


def parse_timepoint(header: str | None) -> dict:
    """Assessment column headers -> time point: an offset ('3 mos', '2.0 yrs'), a range of periods
    ('Weeks 1-6'), or an event-relative point ('Pre-Study', 'Prior to Each Cycle', 'At Relapse')."""
    text = re.sub(r"\s+", " ", header or "").strip()
    low = text.casefold()
    unit = None
    for word in re.findall(r"[a-z]+", low):
        u = ex.parse_unit(word)
        if u in ex.TIME_TO_DAYS:
            unit = u
            break
    nums = ex.numbers(text)
    if unit and len(nums) >= 2 and re.search(r"\d\s*(-|to)\s*\d", text):
        return {"kind": "period_range", "from": nums[0], "to": nums[1], "unit": unit}
    if unit and nums:
        return {"kind": "offset", "value": nums[0], "unit": unit, "days": ex.to_days(nums[0], unit)}
    if re.search(r"annual|yearly|every year", low):
        return {"kind": "recurring", "every": 1, "unit": "year"}
    if text:
        return {"kind": "event_relative", "text": text}
    return {"kind": "unparsed", "text": text}


def _synthetic_patients(tree: dict) -> list[dict]:
    """Empty patient, and patients with every variable present at low / mid / high values."""
    variables: dict[str, list] = {}
    for leaf in ex.leaves(tree):
        var = leaf.get("variable")
        if not var:
            continue
        if leaf["kind"] in {"compare", "range", "table"}:
            v = leaf.get("value") or leaf.get("lower") or leaf.get("upper") or 1.0
            variables.setdefault(var, [])
            variables[var] += [0.0, float(v), float(v) * 10]
            if leaf.get("reference"):
                variables.setdefault(leaf["reference"]["variable"], []).append(1.0)
        elif leaf["kind"] == "category":
            variables.setdefault(var, []).extend(list(leaf["categories"]) + ["__other__"])
        elif leaf["kind"] == "window":
            variables.setdefault(var, []).extend([-10.0, 0.0, 10.0])
        elif leaf["kind"] == "flag":
            variables.setdefault(var, []).extend([True, False])
    patients = [{}]
    for i in range(3):
        patients.append({var: {"value": vals[min(i, len(vals) - 1)], "unit": None} for var, vals in variables.items()})
    return patients


def fingerprint(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()
