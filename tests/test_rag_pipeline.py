from src.agents.rag_pipeline import build_rag_pipeline, query_rag

def test_rag_pipeline_dispute_query():
    vs = build_rag_pipeline()
    result = query_rag(vs, "Show disputed payments for VENDOR-002")
    assert "disputed" in result or "Dispute" in result
    assert "REF-002 in result"