"""Concept normalisation through UMLS 2022AB.

No medical vocabulary is written into this pipeline. Names are resolved to UMLS concepts,
and groups of concepts are selected only by UMLS semantic-type codes.

Lookup order, fastest first:
1. on-disk cache of earlier lookups;
2. exact alias match in the SQLite UMLS index (milliseconds, no model loading);
3. the scispaCy fuzzy linker, only when ``fuzzy=True`` (batch runs load it once, because
   loading takes minutes). Without it, an unmatched term keeps its source wording.
"""

import json
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .umls_index import DEFAULT_INDEX, UmlsIndex

# UMLS semantic-type groups (structural codes, not clinical terms).
DRUG_TYPES = frozenset({"T109", "T116", "T121", "T123", "T125", "T126", "T129", "T131", "T195", "T197", "T200"})
NEOPLASM_TYPES = frozenset({"T191"})
GENE_TYPES = frozenset({"T028", "T116", "T126"})
VARIANT_TYPES = frozenset({"T049", "T045"})
FINDING_TYPES = frozenset(
    {"T019", "T020", "T033", "T034", "T037", "T046", "T047", "T048", "T049", "T184", "T190", "T191"}
)
PROCEDURE_TYPES = frozenset({"T058", "T059", "T060", "T061"})
MIN_SCORE = 0.85


@dataclass(frozen=True)
class Concept:
    cui: str
    name: str
    types: tuple[str, ...]
    score: float
    exact: bool

    @property
    def key(self) -> str:
        return re.sub(r"[^a-z0-9]+", "_", self.name.casefold()).strip("_")


class Terminology(Protocol):
    def link(
        self, text: str, allowed_types: frozenset[str] | None = None, min_score: float = MIN_SCORE
    ) -> Concept | None: ...

    def definition(self, cui: str) -> str | None: ...

    def aliases(self, cui: str) -> list[str]: ...


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def inflection_variants(text: str) -> list[str]:
    """The text first, then generic English inflections of its last word (increase ->
    increased, lesion -> lesions). Only used after the exact form finds nothing."""
    text = _clean(text)
    match = re.search(r"([A-Za-z]+)$", text)
    if not match:
        return [text]
    stem, word = text[: match.start()], match.group(1)
    forms = [word + "d", word + "ed", word + "s", word[:-1] if word.endswith(("s", "d")) else None]
    return [text, *(stem + f for f in forms if f and len(f) > 3)]


class UmlsTerminology:
    def __init__(
        self,
        index_path: Path = DEFAULT_INDEX,
        cache_path: Path = Path("data/cache/umls_links.json"),
        linker_directory: Path = Path("terminology-private/scispacy-umls-2022ab"),
        fuzzy: bool = False,
    ) -> None:
        self.index = UmlsIndex(index_path)
        self.cache_path = cache_path
        self.linker_directory = linker_directory
        self.fuzzy = fuzzy
        self._linker = None
        self._lock = threading.RLock()
        self._dirty = False
        data = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self._links: dict[str, list[dict]] = data.get("links", {})
        self.fuzzy_misses: set[str] = set()

    def _entity(self, cui: str) -> dict:
        return self.index.entity(cui) or {"name": cui, "types": [], "definition": None, "aliases": []}

    def _fuzzy(self, text: str) -> list[dict]:
        if self._linker is None:
            from .nlp import local_linker

            print("Loading the UMLS fuzzy linker (minutes, once per process)...", file=sys.stderr)
            self._linker = local_linker(self.linker_directory)
        batch = self._linker.candidate_generator([text], 8)[0]
        return [{"cui": c.concept_id, "score": round(max(c.similarities), 4), "exact": False} for c in batch]

    def _candidates(self, text: str, record_miss: bool = True) -> list[dict]:
        key = _clean(text).casefold()
        if key in self._links:
            return self._links[key]
        hits: list[tuple[str, bool]] = []
        for variant in inflection_variants(text):
            hits = self.index.exact(variant)
            if hits:
                break
        found = [{"cui": cui, "score": 1.0, "exact": True, "canonical": canonical} for cui, canonical in hits]
        if not found and self.fuzzy and record_miss:
            found = self._fuzzy(_clean(text))
        elif not found:
            if record_miss:
                self.fuzzy_misses.add(_clean(text))
            return []  # not cached, so a later fuzzy run can still resolve it
        self._links[key] = found
        self._dirty = True
        return found

    def link(
        self, text: str, allowed_types: frozenset[str] | None = None, min_score: float = MIN_SCORE
    ) -> Concept | None:
        return self._link(text, allowed_types, min_score, record_miss=True)

    def probe(self, text: str, allowed_types: frozenset[str] | None = None) -> Concept | None:
        """Exact-only lookup for phrase detection: never fuzzy, never reported as a miss."""
        return self._link(text, allowed_types, MIN_SCORE, record_miss=False)

    def _link(
        self, text: str, allowed_types: frozenset[str] | None, min_score: float, record_miss: bool
    ) -> Concept | None:
        if not text or not _clean(text):
            return None
        with self._lock:
            options = []
            for candidate in self._candidates(text, record_miss):
                entity = self._entity(candidate["cui"])
                types = tuple(entity["types"])
                if allowed_types and not set(types) & allowed_types:
                    continue
                if candidate["score"] < min_score and not candidate["exact"]:
                    continue
                # Prefer: concept name equal to the text, then canonical-name match, then exact
                # alias, then score, then the shortest (least qualified) name, then lowest CUI.
                name_equal = _clean(entity["name"]).casefold() == _clean(text).casefold()
                rank = (
                    not name_equal,
                    not candidate.get("canonical"),
                    not candidate["exact"],
                    -candidate["score"],
                    len(entity["name"]),
                    candidate["cui"],
                )
                options.append((rank, candidate, entity))
            if not options:
                return None
            _, best, entity = min(options, key=lambda item: item[0])
            return Concept(best["cui"], entity["name"], tuple(entity["types"]), best["score"], best["exact"])

    def definition(self, cui: str) -> str | None:
        return self._entity(cui).get("definition")

    def aliases(self, cui: str) -> list[str]:
        return list(self._entity(cui).get("aliases", []))

    def save(self) -> None:
        if not self._dirty:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".part")
        temporary.write_text(json.dumps({"links": self._links}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.cache_path)
        self._dirty = False


def concept_mentions(
    text: str,
    terminology: Terminology,
    allowed_types: frozenset[str] | None = None,
    stop_words: frozenset[str] = frozenset(),
    max_words: int = 6,
) -> list[tuple[int, int, Concept]]:
    """Every word n-gram of the text that is an exact UMLS alias (dictionary-free NER).

    Returns overlapping spans; callers decide whether to keep the innermost or outermost.
    """
    words = [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9.'+-]*[A-Za-z0-9+]|[A-Za-z0-9]", text)]
    found = []
    for i in range(len(words)):
        for j in range(min(len(words), i + max_words), i, -1):
            start, end = words[i][0], words[j - 1][1]
            phrase = text[start:end]
            if j - i == 1 and (len(phrase) < 3 or phrase.casefold() in stop_words):
                continue
            lookup = getattr(terminology, "probe", None) or terminology.link
            concept = lookup(phrase, allowed_types)
            if concept is not None:
                found.append((start, end, concept))
    return found
