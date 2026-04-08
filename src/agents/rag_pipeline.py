from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import Chroma

# Sample financial audit logs
sample_logs = [
    "Payment REF-001 for VENDOR-001 amount $15000 settled on 2026-03-01",
    "Payment REF-002 for VENDOR-002 amount $8500 disputed on 2026-03-05",
    "Payment REF-003 for VENDOR-001 amount $22000 processing on 2026-03-10",
    "Dispute raised by VENDOR-002 for invoice mismatch on REF-002",
    "Settlement reconciliation completed for VENDOR-001 batch March 2026"
]

def build_rag_pipeline():
    #Step 1 - Create documents
    docs = [Document(page_content = log) for log in sample_logs]

    #Step 2 - Chunk
    splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20)
    chunks = splitter.split_documents(docs)

    #Step 3 - Embed using  Bedrock Titan
    embeddings = BedrockEmbeddings(
        model_id = "amazon.titan-embed-text-v1"
    )

    #Step 4 - Store in ChromaDB locally
    vectorstore = Chroma.from_documents(
        documents = chunks,
        embedding=embeddings,
        persist_directory = "./chroma_db"
    )
    return vectorstore

def query_rag(vectorstore, question:str) -> str:
    #Step 5 - Similarity Search
    relevant_docs = vectorstore.similarity_search(question, k=3)
    context = "\n".join([doc.page_content for doc in relevant_docs])
    return context

if __name__ == "__main__":
    vs = build_rag_pipeline()
    result = query_rag(vs, "Show disputed payments for VENDOR-002")
    print(result)