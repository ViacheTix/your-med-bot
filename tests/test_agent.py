import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.agent import agent

def test_agent():
    load_dotenv()
    print("Testing MedicalAgent with Gemma 3...")
    try:
        history = []
        message = "У меня болит голова и тошнота"
        print(f"User: {message}")
        response = agent.chat(history, message)
        print("Agent Response Model Object:", response)
        print("Question:", response.question)
        print("Decision Reached:", response.decision_reached)
    except Exception as e:
        print(f"Error during agent.chat: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_agent()
