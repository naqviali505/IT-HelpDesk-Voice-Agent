import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from memory import ChatMemory
from helper import cancel_active_response,run_llm_response,get_retell
load_dotenv()
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
    retell = get_retell()
    web_call_response = retell.call.create_web_call(
        agent_id="agent_959c3ec074022bde645b073b42"
    )
    return {"access_token": web_call_response.access_token}