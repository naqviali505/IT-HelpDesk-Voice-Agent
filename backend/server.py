import json
import os
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from groq import AsyncGroq
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from retell import Retell
from memory import ChatMemory
from tools import create_meeting,check_availability
from datetime import datetime

# 1. Setup & Config
load_dotenv()
app = FastAPI()
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
retell = Retell(api_key=os.getenv("RETELL_API_KEY"))
# Your detailed instruction set
now = datetime.now()
current_date_str = now.strftime("%A, %B %d, %Y")

IT_HELPDESK_PROMPT = f"""
## ROLE
You are a knowledgeable IT Technician specializing in hardware and system configurations. 
our task is to provide accurate, clear, and practical solutions to user questions about hardware 
components, system performance, troubleshooting,upgrades, and maintenance.

## CURRENT CONTEXT
- Today's Date: {current_date_str}
- Technician Hours: 9:00 AM - 5:00 PM
- Technician Lunch (RESERVED): 1:00 PM - 2:00 PM daily (Never book during this hour).

## SCHEDULING WORKFLOW (MANDATORY)
If a problem cannot be resolved and requires a technician visit, follow these steps exactly:

1. **FIND SLOT**: Call 'check_availability'. This tool automatically searches for the first 30-minute gap within the next 7 days excluding Saturday and Sunday.
2. **PROPOSE**: Using the tool's result, say: "I've checked the schedule. The first available time is [Day], [Date] at [Time]. Does that work for you?"
3. **EMAIL CAPTURE**: Once they agree to a time, you MUST ask them to spell their email:
   - "Great. To send the invite to the right place, could you please spell your email address for me?"
4. **VERIFY**: Repeat the spelled email back (e.g., "I have that as n-a-m-e at gmail dot com, correct?").
5. **BOOK**: Only after the email is verified, call 'create_meeting' using the exact ISO timestamps provided by the 'check_availability' tool.

## RULES
- Be conversational but concise.
- Never guess availability; always call 'check_availability' first.
- If the user rejects the first slot, ask them for their preferred date and call 'check_availability' again.
- Always put the user's email in the meeting 'description' to ensure the invite goes through.
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
                    # 1. Stitch together arguments
                    fn_name = tool_call_chunks[0].function.name
                    fn_args_str = "".join([c.function.arguments for c in tool_call_chunks if c.function.arguments])
                    args = json.loads(fn_args_str)
                    
                    # 2. Add the assistant's "intent" to call the tool to memory
                    # Required for Groq's conversational history to stay valid
                    tool_call_id = tool_call_chunks[0].id if hasattr(tool_call_chunks[0], 'id') else "call_" + str(uuid.uuid4())
                    chat_memory.add_message("assistant", None, tool_calls=[{
                        "id": tool_call_id,
                        "type": "function",
                        "function": {"name": fn_name, "arguments": fn_args_str}
                    }])

                    # 3. Execute the appropriate tool
                    if fn_name == "check_availability":
                        result_data = check_availability(args.get("date_str"))
                        msg_to_user = f"I've checked the schedule: {result_data}"
                    
                    elif fn_name == "create_meeting":
                        # Ensure you've removed 'attendees' in your create_meeting function to avoid 403
                        result = create_meeting(**args)
                        result_data = f"Success. Meeting Link: {result.get('meeting_link')}"
                        msg_to_user = "All set! I've scheduled that and sent the invite to your email."

                    # 4. Add the TOOL result to memory
                    chat_memory.add_message(
                        role="tool", 
                        content=str(result_data), 
                        tool_call_id=tool_call_id, 
                        name=fn_name
                    )

                    # 5. Inform Retell to speak the confirmation
                    await websocket.send_json({
                        "response_id": response_id,
                        "content": msg_to_user,
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