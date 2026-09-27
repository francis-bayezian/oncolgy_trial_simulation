"""Linked-abstract facts: rules, model fallback, validation and reconciliation."""

from fakes import FakeModel, mentions_for, standard_terminology
from test_accuracy_fixes import SELECTION, crossover_study, enriched

from clinical_asset.abstract_evidence import Resources, agrees, extract_publication_evidence
from clinical_asset.publications import Publication
from clinical_asset.registry import parse_study
from clinical_asset.report import build_asset_and_reconciliation, build_audit

# Drug A: 48 treated, Drug B: 45 treated (registry safety denominators in the fixture).
ABSTRACT = (
    "Background Drug A is a targeted agent. "
    "Methods We recruited patients who progressed after previous platinum-based chemotherapy "
    "and a PD-1 or PD-L1 inhibitor. "
    "Findings After a median follow-up of 12·0 months (IQR 10·1-14·2), grade 3 "
    "or worse treatment-related adverse events occurred with Drug A compared with Drug B "
    "(n=12 [25%] vs n=18 [40%]). "
    "For Drug A, the most common treatment-related adverse events of grade 3 or worse were "
    "diarrhoea (n=6 [13%]) and alanine aminotransferase increase (n=3 [6%]). "
    "Interpretation Drug A was better tolerated. Funding Sponsor."
)
ORR_SENTENCE = (
    "The objective response rate was 28.1% with Drug A and 13.2% with Drug B, and 21.0% among "
    "Drug A patients with liver metastases."
)


def publication(text: str | None) -> Publication:
    return Publication(
        pmid="999", doi="", pmcid="", url="", citation="", registry_reference_type="RESULT",
        retrieval_status="retrieved" if text else "text_unavailable",
        text_source="abstract" if text else None,
        paragraphs=[{"section": "abstract", "kind": "paragraph", "text": text}] if text else [],
    )


def run(text: str | None, model: FakeModel | None = None, study: dict | None = None):
    model = model or FakeModel(SELECTION)
    parsed, _ = enriched(study, model)
    terminology = standard_terminology()
    evidence = extract_publication_evidence(
        parsed, [publication(text)], Resources(terminology, model, mentions_for(terminology))
    )
    asset, log = build_asset_and_reconciliation(parsed, [publication(text)], evidence)
    return parsed, evidence, asset, log


def arm_profiles(asset: dict) -> dict:
    return {
        p["source"]["registry_group"]: p for p in asset["clinical_profiles"] if p["profile_type"] == "randomized_arm"
    }


def test_rule_facts_are_attributed_and_checked_against_denominators() -> None:
    methods = FakeModel({
        **SELECTION,
        "selection_criteria": lambda payload: (
            {"criteria": [{"kind": "required_prior_therapy", "concept_quote": "PD-L1 inhibitor",
                           "qualifier_quote": "a PD-1 or PD-L1 inhibitor"},
                          {"kind": "required_prior_therapy", "concept_quote": "platinum-based chemotherapy",
                           "qualifier_quote": "previous"}]}
            if "platinum" in payload["eligibility_text"] else SELECTION["selection_criteria"]
        ),
    })
    _, _, asset, _ = run(ABSTRACT, methods)
    profiles = arm_profiles(asset)
    tox_a = profiles["Drug A"]["toxicity"]
    assert tox_a["grade_3_plus_treatment_related_AE"] == {"n": 12, "N": 48, "rate": 0.25, "source": "PMID:999"}
    assert profiles["Drug B"]["toxicity"]["grade_3_plus_treatment_related_AE"]["n"] == 18
    events = tox_a["key_grade_3_plus_treatment_related_events"]["events"]
    assert events["alanine_aminotransferase_increased"]["n"] == 3
    assert profiles["Drug A"]["efficacy"]["follow_up"][0]["value"] == 12.0
    therapies = {e["umls_cui"] for e in profiles["Drug A"]["selection_context"]["required_prior_therapy"]}
    # "a PD-1 or PD-L1 inhibitor" expands to both concepts by grammar.
    assert therapies == {"C_PLAT", "C_PD1", "C_PDL1"}


def test_swapped_arm_values_are_rejected_not_attributed() -> None:
    swapped = ABSTRACT.replace("(n=12 [25%] vs n=18 [40%])", "(n=12 [27%] vs n=18 [38%])")
    _, evidence, asset, _ = run(swapped)
    assert "grade_3_plus_treatment_related_AE" not in arm_profiles(asset)["Drug A"]["toxicity"]
    problems = [p for s in evidence[0].sentence_log for p in s.get("problems", [])]
    assert "attribution_conflict_swapped_arms" in problems


