"""List all available Groq models on this account."""
import os
from dotenv import load_dotenv
load_dotenv(".env")

from groq import Groq
client = Groq(api_key=os.environ.get("GROQ_API_KEY", "").strip())

models = client.models.list()
print("Available models:")
for m in sorted(models.data, key=lambda x: x.id):
    print(f"  {m.id}")
