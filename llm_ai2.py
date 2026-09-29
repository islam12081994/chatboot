from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

while True:
    question = input("Toi : ")
    if question.lower() in ["exit", "quit"]:
        break

    response = client.responses.create(
        input=question,
        model="openai/gpt-oss-120b",
    )
    print("IA :", response.output_text)
    print()