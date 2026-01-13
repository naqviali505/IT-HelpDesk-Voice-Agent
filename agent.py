from groq import AsyncGroq
import os
from dotenv import load_dotenv
load_dotenv()
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

IT_HELPDESK_PROMPT="""
"""


async def query_groq(prompt_text):
    """
    Sends prompt_text to Groq chat model and returns response text.
    """
    prompt_text= IT_HELPDESK_PROMPT
    response = await client.chat.completions.create(
        messages=[
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": prompt_text}
        ],
        model="openai/gpt-oss-20b"  # replace with your LLM
    )
    return response.choices[0].message.content
