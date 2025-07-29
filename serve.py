from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import uuid
from pathlib import Path
import json
from typing import Any
import traceback

from src.react_agent.graph import graph
from langgraph.graph import END
from src.react_agent.state import State
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from fastapi.responses import JSONResponse
import shutil
import os
from src.react_agent.vision import get_gemini_vision_report
from src.react_agent.prompts import VISION_PROMPT
from src.react_agent.quote_parser import parse_image_report

# --- JSON Serialization Helper ---
def _cleanup_state_for_json(data: Any) -> Any:
    """
    Recursively cleans data to make it JSON serializable.
    Converts BaseMessage objects to dicts and other non-serializable objects to strings.
    """
    if isinstance(data, dict):
        return {k: _cleanup_state_for_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_cleanup_state_for_json(i) for i in data]
    if isinstance(data, BaseMessage):
        return {"type": data.type, "content": data.content}
    
    # Special handling for tool_results to ensure it's always properly serializable
    if isinstance(data, str) and '"title":' in data:
        try:
            # This might be a JSON string containing a title field
            # Try to parse it and then re-serialize it properly
            print(f"DEBUG: Found potential JSON string with 'title' field, attempting to parse")
            parsed = json.loads(data)
            return parsed  # Return the parsed object, not the string
        except json.JSONDecodeError:
            # If it's not valid JSON, just continue with normal processing
            print(f"DEBUG: String contains 'title' but is not valid JSON")
            pass
    
    # Add other non-serializable types here if they appear in the future
    try:
        # A risky but often effective fallback
        json.dumps(data)
        return data
    except (TypeError, OverflowError) as e:
        print(f"DEBUG: JSON serialization error for {type(data)}: {e}")
        return str(data)

# --- FastAPI App Setup ---
app = FastAPI(
    title="React Agent Server",
    version="1.0",
    description="A simple API server for a React-based agent",
)

# --- CORS ---
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WebSocket Endpoint ---
@app.websocket("/ws/invoke")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            
            # Reconstruct the message history from the client
            message_history: list[BaseMessage] = [
                HumanMessage(content=msg["text"]) if msg["sender"] == "user" 
                else AIMessage(content=msg["text"]) 
                for msg in data["history"]
            ]

            # Nếu có image report từ frontend, thêm vào messages
            if "image_report" in data:
                message_history.append(SystemMessage(content=f"[Image Analysis Report]:\n{data['image_report']}"))

            initial_state: State = {
                "messages": message_history,
            }
            
            # Use astream() to get the full state after each node runs.
            async for step in graph.astream(initial_state):
                node_name = list(step.keys())[0]
                
                if node_name == END:
                    continue
                    
                current_state = step[node_name]
                
                # Recursively clean the entire state object before sending
                try:
                    serializable_state = _cleanup_state_for_json(current_state)
                    
                    # Extra validation step to catch any serialization issues
                    try:
                        # Test if the cleaned state can be properly serialized
                        json.dumps(serializable_state)
                    except Exception as json_err:
                        print(f"ERROR: State still not JSON serializable after cleaning: {json_err}")
                        # Fall back to a simpler representation
                        serializable_state = {
                            "error": "State serialization failed",
                            "node": node_name,
                            "available_keys": list(current_state.keys())
                        }
                    
                    trace_data = {
                        "node": node_name,
                        "state": serializable_state
                    }
                    await websocket.send_json(trace_data)
                except Exception as clean_err:
                    print(f"ERROR during state cleaning: {clean_err}")
                    print(traceback.format_exc())
                    # Send a simplified error state
                    await websocket.send_json({
                        "node": node_name,
                        "state": {"error": f"Failed to process state: {str(clean_err)}"}
                    })
                    
    except WebSocketDisconnect:
        print(f"Client disconnected.")
    except Exception as e:
        print(f"An error occurred: {e}")
        print(traceback.format_exc())
        await websocket.close(code=1011, reason=f"Internal Server Error: {e}")

