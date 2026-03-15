import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def run_turn(session_id, message):
    print(f"\n--- Patient: {message} ---")
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    
    response = client.post("/chat_anamnesis", json=payload)
    if response.status_code != 200:
        print("Error:", response.status_code, response.text)
        return None, True
    
    data = response.json()
    print(f"Agent Reply: {data['reply']}")
    print("Turn Data:", json.dumps(data['turn_data'], ensure_ascii=False, indent=2))
    return data['session_id'], data['turn_data']['decision_reached']

def main():
    session_id = None
    messages = [
        "Здравствуйте. У меня сильно болит живот со вчерашнего дня.",
        "Болит справа внизу, боль довольно острая.",
        "Да, меня немного тошнит, но рвоты не было. Температура 37.8.",
        "Нет, хронических заболеваний нет. Боль усиливается при движении."
    ]

    for msg in messages:
        session_id, decision_reached = run_turn(session_id, msg)
        if decision_reached:
            print("\nAgent reached a decision and stopped asking questions.")
            break

if __name__ == "__main__":
    main()
