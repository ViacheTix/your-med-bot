import os
import sys

# Add project root to sys.path so we can import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)
response = client.post("/chat_anamnesis", json={"message": "У меня болит живот"})
print("Status:", response.status_code)
print("Response:", response.json())
