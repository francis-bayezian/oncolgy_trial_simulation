"""ClinicalTrials.gov API v2 retrieval and exact source gating."""

import re
import time
from collections.abc import Iterator
from typing import Any, Self

import requests

API_ROOT = "https://clinicaltrials.gov/api/v2"
NCT_PATTERN = re.compile(r"^NCT[0-9]{8}$")
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s;]+", re.IGNORECASE)


class RegistryError(RuntimeError):
    """Retrieval or response integrity failure."""


def validate_nct_id(nct_id: str) -> str:
    value = nct_id.strip().upper()
    if not NCT_PATTERN.fullmatch(value):
        raise ValueError("Expected an NCT identifier such as NCT04303780.")
    return value


class ClinicalTrialsClient:
    def __init__(self, client: requests.Session | None = None) -> None:
        self.client = client or requests.Session()
        if client is None:
            self.client.headers.update({"User-Agent": "ClinicalEvidenceAsset/0.1 (research)"})
        self._owns_client = client is None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        if self._owns_client:
            self.client.close()

    def _get_json(self, path: str, params: dict[str, str | int] | None = None) -> dict[str, Any]:
        url = API_ROOT + path
        for attempt in range(3):
            try:
                response = self.client.get(url, params=params, timeout=30)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RegistryError("ClinicalTrials.gov returned a non-object response.")
                return payload
            except (requests.RequestException, ValueError) as error:
                if attempt == 2:
                    raise RegistryError(
                        f"ClinicalTrials.gov request failed: {type(error).__name__}"
                    ) from error
                time.sleep(2**attempt)
        raise RegistryError("ClinicalTrials.gov request exhausted retries.")

    def get_study(self, nct_id: str) -> dict[str, Any]:
        nct_id = validate_nct_id(nct_id)
        study = self._get_json(f"/studies/{nct_id}")
        returned = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
        if returned != nct_id:
            raise RegistryError("The returned study identifier did not match the request.")
        return study

    def discover(self, condition: str, *, page_size: int = 100) -> Iterator[dict[str, Any]]:
        if not condition.strip():
            raise ValueError("An explicit oncology condition query is required.")
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000.")
        token: str | None = None
        while True:
            params: dict[str, str | int] = {
                "format": "json",
                "query.cond": condition,
                "query.term": "AREA[StudyType]INTERVENTIONAL AND AREA[HasResults]TRUE",
                "filter.overallStatus": "COMPLETED",
                "pageSize": page_size,
            }
            if token:
                params["pageToken"] = token
            page = self._get_json("/studies", params)
            studies = page.get("studies", [])
            if not isinstance(studies, list):
                raise RegistryError("ClinicalTrials.gov returned an invalid studies list.")
            yield from studies
            next_token = page.get("nextPageToken")
            if not next_token:
                break
            if not isinstance(next_token, str) or next_token == token:
                raise RegistryError("ClinicalTrials.gov returned an invalid page token.")
            token = next_token


def eligibility(study: dict[str, Any]) -> tuple[bool, str | None]:
    protocol = study.get("protocolSection", {})
    if protocol.get("designModule", {}).get("studyType") != "INTERVENTIONAL":
        return False, "study_type_not_interventional"
    if protocol.get("statusModule", {}).get("overallStatus") != "COMPLETED":
        return False, "overall_status_not_completed"
    if study.get("hasResults") is not True or not study.get("resultsSection"):
        return False, "results_not_posted"
    # Oncology scope is confirmed later from a UMLS neoplasm concept (enrich.py),
    # not from a hard-coded word list.
    return True, None


def linked_result_references(study: dict[str, Any]) -> list[dict[str, str]]:
    """Use only result/derived registry references, never an NCT web search."""
    raw = study.get("protocolSection", {}).get("referencesModule", {}).get("references", [])
    results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for reference in raw:
        if reference.get("type") not in {"RESULT", "DERIVED"}:
            continue
        pmid = str(reference.get("pmid") or "").strip()
        citation = str(reference.get("citation") or "")
        match = DOI_PATTERN.search(citation)
        doi = match.group(0).rstrip(".,)") if match else ""
        if not pmid and not doi:
            continue
        key = (pmid, doi.lower())
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "pmid": pmid,
                "doi": doi,
                "citation": citation,
                "registry_reference_type": reference["type"],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                if pmid
                else f"https://doi.org/{doi}",
            }
        )
    return results
