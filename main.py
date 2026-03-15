import os
import uuid
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# LangChain imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

app = FastAPI(
    title="Medical Conversational RAG API",
    description="Differential diagnosis agent with probability thresholds.",
    version="2.0.0"
)

FAISS_INDEX_DIR = "data/faiss_db"
load_dotenv()
GOOGLE_API_KEY = os.getenv("AI_STUDIO", "")
# Load models at startup
print("Loading Local Embedding Model...")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

print("Loading FAISS Vector Store...")
try:
    vectorstore = FAISS.load_local(FAISS_INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
except Exception as e:
    print(f"Warning: Could not load FAISS: {e}")
    retriever = None

# Gemini 2.5 Flash via Google AI Studio
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GOOGLE_API_KEY,
    temperature=0.1
)

# In-memory storage for hackathon state (use Redis in prod)
sessions: Dict[str, Dict] = {}

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., example="У меня болит живот")

class DiagnosticTurn(BaseModel):
    extracted_symptoms: List[str] = Field(description="Список всех извлеченных симптомов пациента.")
    urgency: str = Field("Низкая", description="Степень срочности состояния: Высокая / Средняя / Низкая")
    suggested_doctor: str = Field("Терапевт", description="Рекомендуемый профильный врач")
    express_appointment: bool = Field(False, description="Предлагать ли экспресс-приём? (true если Высокая/Средняя срочность)")
    question: Optional[str] = Field(None, description="Следующий уточняющий вопрос пациенту, чтобы собрать больше информации для врача")
    decision_reached: bool = Field(False, description="Завершен ли сбор информации? (true если собрано достаточно симптомов и картина ясна, обычно после 3-5 вопросов)")
    preliminary_diagnosis: Optional[str] = Field(None, description="Предварительная гипотеза о заболевании (скрыто от пациента, только для врача)")

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    turn_data: DiagnosticTurn

parser = JsonOutputParser(pydantic_object=DiagnosticTurn)

SYSTEM_PROMPT = """Ты - умный медицинский ассистент (LLM-агент). Твоя главная цель — собрать максимально полную и точную информацию о жалобах пациента для передачи врачу.
У тебя есть история диалога и справочный контекст из базы данных (RAG).

ТВОЙ АЛГОРИТМ РАБОТЫ:
1. ИЗВЛЕЧЕНИЕ СИМПТОМОВ: Внимательно проанализируй сообщения пациента и выдели все симптомы (extracted_symptoms).
2. КЛАССИФИКАЦИЯ ЖАЛОБ И СРОЧНОСТЬ: Оцени степень срочности (urgency: Высокая / Средняя / Низкая) на основе симптомов.
3. РЕКОМЕНДАЦИЯ ВРАЧА: Выбери наиболее подходящего профильного специалиста (suggested_doctor).
4. ЭКСПРЕСС-ПРИЁМ: Если состояние требует быстрого вмешательства (Высокая или Средняя срочность), установи express_appointment = true.
5. УТОЧНЯЮЩИЕ ВОПРОСЫ: Если картина неполная, задай ОДИН релевантный уточняющий вопрос (question), чтобы детализировать симптомы (например, характер боли, продолжительность, сопутствующие факторы). Используй справочный контекст для формирования релевантных вопросов.
6. ЗАВЕРШЕНИЕ СБОРА: Если собрано достаточно информации (обычно после 3-5 вопросов) и картина ясна, установи decision_reached = true. В этом случае вопрос (question) можно оставить пустым.

СПРАВОЧНЫЙ КОНТЕКСТ (RAG) ПОХОЖИХ ЗАБОЛЕВАНИЙ И ИХ СИМПТОМОВ:
{context}

ОТВЕТЬ СТРОГО В JSON ФОРМАТЕ:
{format_instructions}
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "История диалога:\n{history}\n\nНовое сообщение: {message}")
])

chain = prompt | llm | parser

@app.post("/chat_anamnesis", response_model=ChatResponse)
def chat_anamnesis(req: ChatRequest):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY (AI_STUDIO) key missing")
    
    sid = req.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = {"history": []}
    
    # Update local history
    sessions[sid]["history"].append(f"Пациент: {req.message}")
    history_str = "\n".join(sessions[sid]["history"])
    
    # RAG: Retrieve context based on the *entire* history for better match
    context_text = "Нет данных"
    if retriever:
        docs = retriever.invoke(history_str)
        context_text = "\n\n".join([d.page_content for d in docs])
        
    try:
        res_data = chain.invoke({
            "context": context_text,
            "format_instructions": parser.get_format_instructions(),
            "history": history_str,
            "message": req.message
        })
        
        turn = DiagnosticTurn(**res_data)
        
        if turn.decision_reached:
            sessions[sid]["history"].append("ИИ: Сбор информации завершен.")
            reply = f"Спасибо за ответы! Я собрал всю необходимую информацию для врача. Рекомендуемый специалист: {turn.suggested_doctor}."
            if turn.express_appointment:
                reply += " Учитывая ваши симптомы, мы рекомендуем оформить экспресс-приём."
        else:
            sessions[sid]["history"].append(f"ИИ: {turn.question}")
            reply = turn.question or "Пожалуйста, расскажите подробнее."

        return ChatResponse(session_id=sid, reply=reply, turn_data=turn)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Error: {str(e)}")

@app.get("/health")
def health():
    return {"status": "running", "faiss_loaded": retriever is not None}

