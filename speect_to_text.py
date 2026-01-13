# pip install websockets pyaudio
import asyncio
import websockets
import json
import os
import pyaudio
from dotenv import load_dotenv
from agent import query_groq

async def stream_audio():
    api_key = os.getenv('DEEPGRAM_API_KEY')
    uri = "wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1&punctuate=true&interim_results=true"
    headers = [("Authorization", f"Token {api_key}")]
    conversation_history=[]
    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16,channels=1,rate=16000,input=True,frames_per_buffer=1024)
    async with websockets.connect(uri, additional_headers=headers) as websocket:
        async def send_audio():
            while True:
                data = stream.read(1024, exception_on_overflow=False)
                await websocket.send(data)

        async def receive_transcript():
            buffer = ""
            async for message in websocket:
                data = json.loads(message)
                if "channel" in data:
                    transcript = data["channel"]["alternatives"][0]["transcript"]
                    if transcript:
                        print("Real-time Transcript:", transcript)
                        buffer += " " + transcript

                        # Example: trigger LLM when a sentence ends
                        if transcript.strip().endswith((".", "?", "!")):
                            conversation_history.append(buffer.strip())
                            llm_response = await query_groq(buffer.strip())
                            print("LLM Response:", llm_response)
                            buffer = ""  # reset buffer for next segment


        await asyncio.gather(send_audio(), receive_transcript())

load_dotenv()
asyncio.run(stream_audio())
