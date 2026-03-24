from langgraph.graph import StateGraph, END
from typing import TypedDict

class AgentState(TypedDict):
    query: str
    intent: str
    retrieved_context: str
    response: str
    confidence: float

def classify_intent(state: AgentState) -> AgentState:
    query = state["query"].lower()
    if any(word in query for word in ["status", "find", "get", "show"]):
        return {"intent": "tool_call"}
    return {"intent": "rag_search"}

def retrieve_context(state: AgentState) -> AgentState:
    return {
        "retrieved_context": f"Mock context for: {state['query']}",
        "confidence": 0.85
    }

def generate_response(state: AgentState) -> AgentState:
    return {
        "response": f"Based on context: {state['retrieved_context']}"
    }

def route_intent(state: AgentState) -> str:
    if state["intent"] == "tool_call":
        return "tool"
    return "rag"

workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_intent)
workflow.add_node("retrieve", retrieve_context)
workflow.add_node("generate", generate_response)

workflow.set_entry_point("classify")
workflow.add_conditional_edges("classify", route_intent, {
    "rag": "retrieve",
    "tool": "generate"
})
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

app = workflow.compile()

if __name__ == "__main__":
    result = app.invoke({
        "query": "Show me disputed payments from VENDOR-001",
        "intent": "",
        "retrieved_context": "",
        "response": "",
        "confidence": 0.0
    })
    print(result)