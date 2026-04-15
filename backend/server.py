import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from memory import ChatMemory
from helper import cancel_active_response,run_llm_response,get_retell
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/helpdesk/{call_id}")
async def retell_llm_handler(websocket: WebSocket, call_id: str):
    await websocket.accept()
    logger.info(f"Call {call_id} connected.")
    chat_memory = ChatMemory(limit=20)
    state = {
        "assistant_speaking": False,
        "active_response_id": None,
        "active_stream_task": None,
        "is_initial_turn": True,
        "last_user_input": None,
        "phase": "diagnosis",
        "proposed_slot": None,
        "user_email": None,
        "email_verified": False,
        "meeting_scheduled": False,
        "slot_confirmed": False
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
                if not transcript:
                    continue

                user_input = transcript[-1]["content"].strip()
                if user_input == state["last_user_input"] or not user_input:
                    continue

                state["last_user_input"] = user_input
                if state["meeting_scheduled"]:
                    logger.info("Meeting already scheduled. Ignoring further scheduling.")
                
                response_id = data["response_id"]
                logger.info(f"User: {user_input}")
                
                if state["phase"] == "slot_proposed":
                    if any(neg in user_input.lower() for neg in ["no", "not", "later", "different", "another"]):
                        logger.info("User wants to reschedule → flipping phase to 'reschedule'")
                        state["phase"] = "reschedule"
                        state["proposed_slot"] = None
                
                if state["active_stream_task"] is not None:
                    await asyncio.sleep(0.05)

                task = asyncio.create_task(run_llm_response(websocket, response_id, user_input, state, chat_memory))
                state["active_stream_task"] = task
                task.add_done_callback(lambda _: state.update({"active_stream_task": None}))
    except WebSocketDisconnect:
        logger.info(f"Call {call_id} disconnected.")
    except Exception as e:
        logger.error(f"Error in call {call_id}: {e}")


@app.post("/create-web-call")
async def create_web_call():
    # This creates a short-lived token for the frontend to use
    retell = get_retell()
    web_call_response = retell.call.create_web_call(
        agent_id="agent_c284e8a196c4a73f66c0bf3b60"
    )
    return {"access_token": web_call_response.access_token}