import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            # Receive greeting
            greeting_audio = await websocket.recv()
            print(f"Received audio bytes: {len(greeting_audio)}")
            greeting_text = await websocket.recv()
            print(f"Received text: {greeting_text}")
            
            # Send message
            msg = {"type": "user_message", "text": "hello"}
            await websocket.send(json.dumps(msg))
            
            # Receive response
            while True:
                resp = await websocket.recv()
                if isinstance(resp, str):
                    data = json.loads(resp)
                    print(f"Received: {data}")
                    if data.get("status") == "idle":
                        break
                else:
                    print(f"Received audio response: {len(resp)} bytes")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_ws())
