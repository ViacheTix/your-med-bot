import os
import uuid
from typing import List, Optional, Dict
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

load_dotenv()

FAISS_INDEX_DIR = os.getenv("FAISS_INDEX_DIR", "data/faiss_db")
GOOGLE_API_KEY = os.getenv("AI_STUDIO", "")
SYMPTOMS_FILE = os.getenv("SYMPTOMS_FILE", "doctor/symptoms.txt")

class DiagnosticTurn(BaseModel):
    extracted_symptoms: List[str] = Field(description="Список всех извлеченных симптомов пациента.")
    urgency: str = Field("Низкая", description="Степень срочности состояния: Высокая / Средняя / Низкая")
    suggested_doctor: str = Field("Терапевт", description="Рекомендуемый профильный врач")
    express_appointment: bool = Field(False, description="Предлагать ли экспресс-приём? (true если Высокая/Средняя срочность)")
    question: Optional[str] = Field(None, description="Следующий уточняющий вопрос пациенту, чтобы собрать больше информации для врача")
    decision_reached: bool = Field(False, description="Завершен ли сбор информации? (true если собрано достаточно симптомов и картина ясна, обычно после 3-5 вопросов)")
    preliminary_diagnosis: Optional[str] = Field(None, description="Предварительная гипотеза о заболевании (скрыто от пациента, только для врача)")

class MedicalAgent:
    def __init__(self):
        print("Loading Local Embedding Model...")
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        
        print("Loading FAISS Vector Store...")
        try:
            self.vectorstore = FAISS.load_local(FAISS_INDEX_DIR, self.embeddings, allow_dangerous_deserialization=True)
            self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})
        except Exception as e:
            print(f"Warning: Could not load FAISS: {e}")
            self.retriever = None

        self.llm = ChatGoogleGenerativeAI(
            model="gemma-3-27b-it",
            google_api_key=GOOGLE_API_KEY,
            temperature=0.1
        )
        self.parser = JsonOutputParser(pydantic_object=DiagnosticTurn)
        
        self.symptoms_file = SYMPTOMS_FILE
        if not os.path.exists(self.symptoms_file):
             base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
             self.symptoms_file = os.path.join(base_dir, SYMPTOMS_FILE)

        try:
            with open(self.symptoms_file, "r") as f:
                self.allowed_symptoms = f.read()
        except Exception as e:
            print(f"Warning: Could not load symptoms file {self.symptoms_file}: {e}")
            self.allowed_symptoms = ""

        self.system_prompt = f"""Ты - умный медицинский ассистент (LLM-агент). Твоя главная цель — собрать максимально полную и точную информацию о жалобах пациента для передачи врачу.
У тебя есть история диалога и справочный контекст из базы данных (RAG).

ТВОЙ АЛГОРИТМ РАБОТЫ:
1. ИЗВЛЕЧЕНИЕ СИМПТОМОВ: Внимательно проанализируй сообщения пациента и выдели все симптомы (extracted_symptoms). 
   ВАЖНО: Выбирай симптомы ТОЛЬКО из этого списка (на английском): {self.allowed_symptoms}
2. КЛАССИФИКАЦИЯ ЖАЛОБ И СРОЧНОСТЬ: Оцени степень срочности (urgency: Высокая / Средняя / Низкая) на основе симптомов.
3. РЕКОМЕНДАЦИЯ ВРАЧА: Выбери наиболее подходящего профильного специалиста (suggested_doctor).
4. ЭКСПРЕСС-ПРИЁМ: Если состояние требует быстрого вмешательства (Высокая или Средняя срочность), установи express_appointment = true.
5. УТОЧНЯЮЩИЕ ВОПРОСЫ: Если картина неполная, задай ОДИН релевантный уточняющий вопрос (question), чтобы детализировать симптомы (например, характер боли, продолжительность, сопутствующие факторы). Используй справочный контекст для формирования релевантных вопросов.
6. ЗАВЕРШЕНИЕ СБОРА: Если собрано достаточно информации (обычно после 3-5 вопросов) и картина ясна, установи decision_reached = true. В этом случае вопрос (question) можно оставить пустым.

СПРАВОЧНЫЙ КОНТЕКСТ (RAG) ПОХОЖИХ ЗАБОЛЕВАНИЙ И ИХ СИМПТОМОВ:
{{context}}

ОТВЕТЬ СТРОГО В JSON ФОРМАТЕ:
{{format_instructions}}
"""
        self.prompt = ChatPromptTemplate.from_messages([
            ("human", self.system_prompt + "\n\nИстория диалога:\n{history}\n\nНовое сообщение: {message}")
        ])
        self.chain = self.prompt | self.llm | self.parser

    def chat(self, history: List[str], message: str) -> DiagnosticTurn:
        history_str = "\n".join(history)
        
        context_text = "Нет данных"
        if self.retriever:
            docs = self.retriever.invoke(history_str)
            context_text = "\n\n".join([d.page_content for d in docs])
            
        res_data = self.chain.invoke({
            "context": context_text,
            "format_instructions": self.parser.get_format_instructions(),
            "history": history_str,
            "message": message
        })
        
        return DiagnosticTurn(**res_data)

    def chat_history_to_list(self, state_data: dict) -> List[str]:
        """Extracts history from state data if available."""
        return state_data.get("history", [])

agent = MedicalAgent()
