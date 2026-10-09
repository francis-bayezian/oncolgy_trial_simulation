"""StudySpec intermediate representation, version 1.1: controlled vocabularies and status model.

Every compiled item carries two independent statuses:

* semantic_status - is the item a faithful compilation of the protocol text?
    FAITHFUL      the independent verifier judged it equivalent to the text
    INCOMPLETE    something stated in the text is missing
    INCORRECT     something is wrong or added
    UNVERIFIED    not yet judged, or its source wording could not be verified in the PDF
* runtime_status - can a simulator execute it?
    EXECUTABLE_NOW                        all parts compiled and every variable is simulated today
    EXECUTABLE_AFTER_VARIABLE_AVAILABLE   compiled, but a patient variable is not simulated yet
    OPTIONAL_POLICY                       an optional or recommended action (may / should)
    UNSUPPORTED_RULE_TYPE                 a part could not be expressed in the rule language
    UNRESOLVED_IN_SOURCE                  the protocol does not state what is needed
    NON_EXECUTABLE_INFORMATIONAL          notes, administration, restrictions without a test

and a criticality (CRITICAL / IMPORTANT / INFORMATIONAL) that decides whether it gates the
Milestone 4 acceptance.
"""

MODALITY = ("REQUIRED", "PROHIBITED", "OPTIONAL", "RECOMMENDED", "STRONGLY_RECOMMENDED")
DETERMINISTIC_MODALITIES = {"REQUIRED", "PROHIBITED"}

TEMPORAL_RELATION = ("WITHIN_BEFORE", "WITHIN_AFTER", "BEFORE", "AFTER", "AT_LEAST_BEFORE", "AT_LEAST_AFTER",
                     "MORE_THAN_BEFORE", "MORE_THAN_AFTER", "ON_OR_BEFORE", "ON_CYCLE_DAY", "SAME_DAY", "NONE")
CALENDAR_ADJUSTMENT = ("NONE", "NEXT_BUSINESS_DAY_IF_NON_BUSINESS_DAY", "PREVIOUS_BUSINESS_DAY_IF_NON_BUSINESS_DAY")

EVENT_STATES = ("SCHEDULED", "DUE", "ADMINISTERED", "HELD", "DELAYED", "OMITTED", "COMPLETED", "DISCONTINUED",
                "CANCELLED", "NOT_ADMINISTERED",
                # a condition's course and a procedure's occurrence (a change of state, not a value at one time)
                "RESOLVED", "NOT_RESOLVED", "IMPROVED", "WORSENED", "PERFORMED", "DIAGNOSED")

SEMANTIC = ("FAITHFUL", "INCOMPLETE", "INCORRECT", "UNVERIFIED")
RUNTIME = ("EXECUTABLE_NOW", "EXECUTABLE_AFTER_VARIABLE_AVAILABLE", "OPTIONAL_POLICY", "UNSUPPORTED_RULE_TYPE",
           "UNRESOLVED_IN_SOURCE", "NON_EXECUTABLE_INFORMATIONAL")
CRITICALITY = ("CRITICAL", "IMPORTANT", "INFORMATIONAL")

# Patient variables the current population generator (Parameter Asset V3) can produce. A rule on any
# other variable is valid and compiled, but executes only once that variable is simulated.
SIMULATED_VARIABLES = frozenset({"demographic:age", "demographic:sex", "demographic:race", "demographic:ethnicity"})

# Variables that describe the trial's own events and schedule (created by the simulator itself,
# never by the population model): timing windows, event states, cycle days, days of the week.
SIMULATOR_VARIABLE_PREFIXES = ("timing:", "event:", "cycle:", "calendar:", "count:", "grade:")


def criticality(component: str, item: dict) -> str:
    """Which items gate acceptance: what a trial simulation cannot run without. An item rewritten by
    automatic repair keeps the more severe of its old and new criticality until the independent
    verifier confirms the rewrite, so a repair cannot lower the bar by changing kind or modality."""
    own = _criticality(component, item)
    before = item.get("criticality_before_repair")
    if before and item.get("semantic_status") != "FAITHFUL" and CRITICALITY.index(before) < CRITICALITY.index(own):
        return before
    return own


def _criticality(component: str, item: dict) -> str:
    modality = item.get("modality", "REQUIRED")
    if component == "eligibility":
        if item.get("kind") in {"inclusion", "exclusion"}:
            return "CRITICAL" if modality in DETERMINISTIC_MODALITIES else "IMPORTANT"
        if item.get("kind") == "timing":
            return "IMPORTANT"
        return "INFORMATIONAL"
    if component in {"arms", "randomization", "stratification", "radiotherapy"}:
        return "CRITICAL"
    if component == "treatment":
        if "intervention_id" in item:
            if item.get("modality") in {"OPTIONAL", "RECOMMENDED", "STRONGLY_RECOMMENDED"}:
                return "IMPORTANT"
            return "CRITICAL" if item.get("modality_class") != "supportive" else "IMPORTANT"
        return "CRITICAL"  # phases
    if component == "dose_modification":
        return "CRITICAL" if modality in DETERMINISTIC_MODALITIES else "IMPORTANT"
    if component == "endpoints":
        return "CRITICAL" if item.get("role") == "primary" else "IMPORTANT"
    if component == "analyses":
        return "CRITICAL" if item.get("primary") else "IMPORTANT"
    if component == "decision_rules":
        return "CRITICAL" if item.get("role") == "primary" else "IMPORTANT"
    if component in {"interim", "assessments", "discontinuation", "grades"}:
        return "IMPORTANT"
    return "INFORMATIONAL"


def runtime_from_leaves(leaves: list[dict], modality: str = "REQUIRED") -> str:
    """Runtime status of a rule tree from its leaves and the modality of the rule."""
    if modality not in DETERMINISTIC_MODALITIES:
        return "OPTIONAL_POLICY"
    if not leaves:
        return "UNSUPPORTED_RULE_TYPE"
    if any(leaf.get("status") != "EXECUTABLE" for leaf in leaves):
        if any(leaf.get("unresolved_in_source") for leaf in leaves):
            return "UNRESOLVED_IN_SOURCE"
        return "UNSUPPORTED_RULE_TYPE"
    variables = {leaf.get("variable") for leaf in leaves if leaf.get("variable")}
    for row_leaf in leaves:
        for row in row_leaf.get("rows") or []:
            variables |= {x.get("variable") for x in _row_leaves(row["when"]) if x.get("variable")}
    unsimulated = [v for v in variables if v not in SIMULATED_VARIABLES and not v.startswith(SIMULATOR_VARIABLE_PREFIXES)]
    return "EXECUTABLE_AFTER_VARIABLE_AVAILABLE" if unsimulated else "EXECUTABLE_NOW"


def _row_leaves(node: dict | None) -> list[dict]:
    if not node:
        return []
    if node.get("node") in {"AND", "OR"}:
        return [x for c in node["children"] for x in _row_leaves(c)]
    return [node] if node.get("node") == "LEAF" else []


def executable(runtime_status: str) -> bool:
    return runtime_status in {"EXECUTABLE_NOW", "EXECUTABLE_AFTER_VARIABLE_AVAILABLE"}
