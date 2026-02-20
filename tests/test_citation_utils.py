from citation_utils import build_citation_url, extract_citations_from_metadata


def test_build_citation_url():
    doc = "PRG 1_010 LG 10 2022.pdf"
    url = build_citation_url(doc, 7)
    assert url == "http://127.0.0.1:8008/PRG%201_010%20LG%2010%202022/page0007.png"


def test_extract_citations_from_metadata():
    metadata = {
        "tool_results": [
            {
                "tool": "search",
                "result": {
                    "relevant_docs": [
                        {
                            "metadata": {
                                "document_name": "A B.pdf",
                                "page_label": "12",
                            }
                        },
                        {
                            "metadata": {
                                "document_name": "A B.pdf",
                                "page_label": "12",
                            }
                        },
                        {
                            "metadata": {
                                "source": "C_D.pdf",
                                "page_number": 3,
                            }
                        },
                    ]
                },
            }
        ]
    }

    citations = extract_citations_from_metadata(metadata)
    assert len(citations) == 2
    assert citations[0]["document_name"] == "A B.pdf"
    assert citations[0]["page_number"] == 12
    assert citations[1]["document_name"] == "C_D.pdf"
    assert citations[1]["page_number"] == 3
