import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from groq import AsyncGroq
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from memory import ChatMemory
from tools import create_meeting,check_availability
from helper import cancel_active_response,handle_tool_calls,run_llm_response
# 1. Setup & Config
load_dotenv()
app = FastAPI()
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

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
            "name": "check_availability",
            "description": "Check the technician's busy slots for a specific date to find an available time between 9 AM and 5 PM.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_meeting",
            "description": "Finalize the booking. ONLY call this after checking availability, confirming a time with the user, and asking the user to spell their email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Subject of the meeting (e.g., Internet Issue)"},
                    "start_time_iso": {"type": "string", "description": "ISO 8601 format time (e.g., 2026-01-22T10:00:00Z)"},
                    "end_time_iso": {"type": "string", "description": "ISO 8601 format time (usually 30 mins after start)"},
                    "email": {"type": "string", "description": "The customer's email address"}
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

    chat_memory = ChatMemory(limit=6)

    state = {
        "assistant_speaking": False,
        "active_response_id": None,
        "active_stream_task": None,
        "is_initial_turn": True
    }

    await websocket.send_json({
        "response_id": 0,
        "content": "Hello! I'm your IT Helpdesk Assistant. How can I help you today?",
        "content_complete": True
    })

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("interaction_type") == "response_required":
                transcript = data.get("transcript", [])
                user_input = transcript[-1]["content"]
                response_id = data["response_id"]

                print(f"User: {user_input}")

                await cancel_active_response(websocket, state)

                state["active_stream_task"] = asyncio.create_task(
                    run_llm_response(
                        websocket,
                        response_id,
                        user_input,
                        state,
                        chat_memory
                    )
                )

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