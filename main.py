import os
import uuid
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Import shared agent
from llm.agent import agent, DiagnosticTurn

app = FastAPI(
    title="Medical Conversational RAG API",
    description="Differential diagnosis agent with probability thresholds.",
    version="2.0.0"
)

load_dotenv()
GOOGLE_API_KEY = os.getenv("AI_STUDIO", "")

# In-memory storage for hackathon state (use Redis in prod)
sessions: Dict[str, Dict] = {}

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., example="У меня болит живот")

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    turn_data: DiagnosticTurn

@app.post("/chat_anamnesis", response_model=ChatResponse)
def chat_anamnesis(req: ChatRequest):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY (AI_STUDIO) key missing")
    
    sid = req.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = {"history": []}
    
    # Update local history
    sessions[sid]["history"].append(f"Пациент: {req.message}")
    
    try:
        turn = agent.chat(sessions[sid]["history"], req.message)
        
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
    return {"status": "running", "faiss_loaded": agent.retriever is not None}
