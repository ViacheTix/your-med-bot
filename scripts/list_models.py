import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("AI_STUDIO", "")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
response = requests.get(url)
models = response.json()
print("Available models:")
for model in models.get("models", []):
    print(model["name"])
