import logging 
import json 
import uuid
from langgraph.graph import StateGraph, END
from typing import TypedDict
from src.agents.rag_pipeline import query_rag, build_rag_pipeline
from src.services.dynamodb import get_payment_by_reference

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_node(node_name: str, trace_id: str, state: dict):
    logger.info(json.dumps({
        "node": node_name,
        "trace_id": trace_id,
        "intent":state.get("intent",""),
        "has_rag_context": bool(state.get("rag_context")),
        "has_tool_result": bool(state.get("tool_result"))
    }))

class PaymentAgentState(TypedDict):
    query: str
    intent: str 
    rag_context: str
    tool_result: str
    final_response:str
    trace_id: str

    def classify_intent(state: PaymentAgentState)->PaymentAgentState:
        trace_id = state.get("trace_id") or str(uuid.uuid4())[:8]
        log_node("classify_intent", trace_id, state)
        query = state["query"].lower()
        if any(word in query for word in ["status", "find payment", "get_payment", "ref-"]):
            return{"intent": "tool_call", "trace_id": trace_id}
        return{"intent": "rag_search", "trace_id": trace_id}
    
    def rag_retrieval(state: PaymentAgentState)-> PaymentAgentState:
        trace_id = state_get("trace_id", "unknown")
        try:
            log_node("rag_retrieval", trace_id, state)
            vectorstore = build_rag_pipeline()
            context = query_rag(vectorstore, state["query"])
            return{"rag_context": context}
        except Exception as e:
            logger.error(json.dumps({
                "node":"rag_retrieval",
                "trace_id": trace_id,
                "error": str(e)
            }))
            return {"rag_context": "RAG retrieval failed - no context available" }

    def tool_call(state: PaymentAgentState)->PaymentAgentState:
        trace_id = state.get("trace_id", "unknown")
        try:
            log_node("tool_call", trace_id, state)
            result = get_payment_by_reference("REF-001")
            return{"tool_result":str(result) if result else "No Payment Found"}
        except Exception as e:
            logger.error(json.dumps({
                "node" : "tool_call",
                "trace_id" : trace_id,
                "error" : str(e)
            }))
            return {"tool_result": "Tool call failed"}

    def synthesise_response(state: PaymentAgentState)-> PaymentAgentState:
        context = state.get("rag_context") or state.get("tool_result")
        response = f"Based on financial records:{context}"
        return{"final_result":response}

    def route_intent(state: PaymentAgentState)->str: 
        return state["intent"]
        workflow = StateGraph(PaymentAgentState)
        workflow.add_node("classify", classify_intent)
        workflow.add_node("rag_search", rag_retrieval)
        workflow.add_node("tool_call", tool_call)
        workflow.add_node("synthnsise", synthesise_response)
        workflow.set_entry_point("classify")
        workflow.add_conditional_edges(
            "classify", route_intent,
            { 
            "rag_search": "rag_search",
            "tool_call": "tool_call"
            })
        workflow.add_edge("rag_search", "synthesise")
        workflow.add_edge("tool_call", "synthesise")
        workflow.add_edge("synthesise", END)

        app = workflow.compile()

        if __name__ == "__main__":
            result = app.invoke(
                {
                    "query" : "Show me disputed payments from VENDOR-002",
                    "intent": "",
                    "rag_context":"",
                    "tool_call": ""
                } )

        print(result["final_response"])

