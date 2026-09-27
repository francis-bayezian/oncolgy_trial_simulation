"""Offline stand-ins for UMLS and GPT-5.6 Luna so tests never load models or call the API.

Test data may name drugs and diseases; the pipeline code under test may not.
"""

import re
from typing import Any

from clinical_asset.nlp import Mention
from clinical_asset.terminology import Concept, concept_mentions


def _norm(text: str) -> str:
    return re.sub(r"[\s\-_/,]+", " ", text.casefold()).strip()


class FakeTerminology:
    def __init__(
        self,
        concepts: dict[str, tuple[str, str, tuple[str, ...]]],
        definitions: dict[str, str] | None = None,
        aliases: dict[str, list[str]] | None = None,
    ) -> None:
        self.concepts = {_norm(k): v for k, v in concepts.items()}
        self.definitions = definitions or {}
        self._aliases = aliases or {}

    def link(self, text: str, allowed_types: frozenset[str] | None = None, min_score: float = 0.85) -> Concept | None:
        found = self.concepts.get(_norm(text or ""))
        if not found:
            return None
        cui, name, types = found
        if allowed_types and not set(types) & allowed_types:
            return None
        return Concept(cui, name, types, 1.0, True)

    probe = link

    def definition(self, cui: str) -> str | None:
        return self.definitions.get(cui)

    def aliases(self, cui: str) -> list[str]:
        return self._aliases.get(cui, [])


def mentions_for(terminology: FakeTerminology):
    def detect(text: str) -> list[Mention]:
        return [
            Mention(text[start:end], start, end, concept.types, cui=concept.cui)
            for start, end, concept in concept_mentions(text, terminology)
        ]

    return detect


class FakeModel:
    """Returns canned answers per task; a callable answer receives the payload."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []

    def extract(self, task: str, schema: dict, payload: dict) -> dict:
        self.calls.append((task, payload))
        answer = self.answers.get(task, {})
        return answer(payload) if callable(answer) else answer


# Concepts used across tests (test data, not pipeline vocabulary).
DRUG = ("T121",)
NEO = ("T191",)
FINDING = ("T184",)
STANDARD_CONCEPTS = {
    "Drug A": ("C_A", "drug a", DRUG),
    "Drug B": ("C_B", "drug b", DRUG),
    "Metastatic NSCLC": ("C_MNSCLC", "Metastatic non-small cell lung carcinoma", NEO),
    "NSCLC": ("C_NSCLC", "Non-Small Cell Lung Carcinoma", NEO),
    "KRAS": ("C_KRAS", "KRAS gene", ("T028",)),
    "KRAS p.G12C": ("C_G12C", "KRAS p.G12C", ("T049",)),
    "Pneumonia": ("C_PNEU", "Pneumonia", ("T047",)),
    "Rare event": ("C_RARE", "Rare event", FINDING),
    "Non-small cell lung cancer": ("C_NSCLC", "Non-Small Cell Lung Carcinoma", NEO),
    "Progression-free Survival": ("C_PFS", "Progression-Free Survival", ("T081",)),
    "progression-free survival": ("C_PFS", "Progression-Free Survival", ("T081",)),
    "objective response rate": ("C_ORR", "Objective response rate", ("T081",)),
    "diarrhoea": ("C_DIA", "Diarrhea", FINDING),
    "alanine aminotransferase increase": ("C_ALT", "Alanine Aminotransferase Increased", ("T033",)),
    "brain metastases": ("C_BRAIN", "Metastatic malignant neoplasm to brain", NEO),
    "platinum-based chemotherapy": ("C_PLAT", "Platinum Antineoplastic Compound", DRUG),
    "PD-1 inhibitor": ("C_PD1", "PD-1 inhibitor", DRUG),
    "PD-L1 inhibitor": ("C_PDL1", "PD-L1 Inhibitors", DRUG),
    "liver metastases": ("C_LIVER", "Secondary malignant neoplasm of liver", NEO),
}


def standard_terminology() -> FakeTerminology:
    return FakeTerminology(STANDARD_CONCEPTS)
