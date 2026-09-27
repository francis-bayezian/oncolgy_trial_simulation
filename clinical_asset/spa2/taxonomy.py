"""Map disease concepts to disease families and intervention names to drug classes.

Inputs are the evidence asset's own disease concepts and intervention names, with UMLS
definitions as the only descriptive text. GPT-5.6 Luna chooses a label from the controlled
lists; it supplies no values. Unmapped or low-confidence items are 'other' / 'unclassified',
which simply means that level offers no borrowing for them.
"""

import json
from functools import lru_cache
from pathlib import Path

from ..llm import StructuredModel

CONFIG = Path(__file__).with_name("taxonomy.json")
MIN_CONFIDENCE = 0.7


@lru_cache(maxsize=1)
def taxonomy() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _schema(labels: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item": {"type": "string"},
                        "label": {"type": "string", "enum": labels},
                        "confidence": {"type": "number"},
                    },
                    "required": ["item", "label", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["mappings"],
        "additionalProperties": False,
    }


def _map(model: StructuredModel, task: str, instructions: str, items: list[dict], labels: list[str], batch: int = 40) -> dict:
    result: dict[str, dict] = {}
    for start in range(0, len(items), batch):
        chunk = items[start : start + batch]
        names = {c["item"] for c in chunk}
        answer = model.extract(task, _schema(labels), {"instructions": instructions, "labels": labels, "items": chunk})
        for m in answer.get("mappings", []):
            if m["item"] in names and m["label"] in labels:
                result[m["item"]] = m
    return result


def map_diseases(model: StructuredModel, diseases: list[dict]) -> dict[str, dict]:
    return _map(
        model, "disease_family",
        "Assign each cancer concept (item = its name; definition from UMLS when available) to one disease family "
        "from labels by organ or lineage. Use mixed_solid_tumors or mixed_hematologic only for concepts that "
        "name several cancers; use other when none fits. Give confidence between 0 and 1.",
        diseases, taxonomy()["disease_families"],
    )


def map_drugs(model: StructuredModel, drugs: list[dict]) -> dict[str, dict]:
    labels = list(taxonomy()["drug_classes"])
    return _map(
        model, "drug_class",
        "Assign each trial intervention (item = its name as reported; definition from UMLS when available) to "
        "one class from labels by its mechanism. Placebos, observation and best supportive care alone are "
        "placebo_or_no_active_treatment; antiemetics, growth factors and similar are supportive_care. If the "
        "name is a multi-drug regimen or you cannot tell, use other. Give confidence between 0 and 1.",
        drugs, labels,
    )


def drug_class(name: str, mapping: dict[str, dict]) -> str:
    entry = mapping.get(name)
    return entry["label"] if entry and entry["confidence"] >= MIN_CONFIDENCE else "unclassified"


def modality(drug_class_label: str) -> str:
    return taxonomy()["drug_classes"].get(drug_class_label, "unclassified")


def regimen_signature(components: list[str], mapping: dict[str, dict]) -> tuple[str, str]:
    """(class signature, modality signature) of a regimen; supportive care and placebo drop out
    when an active component is present."""
    classes = sorted({drug_class(c, mapping) for c in components if c})
    active = [c for c in classes if modality(c) not in {"supportive_care", "placebo_or_no_treatment"}]
    classes = active or classes or ["unclassified"]
    modalities = sorted({modality(c) for c in classes})
    return "+".join(classes), "+".join(modalities)
