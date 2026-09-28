"""Document ingestion: PDF -> pages -> lines and tables -> numbered section hierarchy.

Nothing here knows about medicine or about a particular sponsor's template:

* text is extracted per line with its vertical position; a vertical tolerance keeps superscripts
  and subscripts inline (so "mg/m" + raised "2" stays "mg/m2");
* lines that repeat on most pages (running headers and footers) are removed and kept aside;
* tables are extracted as cell grids and attached to the section they appear in;
* numbered headings ("3.2.8.1 Title") are accepted only when they form a consistent outline
  (child, next sibling, or next sibling of an ancestor), which rejects numbers that merely start
  a line of a table or a list; lettered/roman appendix headings are recognised by shape;
* the result is cached by the SHA-256 of the file.
"""

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

CACHE = Path("data/protocol_work/documents")
EXTRACTOR_VERSION = "ingest-1.1.0"
NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+(\S.{1,200})$")
APPENDIX = re.compile(r"^(APPENDIX\s+[A-Z0-9IVXLC]+)\s*[:.\-]?\s*(.*)$", re.IGNORECASE)
TOC_LINE = re.compile(r"\.{3,}\s*\d+\s*$|\s\d{1,3}$")


@dataclass
class Line:
    page: int
    top: float
    text: str


@dataclass
class Table:
    page: int
    top: float
    rows: list[list[str]]


@dataclass
class Section:
    number: str
    title: str
    level: int
    page_start: int
    page_end: int = 0
    top: float = 0.0
    lines: list[Line] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.number

    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class Document:
    doc_id: str
    path: str
    pages: int
    metadata: dict
    removed_running_lines: list[str]
    front_matter: list[Line]
    sections: list[Section]
    extractor_version: str = EXTRACTOR_VERSION

    def section(self, number: str) -> Section | None:
        return next((s for s in self.sections if s.number == number), None)

    def subtree(self, number: str) -> list[Section]:
        return [s for s in self.sections if s.number == number or s.number.startswith(number.rstrip(".0") + ".")
                or (number.endswith(".0") and s.number.split(".")[0] == number.split(".")[0])]

    def full_text(self) -> str:
        return "\n".join(line.text for line in self.front_matter) + "\n" + "\n".join(
            f"{s.number} {s.title}\n{s.text()}" for s in self.sections)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _outline_key(number: str) -> tuple[int, ...]:
    parts = [int(p) for p in number.split(".")]
    if len(parts) == 2 and parts[1] == 0:  # "3.0" is the top-level heading 3
        parts = parts[:1]
    return tuple(parts)


def _valid_successor(previous: tuple[int, ...] | None, candidate: tuple[int, ...]) -> bool:
    """candidate may be the first child, the next sibling, or the next sibling of an ancestor."""
    if previous is None:
        return candidate == (1,)
    if candidate == previous + (1,):
        return True
    for depth in range(len(previous), 0, -1):
        if candidate == previous[: depth - 1] + (previous[depth - 1] + 1,):
            return True
    return False


def _heading_like(title: str) -> bool:
    """Heading titles are words: start with a letter, contain a word of at least three letters,
    and are mostly letters (rejects table rows such as '29 ____mg# a ,f')."""
    title = title.strip()
    if not title or not title[0].isalpha() or "__" in title:
        return False
    if not re.search(r"[A-Za-z]{3,}", title):
        return False
    visible = [c for c in title if not c.isspace()]
    return sum(c.isalpha() for c in visible) >= 0.6 * len(visible)


def _heading_weight(title: str) -> float:
    """How much a candidate looks like a section heading: capitals, few words, no sentence punctuation at the end."""
    t = " ".join(title.split())
    words = t.split()
    w = 1.0 + (1.0 if t.upper() == t else 0.0) + (0.5 if len(words) <= 8 else 0.0)
    if t.endswith((".", ",", ";", ":", "(")) or (words and words[-1][:1].islower() and len(words) > 8):
        w -= 0.75
    return max(w, 0.25)


def _outline_chain(candidates: list[tuple[int, tuple[int, ...], str | None, float]]) -> set[int]:
    """The numbered headings of the document: among candidate lines (position, outline key, top-level style, weight),
    the chain of valid successors starting at 1 with the largest total weight. Choosing the chain globally avoids
    locking onto a false '1' (a table row or list item) and then following a list's numbering."""
    best_chain: tuple[float, list[int]] = (0.0, [])
    for style in ("N", "N.0"):
        usable = [c for c in candidates if c[2] in (None, style)]
        score: list[float] = []
        back: list[int | None] = []
        for i, (_, key, _, w) in enumerate(usable):
            s_best, j_best = (w, None) if key == (1,) else (float("-inf"), None)
            for j in range(i):
                if score[j] > float("-inf") and _valid_successor(usable[j][1], key) and score[j] + w > s_best:
                    s_best, j_best = score[j] + w, j
            score.append(s_best)
            back.append(j_best)
        if not score or max(score) == float("-inf"):
            continue
        end = max(range(len(score)), key=lambda k: score[k])
        if score[end] > best_chain[0]:
            chain, k = [], end
            while k is not None:
                chain.append(usable[k][0])
                k = back[k]
            best_chain = (score[end], chain)
    return set(best_chain[1])


def _top_style(number: str) -> str:
    return "N.0" if number.endswith(".0") else "N"


