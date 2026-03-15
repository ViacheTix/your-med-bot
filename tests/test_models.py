import os
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("AI_STUDIO", "")

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=GOOGLE_API_KEY,
    temperature=0.1
)

try:
    print("Testing gemini-1.5-flash...")
    res = llm.invoke("Hello")
    print(res.content)
except Exception as e:
    print("Error:", e)

llm2 = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash-latest",
    google_api_key=GOOGLE_API_KEY,
    temperature=0.1
)

try:
    print("Testing gemini-1.5-flash-latest...")
    res = llm2.invoke("Hello")
    print(res.content)
except Exception as e:
    print("Error:", e)
