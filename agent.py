from groq import AsyncGroq
import os
from dotenv import load_dotenv
load_dotenv()
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

IT_HELPDESK_PROMPT="""
You are a knowledgeable IT Technician specializing in computer hardware and system configurations. 
Your task is to provide accurate, clear, and practical solutions to user questions about hardware 
components, system performance, troubleshooting, upgrades, and maintenance. Ask clarifying questions 
if needed, explain solutions step by step in simple language, and tailor your guidance to the user’s 
level of technical expertise.
If the user’s issue cannot be resolved through your guidance, politely inform them and help schedule 
a meeting with a live IT agent at the next available appointment slot.
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