def _is_contents_page(lines: list[Line], page_count: int) -> bool:
    """A table-of-contents page: most of its lines end with a page number within the document."""
    if len(lines) < 5:
        return False
    ending = 0
    for line in lines:
        m = re.search(r"(\d{1,3})\s*$", line.text)
        if m and 1 <= int(m.group(1)) <= page_count and not re.fullmatch(r"[\d.\s]+", line.text):
            ending += 1
    return ending >= 0.6 * len(lines)


def _running_lines(pages: list[list[Line]]) -> set[str]:
    """Lines repeated (digits masked) on at least half of the pages are headers or footers."""
    counts: Counter = Counter()
    for lines in pages:
        seen = {re.sub(r"\d+", "#", line.text.strip()) for line in lines[:3] + lines[-3:]}
        counts.update(seen)
    threshold = max(3, len(pages) // 2)
    return {pattern for pattern, c in counts.items() if c >= threshold and pattern}


def extract(path: Path, use_cache: bool = True) -> Document:
    doc_id = sha256(path)
    cache_file = CACHE / f"{doc_id}.{EXTRACTOR_VERSION}.json"
    if use_cache and cache_file.exists():
        return load(cache_file)
    import pdfplumber

    raw_pages: list[list[Line]] = []
    tables: list[Table] = []
    with pdfplumber.open(path) as pdf:
        metadata = {k: str(v) for k, v in (pdf.metadata or {}).items()}
        for number, page in enumerate(pdf.pages, 1):
            lines = [Line(number, float(item["top"]), item["text"].strip())
                     for item in page.extract_text_lines(x_tolerance=1.5, y_tolerance=5) if item["text"].strip()]
            raw_pages.append(lines)
            for found in page.find_tables():
                rows = [[(cell or "").strip() for cell in row] for row in found.extract(x_tolerance=1.5, y_tolerance=5)]
                if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                    tables.append(Table(number, float(found.bbox[1]), rows))
    running = _running_lines(raw_pages)
    kept = [[line for line in lines if re.sub(r"\d+", "#", line.text.strip()) not in running] for lines in raw_pages]
    removed = sorted(running)

    contents = [_is_contents_page(lines, len(kept)) for lines in kept]
    candidates, position = [], 0
    for lines, contents_page in zip(kept, contents, strict=True):
        for line in lines:
            m = NUMBERED.match(line.text)
            if not contents_page and m and not TOC_LINE.search(line.text) and _heading_like(m.group(2)):
                key = _outline_key(m.group(1))
                candidates.append((position, key, _top_style(m.group(1)) if len(key) == 1 else None, _heading_weight(m.group(2))))
            position += 1
    chosen = _outline_chain(candidates)

    sections: list[Section] = []
    front: list[Line] = []
    in_appendix = False
    position = -1
    for lines, contents_page in zip(kept, contents, strict=True):
        for line in lines:
            position += 1
            text = line.text
            heading = None
            if contents_page:
                (sections[-1].lines if sections else front).append(line)
                continue
            m = NUMBERED.match(text)
            if m and not in_appendix and position in chosen:
                heading = (m.group(1), m.group(2).strip(), len(_outline_key(m.group(1))))
            a = APPENDIX.match(text)
            if heading is None and a and not TOC_LINE.search(text) and text.upper() == text:
                heading = (a.group(1).upper(), a.group(2).strip(), 1)
                in_appendix = True
            if heading:
                if sections:
                    sections[-1].page_end = line.page
                sections.append(Section(heading[0], heading[1], heading[2], line.page, line.page, line.top))
            elif sections:
                sections[-1].lines.append(line)
            else:
                front.append(line)
    if sections:
        sections[-1].page_end = len(kept)
    # Attach each table to the section whose heading precedes it (page, then vertical position).
    for table in tables:
        owner = None
        for s in sections:
            if (s.page_start, s.top) <= (table.page, table.top):
                owner = s
        if owner is not None:
            owner.tables.append(table)
    for s in sections:
        s.page_end = max(s.page_end, s.page_start)
    doc = Document(doc_id, str(path), len(kept), metadata, removed, front, sections)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(asdict(doc), ensure_ascii=False), encoding="utf-8")
    return doc


def load(path: Path) -> Document:
    raw = json.loads(path.read_text(encoding="utf-8"))
    sections = []
    for s in raw["sections"]:
        sections.append(Section(s["number"], s["title"], s["level"], s["page_start"], s["page_end"], s.get("top", 0.0),
                                [Line(**x) for x in s["lines"]], [Table(**t) for t in s["tables"]]))
    return Document(raw["doc_id"], raw["path"], raw["pages"], raw["metadata"], raw["removed_running_lines"],
                    [Line(**x) for x in raw["front_matter"]], sections, raw.get("extractor_version", EXTRACTOR_VERSION))


def normalise(text: str, drop_hyphens: bool = False) -> str:
    """Canonical form for quote matching: unify dashes, quotes, micro signs and whitespace.
    drop_hyphens=True also removes hyphens, which tolerates words split across lines."""
    text = text.replace("­", "").replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("µ", "μ")
    text = re.sub(r"-\s+", "-", text)
    if drop_hyphens:
        text = text.replace("-", "")
    return re.sub(r"\s+", " ", text).strip().casefold()
