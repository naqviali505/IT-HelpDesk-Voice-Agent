import asyncio
import json
import re
import uuid
import logging
from fastapi import WebSocket
from groq import AsyncGroq
import pytz
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
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

async def run_llm_response(websocket: WebSocket,response_id: int,user_input: str,state: dict,chat_memory: ChatMemory):
    """
    Streams LLM output and detects tool calls.
    """
    now = datetime.now()
    current_date_str = now.strftime("%A, %B %d, %Y")
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
    3. Never suggest a time earlier than the current time.
    4.Only propose future available slots.

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

    CRITICAL TOOL USAGE RULE:
    - Only use check_availability when the user explicitly requests scheduling, booking, or technician help.
    - Do NOT use tools for general conversation, greetings, or troubleshooting questions.

    General conversation rules:
    • If the user interrupts, acknowledge them and continue naturally.
    • If the user asks unrelated questions, respond briefly then return to troubleshooting or scheduling.
    """
    if state.get("active_turn") and state["active_turn"] != response_id:
        return
    state["active_turn"] = response_id

    state["assistant_speaking"] = True
    state["active_response_id"] = response_id
    active_prompt = IT_HELPDESK_PROMPT
    state["is_initial_turn"] = False
    

    state["active_turn"] = response_id
    
    email_match = re.search(r"[\w\.-]+@[\w\.-]+", user_input)
    if email_match:
        state["user_email"] = email_match.group(0)
        state["email_verified"] = True
        logger.info(f"Captured email: {state['user_email']}")

    chat_memory.add_message("user", user_input)
    try:
        stream = await client.chat.completions.create(
            messages=[{"role": "system", "content": active_prompt}] + chat_memory.get_messages(),
            model="llama-3.3-70b-versatile",stream=True,tools=tools,tool_choice="auto")

        full_response = ""
        tool_calls = {}
        async for chunk in stream:
            if state["active_response_id"] != response_id:
                logger.info("🛑 Detected newer response → stopping current stream")
                break
            delta = chunk.choices[0].delta
            if delta.content:
                if state["active_response_id"] != response_id:
                    return
                full_response += delta.content
                await websocket.send_json({
                    "response_id": response_id,
                    "content": delta.content,
                    "content_complete": False
                })
            
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    tc_id = tc.id or "default"

                    if tc_id not in tool_calls:
                        tool_calls[tc_id] = {
                            "name": "",
                            "arguments": ""
                        }

                    if tc.function.name:
                        tool_calls[tc_id]["name"] = tc.function.name

                    if tc.function.arguments:
                        tool_calls[tc_id]["arguments"] += tc.function.arguments
        
        await websocket.send_json({
            "response_id": response_id,
            "content": "",
            "content_complete": True
        })
        
        if full_response:
            chat_memory.add_message("assistant", full_response)

        state["assistant_speaking"] = False
        state["active_response_id"] = None
        
        if state.get("meeting_scheduled"):
            logger.info("Ignoring tool call after meeting booked")
            return
        if tool_calls:
            await handle_tool_calls(websocket,response_id,tool_calls,active_prompt,chat_memory,state,user_input)
    
    except asyncio.CancelledError:
        logger.warning("🛑 LLM stream cancelled cleanly")
        return

    except Exception as e:
        logger.error(f"LLM error: {e}")

    finally:
        state["assistant_speaking"] = False
        state["active_response_id"] = None
        state["active_turn"] = None

async def handle_tool_calls(websocket: WebSocket,response_id: int,tool_calls: dict,active_prompt: str,chat_memory: ChatMemory,state:dict,user_input:str):
    """
    Executes tools and streams follow-up LLM response.
    """
    try:
        logger.info("Tool Call Chunks "+str(tool_calls))
        tool_results = []
        tool_executed = False

        for tc_id, tc in tool_calls.items():
            tool_executed = True
            fn_name = tc["name"]
            fn_args_str = tc["arguments"]
            try:
                parsed = json.loads(fn_args_str or "{}")
                args = parsed if isinstance(parsed, dict) else {}
            except Exception:
                args = {}            
            
            result = None
            if fn_name == "check_availability":
                result = check_availability()
                state["proposed_slot"] = result

            elif fn_name == "create_meeting":
                email = args.get("email") or state.get("user_email")

                result = create_meeting(
                    summary=args.get("summary", "IT Helpdesk Meeting"),
                    slot=state.get("proposed_slot"),
                    email=email
                )
                state["meeting_scheduled"] = True

            tool_results.append((tc_id, fn_name, result))
        
        for tool_call_id, fn_name, result in tool_results:
            chat_memory.add_message(
                role="tool",
                content=json.dumps(result),
                tool_call_id=tool_call_id,
                name=fn_name
            )

        if tool_executed:
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