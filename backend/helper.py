import asyncio
import json
import uuid
import logging
from fastapi import WebSocket
from groq import AsyncGroq
from memory import ChatMemory
from retell import Retell
from datetime import datetime
import os
from tool_schema import tools
from tool_calls import check_availability,create_meeting
from dotenv import load_dotenv
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()
now = datetime.now()
current_date_str = now.strftime("%A, %B %d, %Y")
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
IT_HELPDESK_PROMPT = f"""
You are an IT Helpdesk voice assistant helping users troubleshoot issues or schedule a technician visit.

Today's date: {current_date_str}
Current Time: {now.strftime("%H:%M:%S")}

Technician working hours:
• Monday–Friday
• 9:00 AM – 5:00 PM
• Lunch break: 1:00 PM – 2:00 PM

Your responsibilities:
1. Help diagnose simple IT issues.
2. If a technician visit is required, schedule a 30-minute appointment.

Guidelines:
• Be conversational and concise.
• Keep responses under 20 words.
• Speak naturally as if talking on the phone.

Scheduling behavior:
• Use the tool `check_availability` to find the next available technician slot.
• After proposing a time, wait for the user to confirm before scheduling.
• Ask the user for their email address to send the meeting invite.
• Repeat the spelled email back to confirm accuracy.

Tool usage rules:
• Never guess or generate an email address.
• Only use the email address provided by the user.
• Only call `create_meeting` after the user confirms both:
  - the proposed time
  - their email address

General conversation rules:
• If the user interrupts, acknowledge them and continue naturally.
• If the user asks unrelated questions, respond briefly then return to troubleshooting or scheduling.
"""

async def cancel_active_response(
    websocket: WebSocket,
    state: dict
):
    """
    Cancels any active assistant speech + LLM stream.
    """
    if state["assistant_speaking"] and state["active_response_id"]:
        logger.info("🔴 Barge-in detected → cancelling assistant response")
        await websocket.send_json({
            "type": "response_cancel",
            "response_id": state["active_response_id"]
        })

    if state["active_stream_task"]:
        state["active_stream_task"].cancel()

    state["assistant_speaking"] = False
    state["active_response_id"] = None
    state["active_stream_task"] = None

async def run_llm_response(websocket: WebSocket,response_id: int,user_input: str,state: dict,chat_memory: ChatMemory):
    """
    Streams LLM output and detects tool calls.
    """
    state["assistant_speaking"] = True
    state["active_response_id"] = response_id
    active_prompt = IT_HELPDESK_PROMPT
    state["is_initial_turn"] = False
    chat_memory.add_message("user", user_input)

    try:
        stream = await client.chat.completions.create(
            messages=[{"role": "system", "content": active_prompt}] + chat_memory.get_messages(),
            model="llama-3.3-70b-versatile",stream=True,tools=tools,tool_choice="auto")

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
        
        if state.get("meeting_scheduled"):
            logger.info("Ignoring tool call after meeting booked")
            return
        if tool_call_chunks:
            await handle_tool_calls(websocket,response_id,tool_call_chunks,active_prompt,chat_memory,state)

    except asyncio.CancelledError:
        logger.warning("🛑 LLM stream cancelled cleanly")

    except Exception as e:
        logger.error(f"LLM error: {e}")

    finally:
        state["assistant_speaking"] = False
        state["active_response_id"] = None

async def handle_tool_calls(websocket: WebSocket,response_id: int,tool_call_chunks: list,active_prompt: str,chat_memory: ChatMemory,state:dict):
    """
    Executes tools and streams follow-up LLM response.
    """
    try:
        logger.info("Tool Call Chunks "+str(tool_call_chunks))
        tool_call = tool_call_chunks[0]
        fn_name = tool_call.function.name
        fn_args_str = "".join(c.function.arguments for c in tool_call_chunks if c.function.arguments)
        args = json.loads(fn_args_str) if fn_args_str else {}
        tool_call_id = getattr(tool_call, "id", f"call_{uuid.uuid4()}")
        chat_memory.add_message("assistant",None,tool_calls=[{
                "id": tool_call_id,
                "type": "function",
                "function": {"name": fn_name, "arguments": fn_args_str}
            }])

        if fn_name == "check_availability":
            if state["phase"] not in ["diagnosis", "reschedule"]:
                logger.warning("Blocked check_availability in phase %s", state["phase"])
                return
            result = check_availability()
            state["proposed_slot"] = result
            state["phase"] = "slot_proposed"

        elif fn_name == "create_meeting":
            # Block duplicate meeting
            if state.get("meeting_scheduled"):
                logger.warning("Meeting already scheduled. Blocking duplicate.")
                return

            # Ensure a slot was proposed
            if state.get("proposed_slot") is None:
                logger.warning("No proposed slot exists.")
                await websocket.send_json({
                    "response_id": response_id,
                    "content": "We need to propose a slot first. Let me find the next available time.",
                    "content_complete": True
                })
                state["phase"] = "reschedule"
                return

            # If we don't have user email yet, explicitly ask for it
            if state.get("user_email") is None:
                logger.info("Asking user for email before scheduling")
                await websocket.send_json({
                    "response_id": response_id,
                    "content": "To send the invite, could you please spell your email address for me?",
                    "content_complete": True
                })
                state["phase"] = "email_pending"
                return

            # Validate the user-provided email
            email = state["user_email"].strip()
            invalid_emails = ["user@example.com","test@example.com","example@example.com"]
            if not email or "@" not in email or email.lower() in invalid_emails:
                logger.warning("Invalid or placeholder email provided: %s", email)
                state["user_email"] = None  # reset to ask again
                await websocket.send_json({
                    "response_id": response_id,
                    "content": "That doesn't look like a valid email. Could you spell it for me again?",
                    "content_complete": True
                })
                state["phase"] = "email_pending"
                return
            email = email.replace("-", "").replace(" ", "").lower()
            # Create the meeting
            meeting_info = create_meeting(
                email=email,
                start_time_iso=state["proposed_slot"]["start_time_iso"],
                end_time_iso=state["proposed_slot"]["end_time_iso"],
                summary="IT Helpdesk Meeting"
            )

            # Update state
            state["meeting_scheduled"] = True
            state["phase"] = "meeting_booked"
            result = meeting_info
            logger.info("Meeting successfully scheduled for email %s", email)
        else:
            logger.error("Unknown tool requested: %s", fn_name)
            result = {"error": "Unknown tool"}

        chat_memory.add_message(role="tool",content=json.dumps(result),tool_call_id=tool_call_id,name=fn_name)
        logger.debug("Tool result added to chat memory")
        logger.info("Starting follow-up LLM streaming response")

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

        logger.info("LLM streaming completed")

        await websocket.send_json({
            "response_id": response_id,
            "content": "",
            "content_complete": True
        })

    except Exception as e:
        logger.exception("Error while handling tool call: %s", str(e))
        await websocket.send_json({
            "response_id": response_id,
            "content": "Sorry, something went wrong while processing your request.",
            "content_complete": True
        })

def get_retell():
    return Retell(api_key=os.getenv("RETELL_API_KEY"))