import os
import sys
import json
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List, Optional

load_dotenv()
GOOGLE_API_KEY = os.getenv("AI_STUDIO", "")

class DiagnosticTurn(BaseModel):
    extracted_symptoms: List[str] = Field(description="Список всех извлеченных симптомов пациента.")
    urgency: str = Field("Низкая", description="Степень срочности состояния: Высокая / Средняя / Низкая")
    suggested_doctor: str = Field("Терапевт", description="Рекомендуемый профильный врач")
    express_appointment: bool = Field(False, description="Предлагать ли экспресс-приём? (true если Высокая/Средняя срочность)")
    question: Optional[str] = Field(None, description="Следующий уточняющий вопрос пациенту, чтобы собрать больше информации для врача")
    decision_reached: bool = Field(False, description="Завершен ли сбор информации? (true если собрано достаточно симптомов и картина ясна, обычно после 3-5 вопросов)")
    preliminary_diagnosis: Optional[str] = Field(None, description="Предварительная гипотеза о заболевании (скрыто от пациента, только для врача)")

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

def run_test_for_model(model_name: str, retriever):
    print(f"\n--- Testing Model: {model_name} ---")
    try:
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=GOOGLE_API_KEY,
            temperature=0.1
        )
        if "gemma" in model_name.lower():
            # Gemma models often don't support system instructions through the API yet
            prompt_to_use = ChatPromptTemplate.from_messages([
                ("human", SYSTEM_PROMPT + "\n\nИстория диалога:\n{history}\n\nНовое сообщение: {message}")
            ])
        else:
            prompt_to_use = prompt
            
        chain = prompt_to_use | llm | parser

        history_str = ""
        message = "У меня сильно болит живот, особенно в правом нижнем боку. Еще тошнит."
        history_str += f"\nПациент: {message}"

        # RAG
        docs = retriever.invoke(history_str)
        context_text = "\n\n".join([d.page_content for d in docs])

        res_data = chain.invoke({
            "context": context_text,
            "format_instructions": parser.get_format_instructions(),
            "history": history_str,
            "message": message
        })

        return res_data, context_text
    except Exception as e:
        print(f"Error with {model_name}: {e}")
        return {"error": str(e)}, ""

def main():
    print("Loading Local Embedding Model...")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    print("Loading FAISS Vector Store...")
    FAISS_INDEX_DIR = "data/faiss_db"
    try:
        vectorstore = FAISS.load_local(FAISS_INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    except Exception as e:
        print("FAISS load error:", e)
        return

    models_to_test = [
        "gemini-3-flash-preview", 
        "gemma-3-27b-it", 
        "gemini-2.5-flash-lite"
    ]

    for model in models_to_test:
        res, context = run_test_for_model(model, retriever)
        
        md_content = f"# Model Test: {model}\n\n"
        md_content += f"**User Message:** У меня сильно болит живот, особенно в правом нижнем боку. Еще тошнит.\n\n"
        md_content += "## LLM Output (JSON Parsed)\n```json\n"
        md_content += json.dumps(res, ensure_ascii=False, indent=2)
        md_content += "\n```\n"

        filename = f"tests/{model.replace('.', '_')}_response.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Saved results to {filename}")

if __name__ == "__main__":
    main()
