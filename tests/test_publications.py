"""Publication fallback uses only the supplied linked reference."""

import httpx

from clinical_asset.publications import PublicationClient


def test_abstract_fallback_when_full_text_is_unavailable() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search")
        assert "EXT_ID%3A111" in str(request.url)
        return httpx.Response(
            200,
            json={
                "resultList": {
                    "result": [
                        {
                            "pmid": "111",
                            "doi": "10.1000/a",
                            "title": "A <i>trial</i>",
                            "abstractText": "<p>ORR was 52% in the positive subgroup.</p>",
                            "hasSuppl": "N",
                        }
                    ]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    with PublicationClient(client) as publications:
        result = publications.retrieve(
            {
                "pmid": "111",
                "doi": "10.1000/a",
                "url": "https://pubmed.ncbi.nlm.nih.gov/111/",
                "citation": "Example",
                "registry_reference_type": "RESULT",
            }
        )
    assert result.retrieval_status == "retrieved"
    assert result.text_source == "abstract"
    assert result.paragraphs[0]["text"] == "ORR was 52% in the positive subgroup."
    assert result.title == "A trial"