def _orr_answer(payload: dict) -> dict:
    base = {"category": "efficacy", "comparator_quote": "", "statistic": "rate", "ci_quote": "",
            "p_value_quote": "", "outcome_quote": "objective response rate", "evidence_quote": payload["source_sentence"]}
    return {
        "status": "RELATIONSHIPS",
        "relationships": [
            {**base, "population_scope": "whole_arm", "population_quote": "", "treatment_quote": "Drug A", "value_quote": "28.1%"},
            {**base, "population_scope": "whole_arm", "population_quote": "", "treatment_quote": "Drug B", "value_quote": "13.2%"},
            {**base, "population_scope": "subgroup", "population_quote": "patients with liver metastases",
             "treatment_quote": "Drug A", "value_quote": "21.0%"},
            # Hallucinated number: not in the sentence, must be rejected.
            {**base, "population_scope": "whole_arm", "population_quote": "", "treatment_quote": "Drug B", "value_quote": "31.0%"},
            # Unknown arm: must be rejected.
            {**base, "population_scope": "whole_arm", "population_quote": "", "treatment_quote": "patients", "value_quote": "13.2%"},
        ],
    }


def test_model_fallback_is_quote_validated_and_creates_subgroups() -> None:
    model = FakeModel({**SELECTION, "clinical_relationships": _orr_answer})
    _, evidence, asset, _ = run(f"Findings {ORR_SENTENCE}", model)
    profiles = arm_profiles(asset)
    assert profiles["Drug A"]["efficacy"]["objective_response_rate"][0]["rate"] == 0.281
    assert profiles["Drug B"]["efficacy"]["objective_response_rate"][0]["rate"] == 0.132
    subgroup = next(p for p in asset["clinical_profiles"] if p.get("definition") == "patients with liver metastases")
    assert subgroup["definition"] == "patients with liver metastases"
    assert subgroup["efficacy"]["objective_response_rate"][0]["rate"] == 0.21
    reasons = [entry.get("reason") for entry in evidence[0].model_log if "answer" in entry]
    assert "value_quote_not_in_source" in reasons
    assert "treatment_not_exactly_one_registry_arm" in reasons


def test_publication_duplicate_is_merged_and_conflict_is_kept_out() -> None:
    study = crossover_study()
    outcome = study["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    outcome.update(title="Progression-free Survival (PFS)", populationDescription="Full analysis set",
                   paramType="MEDIAN", unitOfMeasure="months")
    outcome["classes"][0]["categories"][0]["measurements"] = [
        {"groupId": "OG0", "value": "5.62", "lowerLimit": "4.27", "upperLimit": "7.75"},
        {"groupId": "OG1", "value": "4.47", "lowerLimit": "3.02", "upperLimit": "5.68"},
    ]
    same = ("Findings Median progression-free survival was 5·6 months [95% CI 4·3-7·8] vs "
            "4·5 months [3·0-5·7] for Drug A compared with Drug B.")
    different = same.replace("5·6 months", "6·9 months")

    _, _, merged, _ = run(same, study=study)
    [pfs] = arm_profiles(merged)["Drug A"]["efficacy"]["progression_free_survival"]
    assert (pfs["statistic"], pfs["value"], pfs["unit"]) == ("median", 5.62, "month")
    assert pfs["sources"] == ["registry", "PMID:999"]

    _, _, conflicted, log = run(different, study=study)
    [pfs] = arm_profiles(conflicted)["Drug A"]["efficacy"]["progression_free_survival"]
    assert pfs["value"] == 5.62 and "sources" not in pfs
    assert any(r["reconciliation"] == "CONFLICT" and r.get("key") == "progression_free_survival" for r in log)


def test_trial_without_linked_abstract_gets_no_publication_facts() -> None:
    parsed = parse_study(crossover_study())
    _, evidence, asset, _ = run(None)
    assert "grade_3_plus" not in str(asset)
    assert evidence[0].sentence_log[0]["status"] == "NO_ABSTRACT"
    assert "PMID" not in str(build_audit(parsed, [])["withheld_from_asset"])


def test_rounding_agreement() -> None:
    assert agrees(0.663, "0.66")
    assert agrees(0.002, "0.0017")
    assert agrees(7.75, "7.8")
    assert not agrees(5.62, "5.9")
