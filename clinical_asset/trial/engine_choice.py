"""The primary engine for a StudySpec (any protocol), chosen from what its own parsers can execute:
escalation when a dose-escalation rule exists; time-to-event when the primary endpoint is time-to-event and there is
more than one arm; non-inferiority only when the NI design parser resolves a preserved-fraction design (a stray word
such as 'preserve' in the analyses is not enough); binary otherwise."""

import json
import sys


def choose(spec: dict) -> str:
    from .noninferiority import design

    if any(r.get("kind") == "dose_escalation" for r in spec.get("decision_rules") or []):
        return "escalation"
    from .continuous import design as continuous_design

    if continuous_design(spec).get("status") == "RESOLVED":     # a continuous comparison with a stated design (L034)
        return "continuous"
    primary = [e for e in spec.get("endpoints") or [] if e.get("role") == "primary"]
    if any(e.get("type") == "time_to_event" for e in primary) and len(spec.get("arms") or []) > 1:
        return "tte"
    if len(spec.get("arms") or []) > 1 and any(e.get("type") == "binary" for e in primary):
        try:
            if design(spec).get("status") == "RESOLVED":
                return "ni"
        except Exception:  # noqa: BLE001 - an unparseable NI design is not an NI engine
            pass
    return "binary"


if __name__ == "__main__":
    print(choose(json.load(open(sys.argv[1], encoding="utf-8"))))
