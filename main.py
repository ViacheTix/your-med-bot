import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Application Initialization
app = FastAPI(
    title="Medical RAG Agent API",
    description="An LLM baseline for disease anamnesis via RAG pipeline.",
    version="1.0.0"
)

FAISS_INDEX_DIR = "./faiss_db"
OPEN_ROUTER_API_KEY = os.getenv("OPEN_ROUTER", "")

# Load models at startup
print("Loading Embedding Model...")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

print("Loading Vector Store...")
try:
    vectorstore = FAISS.load_local(FAISS_INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
except Exception as e:
    print(f"Warning: Could not load FAISS vectorstore (have you run ingest.py?): {e}")
    retriever = None

# Initialize LLM via OpenRouter interface
llm = ChatOpenAI(
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=OPEN_ROUTER_API_KEY,
    model_name="mistralai/mistral-small-24b-instruct-2501:free",
    temperature=0.0
)

# Define IO Pydantic Models
class PatientRequest(BaseModel):
    complaint: str = Field(..., example="У меня сильно болит живот вот уже два дня и меня тошнит")

class AgentResponse(BaseModel):
    symptoms: List[str] = Field(description="List of extracted explicit symptoms")
    urgency: str = Field(description="Urgency classification (e.g., Высокая, Средняя, Низкая)")
    suggested_doctor: str = Field(description="Suggested doctor specialist type")
    clarifying_questions: List[str] = Field(description="1-2 clarifying questions to narrow down the context based on potential diseases")
    express_appointment_offered: bool = Field(description="Whether an express appointment is offered")
    express_appointment_message: str = Field(description="Text formulation of the express appointment offer")

# Setup LangChain output parsing and prompt
parser = JsonOutputParser(pydantic_object=AgentResponse)

prompt = ChatPromptTemplate.from_messages([
    ("system", """Ты - медицинский ассистент с искусственным интеллектом, работающий на этапе претриажа.
Твоя задача: на основе первоначальных жалоб пациента и информации из медицинской базы данных (контекста) проанализировать ситуацию.

Обязательно выполни следующие шаги:
1. Извлеки все упомянутые симптомы.
2. Классифицируй срочность состояния (Высокая / Средняя / Низкая).
3. Порекомендуй медицинского специалиста (например: Терапевт, Гастроэнтеролог, Невролог).
4. Задай 1 или 2 уточняющих вопроса, которые помогут собрать дополнительные важные симптомы, характерные для предполагаемых болезней из контекста (чтобы лучше их отдифференцировать).
5. Предложи пациенту записаться на экспресс-прием.

Вот контекст потенциальных похожих заболеваний на основе вектора симптомов:
{context}

ОБЯЗАТЕЛЬНО ответь строго в формате JSON, соответствующем следующей схеме:
{format_instructions}
"""),
    ("human", "Жалобы пациента: {complaint}")
])

chain = prompt | llm | parser

@app.on_event("startup")
def startup_event():
    if not OPEN_ROUTER_API_KEY:
        print("WARNING: OPEN_ROUTER environment variable is not set! LLM requests will fail.")

@app.get("/health")
def health_check():
    return {"status": "ok", "vectorstore_loaded": retriever is not None}

@app.post("/analyze_anamnesis", response_model=AgentResponse)
def analyze_anamnesis(req: PatientRequest):
    if not OPEN_ROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPEN_ROUTER api key not configured")
        
    context_text = "Контекст не найден"
    if retriever:
        docs = retriever.invoke(req.complaint)
        context_text = "\n---\n".join([d.page_content for d in docs])
        
    try:
        response = chain.invoke({
            "context": context_text,
            "format_instructions": parser.get_format_instructions(),
            "complaint": req.complaint
        })
        return response
    except Exception as e:
        # Catch JSON parse errors or API failures
        raise HTTPException(status_code=500, detail=str(e))
