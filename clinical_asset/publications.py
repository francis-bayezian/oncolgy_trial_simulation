"""Retrieve only result publications linked by the registry record."""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Self

import httpx

EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_text(value: str) -> str:
    parser = _TextOnly()
    parser.feed(value)
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()


@dataclass
class Publication:
    pmid: str
    doi: str
    pmcid: str
    url: str
    citation: str
    registry_reference_type: str
    retrieval_status: str
    text_source: str | None = None
    title: str | None = None
    paragraphs: list[dict[str, str]] = field(default_factory=list)
    supplementary_available: bool = False
    error_type: str | None = None

    def audit_metadata(self) -> dict[str, Any]:
        return {
            "pmid": self.pmid,
            "doi": self.doi,
            "pmcid": self.pmcid,
            "url": self.url,
            "citation": self.citation,
            "registry_reference_type": self.registry_reference_type,
            "retrieval_status": self.retrieval_status,
            "text_source": self.text_source,
            "title": self.title,
            "supplementary_available": self.supplementary_available,
            "error_type": self.error_type,
        }


def _jats_paragraphs(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    collected: list[dict[str, str]] = []
    for section_name, tag in (("abstract", "abstract"), ("body", "body")):
        for container in root.findall(f".//{tag}"):
            for element in container.iter():
                if element.tag not in {"p", "table-wrap"}:
                    continue
                text = re.sub(r"\s+", " ", " ".join(element.itertext())).strip()
                if text:
                    collected.append(
                        {
                            "section": section_name,
                            "kind": "table" if element.tag == "table-wrap" else "paragraph",
                            "text": text,
                        }
                    )
    return collected


class PublicationClient:
    def __init__(self, client: httpx.Client | None = None, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir
        self.client = client or httpx.Client(
            timeout=30,
            headers={"User-Agent": "ClinicalEvidenceAsset/0.1 (research)"},
            follow_redirects=True,
        )
        self._owns_client = client is None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        if self._owns_client:
            self.client.close()

    def retrieve(self, reference: dict[str, str]) -> Publication:
        """Cached copy when present; otherwise fetch once and cache a retrieved text."""
        key = reference.get("pmid") or re.sub(r"[^\w.-]+", "_", reference.get("doi", ""))
        path = self.cache_dir / f"{key}.json" if self.cache_dir and key else None
        if path is not None and path.exists():
            return Publication(**json.loads(path.read_text(encoding="utf-8")))
        publication = self._retrieve(reference)
        if path is not None and publication.retrieval_status == "retrieved":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(publication), ensure_ascii=False), encoding="utf-8")
        return publication

    def _retrieve(self, reference: dict[str, str]) -> Publication:
        """Full text from Europe PMC when available; otherwise its abstract."""
        publication = Publication(
            pmid=reference.get("pmid", ""),
            doi=reference.get("doi", ""),
            pmcid="",
            url=reference.get("url", ""),
            citation=reference.get("citation", ""),
            registry_reference_type=reference.get("registry_reference_type", ""),
            retrieval_status="metadata_unavailable",
        )
        query = (
            f"EXT_ID:{publication.pmid} AND SRC:MED"
            if publication.pmid
            else f'DOI:"{publication.doi}"'
        )
        try:
            response = self.client.get(
                f"{EUROPE_PMC}/search",
                params={"query": query, "format": "json", "resultType": "core"},
            )
            response.raise_for_status()
            hits = response.json().get("resultList", {}).get("result", [])
            if not hits:
                return publication
            match = hits[0]
            if publication.pmid and match.get("pmid") != publication.pmid:
                publication.error_type = "metadata_identifier_mismatch"
                return publication
            publication.doi = str(match.get("doi") or publication.doi)
            publication.pmcid = str(match.get("pmcid") or "")
            publication.title = clean_text(str(match.get("title") or ""))
            publication.supplementary_available = match.get("hasSuppl") == "Y"
            abstract = clean_text(str(match.get("abstractText") or ""))
            if publication.pmcid:
                try:
                    full = self.client.get(
                        f"{EUROPE_PMC}/{publication.pmcid}/fullTextXML",
                    )
                    if full.status_code == 200:
                        paragraphs = _jats_paragraphs(full.text)
                        if paragraphs:
                            publication.paragraphs = paragraphs
                            publication.text_source = "full_text"
                            publication.retrieval_status = "retrieved"
                            return publication
                except (httpx.HTTPError, ET.ParseError):
                    pass
            if abstract:
                publication.paragraphs = [
                    {"section": "abstract", "kind": "paragraph", "text": abstract}
                ]
                publication.text_source = "abstract"
                publication.retrieval_status = "retrieved"
            else:
                publication.retrieval_status = "text_unavailable"
            return publication
        except (httpx.HTTPError, ValueError, TypeError) as error:
            publication.retrieval_status = "request_failed"
            publication.error_type = type(error).__name__
            return publication
