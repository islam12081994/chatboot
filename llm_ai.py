from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key =os.getenv("GROQ_API_KEY"),base_url="https://api.groq.com/openai/v1",
)

response = client.responses.create(input="commant installer wazuh",model="openai/gpt-oss-120b",
)
print(response.output_text)