HISTORY_DIR = "sessions"
os.makedirs(HISTORY_DIR, exist_ok=True)

def get_session_id(request: Request):
    # Lấy session_id từ header hoặc tạo mới
    session_id = request.headers.get('X-Session-Id')
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id

def load_history(session_id):
    path = os.path.join(HISTORY_DIR, f"{session_id}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history(session_id, history):
    path = os.path.join(HISTORY_DIR, f"{session_id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(None)):
    """Upload image and return image report only."""
    temp_image_path = None
    try:
        if file:
            temp_image_path = f"uploads/{uuid.uuid4()}_{file.filename}"
            os.makedirs("uploads", exist_ok=True)
            with open(temp_image_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            image_report = await get_gemini_vision_report(temp_image_path, prompt=VISION_PROMPT)
            materials = parse_image_report(image_report)
            return JSONResponse({
                "image_report": image_report,
                "materials": materials
            })
        else:
            return JSONResponse({"error": "No file provided"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"Image analysis failed: {e}"}, status_code=500)
    finally:
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)

@app.post("/api/chat")
async def chat_api(request: Request, message: str = Form(None), file: UploadFile = File(None)):
    session_id = get_session_id(request)
    history = load_history(session_id)
    image_report = None
    temp_image_path = None
    materials = None
    try:
        if file:
            temp_image_path = f"uploads/{uuid.uuid4()}_{file.filename}"
            os.makedirs("uploads", exist_ok=True)
            with open(temp_image_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            image_report = await get_gemini_vision_report(temp_image_path, prompt=VISION_PROMPT)
            materials = parse_image_report(image_report)
            # Không thêm image report vào history - sẽ được xử lý trong graph
        
        if message:
            history.append({
                'type': 'human',
                'content': message
            })
        save_history(session_id, history)
        
        # Truyền đầy đủ history vào graph
        messages_for_graph = []
        for msg in history:
            if msg['type'] == 'human':
                messages_for_graph.append(HumanMessage(content=msg['content']))
            elif msg['type'] == 'ai':
                messages_for_graph.append(AIMessage(content=msg['content']))
            elif msg['type'] == 'system':
                messages_for_graph.append(SystemMessage(content=msg['content']))
        
        # Nếu có image report, thêm vào messages_for_graph
        if image_report:
            messages_for_graph.append(SystemMessage(content=f"[Image Analysis Report]:\n{image_report}"))
        
        initial_state = {"messages": messages_for_graph}
        if message or image_report:
            final_state = None
            async for output in graph.astream(initial_state):
                final_state = output
                print(f"DEBUG: Processing output: {list(output.keys())}")
                for node_name, node_state in output.items():
                    if node_name != END:
                        print(f"DEBUG: Node {node_name} state keys: {list(node_state.keys())}")
            
            # Tìm AI message từ final state
            ai_message = None
            if final_state:
                for node_name, node_state in final_state.items():
                    if node_name != END and 'messages' in node_state:
                        messages = node_state['messages']
                        ai_messages = [msg for msg in messages if hasattr(msg, 'type') and msg.type == 'ai']
                        if ai_messages:
                            ai_message = ai_messages[-1].content
                            print(f"DEBUG: Found AI message in {node_name}: {ai_message[:100]}...")
                            break
            
            if not ai_message:
                print("DEBUG: No AI message found in any node")
            
            return JSONResponse({
                "image_report": image_report,
                "materials": materials,
                "ai_message": ai_message,
                "session_id": session_id
            })
        else:
            return JSONResponse({
                "image_report": image_report,
                "materials": materials,
                "session_id": session_id
            })
    except Exception as e:
        return JSONResponse({"error": f"Image analysis failed: {e}"}, status_code=500)
    finally:
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)

# --- Main Entry Point ---
if __name__ == "__main__":
    Path("sessions").mkdir(exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)
