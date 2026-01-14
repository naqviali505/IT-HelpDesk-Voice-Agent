import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
IT_HELPDESK_PROMPT="""
You are a knowledgeable IT Technician specializing in computer hardware and system configurations. 
Your task is to provide accurate, clear, and practical solutions to user questions about hardware 
components, system performance, troubleshooting, upgrades, and maintenance. Ask clarifying questions 
if needed, explain solutions step by step in simple language, and tailor your guidance to the user’s 
level of technical expertise.
If the user’s issue cannot be resolved through your guidance, politely inform them and help schedule 
a meeting with a live IT agent at the next available appointment slot.
Keep your messages brief and concise and ask relevant question to user regarding it.
"""

@app.websocket("/helpdesk/{call_id}")
async def retell_llm_handler(websocket: WebSocket, call_id: str):
    await websocket.accept()
    
    # Send the first message (Agent speaks first)
    await websocket.send_json({
        "response_id": 0,
        "content": "Hello! I'm your IT Helpdesk Assistant. How can I help you today?",
        "content_complete": True
    })

    try:
        while True:
            data = await websocket.receive_json()
            
            # 2. Only respond if Retell explicitly requests a response
            if data.get("interaction_type") == "response_required":
                transcript = data.get("transcript", [])
                
                # 3. Call Groq (Streaming for speed)
                stream = await client.chat.completions.create(
                    messages=[{"role": "system", "content": IT_HELPDESK_PROMPT}] + transcript,
                    model="llama3-70b-8192",
                    stream=True
                )

                # 4. Stream text chunks back to Retell
                full_response = ""
                async for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_response += content
                        await websocket.send_json({
                            "response_id": data["response_id"],
                            "content": content,
                            "content_complete": False
                        })
                
                # Finalize the turn
                await websocket.send_json({
                    "response_id": data["response_id"],
                    "content": "",
                    "content_complete": True
                })

    except WebSocketDisconnect:
        print(f"Call {call_id} ended.")