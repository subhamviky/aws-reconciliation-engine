from langgraph.graph import StateGraph, END
from langchain_aws import BedrockEmbeddings
from langchain_chroma import Chroma
from langchain.embeddings.base import Embeddings
from typing import TypedDict
import boto3
import logging
import json

class AgentState(TypedDict):
    query: str
    intent: str
    retrieved_context: str
    response: str
    confidence: float
    retrieval_id: str
    token_usage: int
 
class MockEmbeddings(Embeddings):
    def embed_documents(self,texts):
        return[[1.0] * 10 for _ in texts]
    def embed_query(self, text):
        return [1.0] * 10

def classify_intent(state: AgentState) -> AgentState:
    query = state["query"].lower()
    if any(word in query for word in ["status", "healthcheck", "uptime"]):
        return {"intent": "tool_call"}
    return {"intent": "rag_search"}

embeddings = MockEmbeddings()
vectorstore = Chroma(collection_name="audit_logs", embedding_function=embeddings)

vectorstore.add_texts(
    texts = ["Payment dispute log for VENDOR-001 on March 15"],
    ids=["docs1"]
)

vectorstore.add_texts(
    texts=[
        "Payment dispute log for VENDOR-001 on March 15",
        "DLQ entry for failed reconciliation on March 20",
        "Vendor-002 audit log showing successful payment"
    ],
    ids=["doc1", "doc2", "doc3"]
)

def retrieve_context(state: AgentState) -> AgentState:
    docs = vectorstore.similarity_search(state["query"], k=3)
    return {
        "retrieved_context": " ".join([d.page_content for d in docs]),
        "confidence": 0.85,
        "retrieval_id": "RAG123"
    }

bedrock = boto3.client("bedrock-runtime", region_name='ap-south-1')

def groundedness_check(state: AgentState) -> AgentState:
    if state["confidence"] < 0.7:
        return {"response": "Low Confidence - escalate to fallback agent"}
    return state

def generate_response(state: AgentState) -> AgentState:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{state['query']}\n\nContext:\n{state['retrieved_context']}"
                    }
                ]
            }
        ],
        "maxOutputTokens": 512
    }

    response = bedrock.invoke_model(
        modelId="google.gemma-3-4b-it",
        body=json.dumps(payload)
    )

    # Read once
    raw_body = response["body"].read()
    output = json.loads(raw_body)

    text_response = ""
    if "choices" in output and output["choices"]:
        text_response = output["choices"][0]["message"]["content"]

    return {
        "response": text_response,
        "token_usage": output.get("usage", {}).get("total_tokens", 0)
    }

def route_intent(state: AgentState) -> str:
    if state["intent"] == "tool_call":
        return "tool"
    return "rag"

workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_intent)
workflow.add_node("retrieve", retrieve_context)
workflow.add_node("groundedness", groundedness_check)
workflow.add_node("generate", generate_response)

workflow.set_entry_point("classify")
workflow.add_conditional_edges("classify", route_intent, {
    "rag": "retrieve",
    "tool": "generate"
})
workflow.add_edge("retrieve", "groundedness")
workflow.add_edge("groundedness", "generate")
workflow.add_edge("generate", END)

logger = logging.getLogger(__name__)

def log_state(state: AgentState):
    logger.info({
        "query": state["query"],
        "retrieval_id": state.get("retrieval_id"),
        "token_usage": state.get("token_usage")
    })

app = workflow.compile()

if __name__ == "__main__":
    result = app.invoke({
        "query": "Show me disputed payments from VENDOR-001",
        "intent": "",
        "retrieved_context": "",
        "response": "",
        "confidence": 0.0,
        "retrieval_id": "",
        "token_usage": 0
    })
    log_state(result)
    print(result)