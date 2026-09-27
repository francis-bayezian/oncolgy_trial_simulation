"""Explicit boundaries between source evidence and the clinical asset."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuditItem:
    kind: str
    source_path: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClinicalProfile:
    source_nct: str
    source_arm: str
    source_population: str
    disease: str | None = None
    histology: str | None = None
    setting: str | None = None
    primary_biomarker: str | None = None
    primary_drug: str | None = None
    drug_class: str | None = None
    cancer: dict[str, Any] = field(default_factory=dict)
    patient_group: dict[str, Any] = field(default_factory=dict)
    treatment: dict[str, Any] = field(default_factory=dict)
    baseline: dict[str, Any] = field(default_factory=dict)
    longitudinal: list[dict[str, Any]] = field(default_factory=list)
    response: dict[str, Any] = field(default_factory=dict)
    survival: dict[str, Any] = field(default_factory=dict)
    toxicity: dict[str, Any] = field(default_factory=dict)
    treatment_course: dict[str, Any] = field(default_factory=dict)
    comparative_effects: list[dict[str, Any]] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)

    def as_asset(self) -> dict[str, Any]:
        """Omit empty clinical sections; never include audit metadata."""
        result: dict[str, Any] = {}
        for key in (
            "cancer",
            "patient_group",
            "treatment",
            "baseline",
            "longitudinal",
            "response",
            "survival",
            "toxicity",
            "treatment_course",
            "comparative_effects",
            "source",
        ):
            value = getattr(self, key)
            if value:
                result[key] = value
        return result


@dataclass
class ParsedStudy:
    nct_id: str
    study_title: str
    study_url: str
    eligible: bool
    exclusion_reason: str | None
    profiles: list[ClinicalProfile] = field(default_factory=list)
    audit: list[AuditItem] = field(default_factory=list)
    result_references: list[dict[str, str]] = field(default_factory=list)
    safety_reporting: dict[str, Any] = field(default_factory=dict)
    allocation: str | None = None
    source_conflicts: list[dict[str, Any]] = field(default_factory=list)
