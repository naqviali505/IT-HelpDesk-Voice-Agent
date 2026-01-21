import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from groq import AsyncGroq
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from retell import Retell
from memory import ChatMemory
from tools import create_meeting

# 1. Setup & Config
load_dotenv()
app = FastAPI()
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
retell = Retell(api_key=os.getenv("RETELL_API_KEY"))
# Your detailed instruction set
IT_HELPDESK_PROMPT = """
You are a knowledgeable IT Technician specializing in computer hardware and system configurations. 
Your task is to provide accurate, clear, and practical solutions to user questions about hardware 
components, system performance, troubleshooting, upgrades, and maintenance. Ask clarifying questions 
if needed, explain solutions step by step in simple language, and tailor your guidance to the user’s 
level of technical expertise.If the user’s issue cannot be resolved through your guidance, politely inform them and help schedule 
a meeting with a live IT agent at the next available appointment slot.Keep your messages brief and concise and ask relevant question to user regarding it. 
"""
# A tiny reminder prompt for subsequent turns to save tokens
TINY_REMINDER = "You are the IT Technician. Continue troubleshooting briefly."

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "create_meeting",
            "description": "Schedule a Google Meet and send email invite when the customer wants to book a call with a technician.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Subject of the meeting"},
                    "start_time_iso": {"type": "string", "description": "ISO 8601 format time"},
                    "end_time_iso": {"type": "string", "description": "ISO 8601 format time"},
                    "email": {"type": "string", "description": "Email to invite"}
                },
                "required": ["summary", "start_time_iso", "end_time_iso", "email"]
            }
        }
    }
]

@app.websocket("/helpdesk/{call_id}")
async def retell_llm_handler(websocket: WebSocket, call_id: str):
    await websocket.accept()
    print(f"Call {call_id} connected.")

    # State tracking
    is_initial_turn = True 
    chat_memory = ChatMemory(limit=6)
    # 2. Initial Handshake: Agent speaks first
    # This triggers the ElevenLabs voice in Retell immediately
    await websocket.send_json({
        "response_id": 0,
        "content": "Hello! I'm your IT Helpdesk Assistant. How can I help you today?",
        "content_complete": True
    })

    try:
        while True:
            # Receive transcript data from Retell
            data = await websocket.receive_json()
            # 3. Handle 'response_required' event
            if data.get("interaction_type") == "response_required":
                response_id = data.get("response_id")
                transcript = data.get("transcript", [])
                user_input = transcript[-1].get('content')
                chat_memory.add_message("user", user_input)
                active_prompt = IT_HELPDESK_PROMPT if is_initial_turn else TINY_REMINDER
                
                # Call Groq with streaming enabled
                print(chat_memory.get_messages())
                stream = await client.chat.completions.create(
                    messages=[{"role": "system", "content": active_prompt}]+ chat_memory.get_messages(),
                    model="llama-3.3-70b-versatile",stream=True,tools=tools,tool_choice="auto")
                is_initial_turn = False
                full_response_content = ""
                tool_call_chunks = []
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    # 1. Handle regular text response
                    if delta.content:
                        full_response_content += delta.content
                        await websocket.send_json({
                            "response_id": response_id,
                            "content": delta.content,
                            "content_complete": False
                        })
                    
                    # 2. Handle Tool Call (accumulate chunks)
                    if delta.tool_calls:
                        tool_call_chunks.append(delta.tool_calls[0])
                if tool_call_chunks:
                    # Stitch together the arguments (they arrive in pieces)
                    
                    fn_name = tool_call_chunks[0].function.name
                    fn_args_str = "".join([c.function.arguments for c in tool_call_chunks if c.function.arguments])
                    
                    if fn_name == "create_meeting":
                        # Execute the tool
                        args = json.loads(fn_args_str)
                        result = create_meeting(**args)
                        
                        # Add tool results to memory and get a final response
                        chat_memory.add_message("assistant", f"I've scheduled the meeting. Link: {result['meeting_link']}")
                        
                        # Let the user know it's done
                        await websocket.send_json({
                            "response_id": response_id,
                            "content": f"All set! I've sent the invite. The Google Meet link is ready.",
                            "content_complete": True
                        })
                else:
                    chat_memory.add_message("assistant", full_response_content)
                    # Signal that this specific turn is finished
                    await websocket.send_json({
                        "response_id": response_id,
                        "content": "",
                        "content_complete": True
                    })

    except WebSocketDisconnect:
        print(f"Call {call_id} disconnected.")
    except Exception as e:
        print(f"Error in call {call_id}: {e}")

@app.post("/create-web-call")
async def create_web_call():
    # This creates a short-lived token for the frontend to use
    web_call_response = retell.call.create_web_call(
        agent_id="agent_959c3ec074022bde645b073b42"
    )
    return {"access_token": web_call_response.access_token}