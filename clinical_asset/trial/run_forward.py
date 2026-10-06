"""Run-forward policy for StudySpec items (one rule for every stage, any protocol).

An EXECUTABLE item runs. An item the verifiers flagged REVIEW_REQUIRED runs as compiled when their verdict is that its
meaning is right (FAITHFUL, or INCOMPLETE: a detail missing); when they judged it INCORRECT (a reversed bound, a wrong
value: e.g. creatinine clearance '< 60 but >= 30' compiled as '>= 60 and <= 30', or alpha 1.0) its compiled logic is
NOT used: the stage treats the item as unknown and resolves it the way it resolves any unknown, so a misread item can
never drive a result.
"""

WRONG = {"INCORRECT", "NOT_A_RULE"}


def use_compiled_logic(item: dict) -> bool:
    if item.get("status") == "EXECUTABLE":
        return True
    verdict = item.get("semantic_status") or (item.get("verification") or {}).get("verdict")
    return verdict not in WRONG


def flag(item: dict) -> str | None:
    """None when the item runs unflagged; else why it is flagged."""
    if item.get("status") == "EXECUTABLE":
        return None
    return "compiled logic not used (verifiers: incorrect)" if not use_compiled_logic(item) else "run as compiled (review flag)"


def analysis_alpha(analysis: dict) -> dict:
    """The analysis's alpha: the compiled value when plausible (0 < alpha <= 0.5); else the deterministic parse of its
    verified quote (lesson L003: '1-sided 0.025' had been stored as 1.0); else the conventional level for its
    sidedness (0.025 one-sided, 0.05 two-sided), flagged as an assumption."""
    from ..protocol import expressions as ex
    from ..protocol.compiler import _as_fraction

    a = analysis.get("alpha") or {}
    value = a.get("value") if isinstance(a, dict) else a
    if isinstance(value, (int, float)) and 0 < value <= 0.5:
        return {"value": float(value), "source": "compiled"}
    quote = ((a.get("text") or {}).get("text") if isinstance(a.get("text"), dict) else a.get("text")) if isinstance(a, dict) else None
    if quote:
        parsed = _as_fraction(ex.parse_number(quote), quote)
        if parsed is not None and 0 < parsed <= 0.5:
            return {"value": float(parsed), "source": f"re-parsed from the verified quote '{quote}'"}
    one_sided = analysis.get("sidedness") == "one_sided"
    return {"value": 0.025 if one_sided else 0.05, "source": "assumption: conventional level for the stated sidedness (no usable alpha)"}
