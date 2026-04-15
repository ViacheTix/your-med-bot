import json
import os
from langchain.schema import Document
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

FAISS_INDEX_DIR = "data/faiss_db"

def main():
    print("Initializing embedding model (free local multilingual model)...")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    print("Loading cleaned disease database...")
    db_path = "disease_anamnesis_database_cleaned.json"
    if not os.path.exists(db_path):
        print(f"Error: Database file {db_path} not found.")
        return
        
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    docs = []
    print(f"Processing {len(data)} articles...")
    for item in data:
        disease_name = item.get("Disease_Name", "Unknown")
        summary = item.get("Summary", "")
        
        sections_text = ""
        for key, value in item.items():
            if key not in ["Disease_Name", "Wikipedia_Title", "Wikidata_URL", "Summary"]:
                sections_text += f"\n{key}:\n{value}\n"
                
        content = f"Disease: {disease_name}\nSummary: {summary}\n{sections_text}"
        
        doc = Document(
            page_content=content,
            metadata={"disease": disease_name, "source": item.get("Wikipedia_Title", "")}
        )
        docs.append(doc)
        
    print(f"Creating FAISS vector store for {len(docs)} documents...")
    vectorstore = FAISS.from_documents(
        documents=docs,
        embedding=embeddings
    )
    
    try:
        if not os.path.exists(FAISS_INDEX_DIR):
            os.makedirs(FAISS_INDEX_DIR)
        vectorstore.save_local(FAISS_INDEX_DIR)
    except Exception as e:
        print(f"Error saving FAISS index: {e}")
        
    print(f"Vector store successfully saved to {FAISS_INDEX_DIR}")

if __name__ == "__main__":
    main()
