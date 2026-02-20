import asyncio
import json
import uuid
from fastapi import WebSocket
from groq import AsyncGroq
from memory import ChatMemory
from retell import Retell
from datetime import datetime
import os
from tool_schema import tools
from tool_calls import check_availability,create_meeting
from dotenv import load_dotenv
load_dotenv()
now = datetime.now()
current_date_str = now.strftime("%A, %B %d, %Y")
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
IT_HELPDESK_PROMPT = f"""
## ROLE
You are a knowledgeable and concise IT Technician. Your goal is to troubleshoot hardware/system issues or schedule a technician visit if needed.

## CURRENT CONTEXT
- Today's Date: {current_date_str}
- Technician Hours: 9:00 AM - 5:00 PM (Mon-Fri)
- Technician Lunch: 1:00 PM - 2:00 PM (Strictly reserved).

## SCHEDULING WORKFLOW (MANDATORY PHASES)
You must complete each phase in order. Never skip to Phase 3 before Phase 2.

### PHASE 1: FIND & PROPOSE SLOT
- Call 'check_availability' (no arguments) to find the first 30-minute gap in the next 7 days.
- Propose the specific Day, Date, and Time to the user.
- **WAIT** for the user to explicitly agree (e.g., "Yes," "That works," "Okay").

### PHASE 2: THE EMAIL CHALLENGE
- **ONLY** after the user agrees to the time, you MUST capture their email.
- You do not know their email. You MUST ask: "To send the invite, could you please spell your email address for me?"
- Once they spell it, repeat it back (e.g., "I have that as n-a-m-e at gmail dot com, correct?") to verify.

### PHASE 3: FINAL BOOKING
- **ONLY** after the user confirms the spelling is correct, call 'create_meeting'.
- Use the 'start_time_iso' and 'end_time_iso' provided previously by the 'check_availability' tool.

## RULES
- RECOVERY: If the user interrupts you, do not skip ahead. Acknowledge what they said, then resume from the exact Phase you were in.
- NEVER call 'create_meeting' without a verified email from the current conversation.
- If the user wants to reschedule, reset to PHASE 1.
- Be conversational but keep responses under 20 words.
- Always put the user's email in the meeting 'description'.
"""
# A tiny reminder prompt for subsequent turns to save tokens
TINY_REMINDER = "You are the IT Technician. Continue troubleshooting briefly."

async def cancel_active_response(
    websocket: WebSocket,
    state: dict
):
    """
    Cancels any active assistant speech + LLM stream.
    """
    if state["assistant_speaking"] and state["active_response_id"]:
        print("🔴 Barge-in detected → cancelling assistant response")
        await websocket.send_json({
            "type": "response_cancel",
            "response_id": state["active_response_id"]
        })

    if state["active_stream_task"]:
        state["active_stream_task"].cancel()

    state["assistant_speaking"] = False
    state["active_response_id"] = None
    state["active_stream_task"] = None

async def run_llm_response(websocket: WebSocket,response_id: int,user_input: str,state: dict,
                           chat_memory: ChatMemory):
    """
    Streams LLM output and detects tool calls.
    """
    state["assistant_speaking"] = True
    state["active_response_id"] = response_id

    active_prompt = IT_HELPDESK_PROMPT if state["is_initial_turn"] else TINY_REMINDER
    state["is_initial_turn"] = False

    chat_memory.add_message("user", user_input)

    try:
        stream = await client.chat.completions.create(
            messages=[{"role": "system", "content": active_prompt}] + chat_memory.get_messages(),
            model="llama-3.3-70b-versatile",
            stream=True,
            tools=tools,
            tool_choice="auto"
        )

        full_response = ""
        tool_call_chunks = []

        async for chunk in stream:
            delta = chunk.choices[0].delta

            if delta.content:
                full_response += delta.content
                await websocket.send_json({
                    "response_id": response_id,
                    "content": delta.content,
                    "content_complete": False
                })

            if delta.tool_calls:
                tool_call_chunks.append(delta.tool_calls[0])

        if full_response:
            chat_memory.add_message("assistant", full_response)

        state["assistant_speaking"] = False
        state["active_response_id"] = None
        print("About to handle tool calls")
        if tool_call_chunks:
            await handle_tool_calls(websocket,response_id,tool_call_chunks,active_prompt,chat_memory)

    except asyncio.CancelledError:
        print("🛑 LLM stream cancelled cleanly")

    except Exception as e:
        print(f"LLM error: {e}")

    finally:
        state["assistant_speaking"] = False
        state["active_response_id"] = None

async def handle_tool_calls(websocket: WebSocket,response_id: int,tool_call_chunks: list,active_prompt: str,
                            chat_memory: ChatMemory):
    """
    Executes tools and streams follow-up LLM response.
    """
    print("In handle_tool_calls")
    tool_call = tool_call_chunks[0]
    fn_name = tool_call.function.name
    fn_args_str = "".join(
        c.function.arguments for c in tool_call_chunks if c.function.arguments
    )

    args = json.loads(fn_args_str) if fn_args_str else {}
    tool_call_id = getattr(tool_call, "id", f"call_{uuid.uuid4()}")

    chat_memory.add_message("assistant",None,
        tool_calls=[{
            "id": tool_call_id,
            "type": "function",
            "function": {"name": fn_name, "arguments": fn_args_str}
        }]
    )

    # ---- Execute tool ----
    if fn_name == "check_availability":
        result = check_availability()

    elif fn_name == "create_meeting":
        email = args.get("email", "").strip()
        if not email or "@" not in email:
            chat_memory.add_message(
                role="tool",
                content="Error: Missing or invalid email.",
                tool_call_id=tool_call_id,
                name=fn_name
            )
            await websocket.send_json({
                "response_id": response_id,
                "content": "Could you please spell your email address for me?",
                "content_complete": True
            })
            return
        meeting_info = create_meeting(**args)
        if meeting_info["status"] == "success":
            print(f"Scheduled Zoom Meeting: {meeting_info['meeting_link']} (ID {meeting_info['meeting_id']})")
#         service.events().insert(
#     calendarId=CALENDAR_ID,
#     body={
#         "summary": summary,
#         "start": {"dateTime": start_time_iso, "timeZone": "UTC"},
#         "end": {"dateTime": end_time_iso, "timeZone": "UTC"},
#         "attendees": [{"email": email}],
#         "description": f"Zoom Link: {meeting_link}"
#     }
# ).execute()


    else:
        result = {"error": "Unknown tool"}

    chat_memory.add_message(
        role="tool",
        content=json.dumps(result),
        tool_call_id=tool_call_id,
        name=fn_name
    )

    # ---- Follow-up LLM response ----
    followup_stream = await client.chat.completions.create(
        messages=[{"role": "system", "content": active_prompt}] + chat_memory.get_messages(),
        model="llama-3.3-70b-versatile",
        stream=True
    )

    async for chunk in followup_stream:
        delta = chunk.choices[0].delta
        if delta.content:
            await websocket.send_json({
                "response_id": response_id,
                "content": delta.content,
                "content_complete": False
            })

    await websocket.send_json({
        "response_id": response_id,
        "content": "",
        "content_complete": True
    })

def get_retell():
    return Retell(api_key=os.getenv("RETELL_API_KEY"))