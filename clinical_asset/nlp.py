"""scispaCy entity detection and medspaCy context, loaded once per process.

Entities are candidates only. They become clinical facts only after UMLS linking and the
validation rules of the extractors that use them.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

NER_MODELS = ("en_ner_bionlp13cg_md", "en_ner_bc5cdr_md")
logger.disable("PyRuSH")


def local_linker(directory: Path) -> Any:
    """scispaCy EntityLinker over the verified local UMLS 2022AB files."""
    from scispacy.candidate_generation import (
        DEFAULT_KNOWLEDGE_BASES,
        DEFAULT_PATHS,
        CandidateGenerator,
        LinkerPaths,
    )
    from scispacy.linking import EntityLinker
    from scispacy.linking_utils import UmlsKnowledgeBase

    root = directory.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if (root / item["name"]).stat().st_size != item["bytes"]:
            raise ValueError(f"Local UMLS linker file has the wrong size: {item['name']}")

    class LocalKnowledgeBase(UmlsKnowledgeBase):
        def __init__(self) -> None:
            super().__init__(
                file_path=str(root / "umls_2022_ab_cat0129.jsonl"),
                types_file_path=str(root / "umls_semantic_type_tree.tsv"),
            )

    name = "local_umls_2022ab"
    DEFAULT_PATHS[name] = LinkerPaths(
        ann_index=str(root / "nmslib_index.bin"),
        tfidf_vectorizer=str(root / "tfidf_vectorizer.joblib"),
        tfidf_vectors=str(root / "tfidf_vectors_sparse.npz"),
        concept_aliases_list=str(root / "concept_aliases.json"),
    )
    DEFAULT_KNOWLEDGE_BASES[name] = LocalKnowledgeBase
    return EntityLinker(candidate_generator=CandidateGenerator(name=name))


@dataclass(frozen=True)
class Mention:
    text: str
    start: int
    end: int
    labels: tuple[str, ...]
    negated: bool = False
    historical: bool = False
    hypothetical: bool = False
    cui: str | None = None


class ClinicalNLP:
    """Candidate clinical mentions with medspaCy ConText (negation, history, hypothetical).

    Default detection is dictionary-free: every n-gram that is an exact UMLS alias becomes a
    candidate, labelled with its UMLS semantic types. The heavier scispaCy NER models
    (bionlp13cg, bc5cdr) add candidates only when ``use_ner_models=True``; they cost about
    40 seconds to load, so they are reserved for batch runs.
    """

    def __init__(self, terminology: Any, use_ner_models: bool = False) -> None:
        import medspacy
        import spacy
        from spacy.lang.en.stop_words import STOP_WORDS

        self.terminology = terminology
        self.stop_words = frozenset(STOP_WORDS)
        self._models = [spacy.load(name) for name in NER_MODELS] if use_ner_models else []
        self._context = medspacy.load(medspacy_enable=["medspacy_pyrush", "medspacy_context"])

    def mentions(self, text: str) -> list[Mention]:
        from spacy.util import filter_spans

        from .terminology import concept_mentions

        found: dict[tuple[int, int], tuple[set[str], str | None]] = {}
        for start, end, concept in concept_mentions(text, self.terminology, stop_words=self.stop_words):
            found[(start, end)] = (set(concept.types), concept.cui)
        for model in self._models:
            for entity in model(text).ents:
                labels, cui = found.get((entity.start_char, entity.end_char), (set(), None))
                found[(entity.start_char, entity.end_char)] = (labels | {entity.label_}, cui)
        if not found:
            return []
        doc = self._context.make_doc(text)
        for name, component in self._context.pipeline:
            if name != "medspacy_context":
                doc = component(doc)
        spans = [doc.char_span(start, end, label="ENTITY", alignment_mode="expand") for start, end in found]
        doc.ents = tuple(filter_spans([span for span in spans if span is not None]))
        doc = self._context.get_pipe("medspacy_context")(doc)
        flags = [
            (span.start_char, span.end_char, bool(span._.is_negated), bool(span._.is_historical), bool(span._.is_hypothetical))
            for span in doc.ents
        ]

        def context_for(start: int, end: int) -> tuple[bool, bool, bool]:
            for s0, e0, negated, historical, hypothetical in flags:
                if s0 <= start and end <= e0:
                    return negated, historical, hypothetical
            return False, False, False

        return [
            Mention(text[start:end], start, end, tuple(sorted(labels)), *context_for(start, end), cui=cui)
            for (start, end), (labels, cui) in sorted(found.items())
        ]
