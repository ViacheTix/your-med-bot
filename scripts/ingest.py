import json
import os
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Set up persistence directory
FAISS_INDEX_DIR = "data/faiss_db"

def main():
    if os.path.exists(FAISS_INDEX_DIR) and os.listdir(FAISS_INDEX_DIR):
        print(f"FAISS index already exists at {FAISS_INDEX_DIR}. Skipping ingestion.")
        return

    print("Initializing local embedding model (sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)...")
    embeddings = HuggingFaceEmbeddings(model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    print("Loading cleaned disease database...")
    db_path = "data/disease_anamnesis_database_cleaned.json"
    if not os.path.exists(db_path):
        print(f"Error: Database file {db_path} not found. Run clean_db.py first.")
        return
        
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    raw_docs = []
    print(f"Processing {len(data)} articles...")
    for item in data:
        disease_name = item.get("Disease_Name", "Unknown")
        summary = item.get("Summary", "")
        
        # Aggregate all text from symptomatology sections
        meta_sections = ["Disease_Name", "Wikipedia_Title", "Wikidata_URL", "Summary"]
        sections_text = ""
        for key, value in item.items():
            if key not in meta_sections:
                sections_text += f"\n{key}:\n{value}\n"
                
        content = f"Заболевание: {disease_name}\nКраткое описание: {summary}\n{sections_text}"
        
        doc = Document(
            page_content=content,
            metadata={"disease": disease_name, "source": item.get("Wikipedia_Title", "")}
        )
        raw_docs.append(doc)
        
    print("Splitting documents for better retrieval granularity...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = text_splitter.split_documents(raw_docs)
    print(f"Created {len(docs)} document chunks.")
        
    print(f"Creating FAISS vector store for {len(docs)} documents locally...")
    # This is fast and reliable locally.
    vectorstore = FAISS.from_documents(docs, embeddings)
    
    if not os.path.exists(FAISS_INDEX_DIR):
        os.makedirs(FAISS_INDEX_DIR)
    vectorstore.save_local(FAISS_INDEX_DIR)
    print(f"Vector store successfully saved to {FAISS_INDEX_DIR}!")

if __name__ == "__main__":
    main()
