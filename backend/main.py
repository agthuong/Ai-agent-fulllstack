from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json

app = FastAPI()

# Allow CORS for the React frontend
origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def event_generator():
    """A generator that simulates the agent's thinking process."""
    events = [
        {"node": "DB-MASTER", "status": "active", "message": "Received user request for a quote."},
        {"node": "DB-MASTER", "status": "inactive", "message": "Routing to Quote Expert..."},
        {"node": "DB-AI báo giá", "status": "active", "message": "Handling quote request."},
        {"node": "DB-AI báo giá", "status": "active", "tool": "Tool tra cứu giá", "message": "Calling price lookup tool..."},
        {"node": "DB-AI báo giá", "status": "active", "message": "Price lookup complete. Found price for 'sàn gỗ'."},
        {"node": "DB-AI báo giá", "status": "inactive", "message": "Quote calculation complete. Returning to Master."},
        {"node": "DB-MASTER", "status": "active", "message": "Synthesizing final response."},
        {"node": "DB-MASTER", "status": "complete", "message": "Final response generated."}
    ]
    
    for event in events:
        # Stream the event as a Server-Sent Event (SSE)
        yield f"data: {json.dumps(event)}\n\n"
        await asyncio.sleep(1.5) # Simulate work

@app.get("/stream")
async def stream_events(request: Request):
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 