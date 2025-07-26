import base64
import json
import uuid
import os
import re # Import regex module
import datetime
import time
from flask import Flask, render_template, request, session, jsonify
from flask_session import Session

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from react_agent.graph import graph
from react_agent.vision import get_gemini_vision_report
from react_agent.tools import get_available_materials_string
from react_agent.prompts import VISION_PROMPT

def cleanup_temp_files():
    """Dọn dẹp các file tạm thời trong thư mục uploads khi khởi động."""
    uploads_dir = 'uploads'
    
    # Nếu thư mục không tồn tại, không cần dọn dẹp
    if not os.path.exists(uploads_dir):
        return
    
    # Dọn dẹp các file trong danh sách cần xóa
    cleanup_list_file = os.path.join(uploads_dir, 'to_cleanup', 'files_to_delete.txt')
    if os.path.exists(cleanup_list_file):
        try:
            with open(cleanup_list_file, 'r') as f:
                files_to_delete = f.readlines()
            
            # Xóa các file trong danh sách
            for file_path in files_to_delete:
                file_path = file_path.strip()
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"Cleaned up file: {file_path}")
                    except Exception as e:
                        print(f"Could not delete {file_path}: {e}")
            
            # Xóa danh sách sau khi xử lý
            os.remove(cleanup_list_file)
        except Exception as e:
            print(f"Error cleaning up files: {e}")
    
    # Xóa tất cả các file tạm thời cũ hơn 1 giờ
    cutoff_time = time.time() - 3600  # 1 giờ = 3600 giây
    
    for filename in os.listdir(uploads_dir):
        if filename == 'to_cleanup':
            continue
            
        file_path = os.path.join(uploads_dir, filename)
        # Chỉ xử lý các file, không phải thư mục
        if os.path.isfile(file_path):
            # Kiểm tra thời gian tạo file
            file_creation_time = os.path.getctime(file_path)
            if file_creation_time < cutoff_time:
                try:
                    os.remove(file_path)
                    print(f"Removed old temp file: {file_path}")
                except Exception as e:
                    print(f"Could not remove old temp file {file_path}: {e}")

# --- App Initialization ---
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
app.config["SESSION_TYPE"] = "filesystem"
app.config['SESSION_FILE_DIR'] = './flask_session/'
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
Session(app)

# Run cleanup at startup
cleanup_temp_files()

# Global state tracking (cho debugging)
# current_state = {
#     'current_node': 'idle',
#     'route': None,
#     'tool': None,
#     'status': 'idle',
#     'logs': []
# }

# def update_state(node=None, route=None, tool=None, status=None, log=None):
#     """Cập nhật state hiện tại và lưu log"""
#     global current_state
#     if node:
#         current_state['current_node'] = node
#     if route:
#         current_state['route'] = route
#     if tool:
#         current_state['tool'] = tool
#     if status:
#         current_state['status'] = status
#     if log:
#         timestamp = datetime.datetime.now().strftime("%H:%M:%S")
#         current_state['logs'].insert(0, f"[{timestamp}] {log}")
#         # Giữ tối đa 10 log entries
#         if len(current_state['logs']) > 10:
#             current_state['logs'] = current_state['logs'][:10]

def preprocess_user_input(message: str) -> str:
    """
    Phát hiện kích thước phòng từ input của người dùng và tự động tính diện tích các bề mặt.
    Hỗ trợ phát hiện linh hoạt các kích thước (dài, rộng, cao) ngay cả khi chỉ cung cấp một hoặc hai kích thước.
    
    Args:
        message: Input từ người dùng
        
    Returns:
        Chuỗi đã được xử lý, có thể bao gồm thông tin diện tích
    """
    # Tìm các kích thước riêng lẻ
    length_pattern = r'dài\s+(\d+(?:\.\d+)?)\s*m'
    width_pattern = r'rộng\s+(\d+(?:\.\d+)?)\s*m'
    height_pattern = r'cao\s+(\d+(?:\.\d+)?)\s*m'
    
    # Pattern cho định dạng XxYxZ
    xyz_pattern = r'(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)'
    
    # Pattern cho định dạng XxY (chỉ dài và rộng)
    xy_pattern = r'(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\b(?!\s*[xX×])'
    
    # Tìm kiếm các kích thước
    length_match = re.search(length_pattern, message, re.IGNORECASE)
    width_match = re.search(width_pattern, message, re.IGNORECASE)
    height_match = re.search(height_pattern, message, re.IGNORECASE)
    xyz_match = re.search(xyz_pattern, message, re.IGNORECASE)
    xy_match = re.search(xy_pattern, message, re.IGNORECASE)
    
    # Giá trị mặc định
    length = None
    width = None
    height = None
    
    # Ưu tiên định dạng XxYxZ
    if xyz_match:
        length = float(xyz_match.group(1))
        width = float(xyz_match.group(2))
        height = float(xyz_match.group(3))
        print(f"Detected XxYxZ format: {length}x{width}x{height}")
    # Nếu không có XxYxZ, thử định dạng XxY
    elif xy_match:
        length = float(xy_match.group(1))
        width = float(xy_match.group(2))
        # Giả định chiều cao mặc định
        height = 2.7  # Chiều cao trung bình của phòng
        print(f"Detected XxY format: {length}x{width}, using default height: {height}")
    # Nếu không có cả hai, thử tìm các kích thước riêng lẻ
    else:
        if length_match:
            length = float(length_match.group(1))
        if width_match:
            width = float(width_match.group(1))
        if height_match:
            height = float(height_match.group(1))
        
        # Nếu thiếu kích thước, sử dụng giá trị mặc định hoặc suy luận
        if length is not None and width is None and height is None:
            # Nếu chỉ có chiều dài, giả định đó là diện tích sàn hình vuông
            width = length
            height = 2.7  # Chiều cao trung bình
            print(f"Only length provided: {length}m. Assuming square room with width={width}m, height={height}m")
        elif length is not None and width is not None and height is None:
            # Nếu có chiều dài và rộng, giả định chiều cao trung bình
            height = 2.7
            print(f"Length and width provided: {length}x{width}m. Using default height: {height}m")
        elif length is None or width is None:
            # Không đủ thông tin để tính toán
            return message
    
    # Nếu không tìm thấy đủ thông tin, trả về nguyên bản
    if length is None or width is None or height is None:
        return message
    
    # Tính diện tích các bề mặt
    floor_area = length * width
    ceiling_area = floor_area
    wall1_area = length * height  # Tường 1 (dài x cao)
    wall2_area = length * height  # Tường 2 (đối diện tường 1)
    wall3_area = width * height   # Tường 3 (rộng x cao)
    wall4_area = width * height   # Tường 4 (đối diện tường 3)
    total_wall_area = 2 * (length + width) * height
    
    # Tạo thông tin diện tích
    area_info = (
        f"{message}\n\n"
        f"- Diện tích sàn: {floor_area}m²\n"
        f"- Diện tích trần: {ceiling_area}m²\n"
        f"- Diện tích tường 1: {wall1_area}m²\n"
        f"- Diện tích tường 2: {wall1_area}m²\n"
        f"- Diện tích tường 3: {wall3_area}m²\n"
        f"- Diện tích tường 4: {wall3_area}m²\n"
    )
    
    print(f"Calculated areas: floor={floor_area}m², walls={total_wall_area}m²")
    
    return area_info

@app.route('/api/state', methods=['GET'])
def get_current_state():
    """Return current processing state for the session."""
    graph_state = session.get('graph_state', {
        'nodes': {},
        'status': 'idle',
    })
    return jsonify(graph_state)

# --- Constants ---
# IMAGE_ANALYSIS_PROMPT_TEMPLATE is now imported from prompts.py
SESSION_HISTORY_PATH = './chat_sessions/'
os.makedirs(SESSION_HISTORY_PATH, exist_ok=True)

# --- Helper Functions ---
def parse_thought_and_response(raw_response: str) -> dict:
    """Parses a raw response to separate the <think> block from the display response."""
    thought_match = re.search(r"<think>(.*?)</think>", raw_response, re.DOTALL)
    
    if thought_match:
        thought = thought_match.group(1).strip()
        # The display response is everything after the </think> tag
        display_response = raw_response[thought_match.end():].strip()
        return {"response": display_response, "thought": thought}
    else:
        # No think block found, the whole thing is the response
        return {"response": raw_response, "thought": None}

# --- Session Management ---
def get_session_id():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def save_session_history(session_id, history):
    with open(os.path.join(SESSION_HISTORY_PATH, f"{session_id}.json"), 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_session_history(session_id):
    history_file = os.path.join(SESSION_HISTORY_PATH, f"{session_id}.json")
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

# --- Context Management ---
def prune_history(history: list) -> list:
    """
    Prunes history but ensures important SystemMessages (like image reports and quote parameters) are kept.
    
    Args:
        history: List of message dictionaries from session history
        
    Returns:
        List of BaseMessage objects for the graph
    """
    if not history: 
        return []
    
    # Convert to LangChain message objects
    messages = []
    for msg in history:
        if msg['type'] == 'ai':
            messages.append(AIMessage(**msg))
        elif msg['type'] == 'human':
            messages.append(HumanMessage(**msg))
        elif msg['type'] == 'system':
            messages.append(SystemMessage(**msg))
    
    # If we have fewer than 5 human messages, keep everything
    human_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
    if len(human_messages) <= 5:
        return messages
    
    # Otherwise, keep the last 5 human messages and their context
    human_indices = [i for i, msg in enumerate(messages) if isinstance(msg, HumanMessage)]
    last_five_start = human_indices[-5]
    
    # Always keep important SystemMessages regardless of position
    important_system_messages = []
    for i, msg in enumerate(messages):
        if i < last_five_start and isinstance(msg, SystemMessage):
            content = msg.content
            # Keep image reports and quote parameters
            if "[Image Analysis Report]:" in content or "[Quote Parameters]:" in content:
                important_system_messages.append(msg)
                print(f"Keeping important SystemMessage: {content[:50]}...")
    
    # Return important SystemMessages + last 5 human messages and their context
    return important_system_messages + messages[last_five_start:]

# --- API Routes ---
@app.route('/')
def index():
    # Priority 1: Get session_id from URL parameter for loading shared/old sessions
    session_id_from_url = request.args.get('session_id')
    
    if session_id_from_url:
        # If a specific session is requested via URL, use it and set it in the session cookie
        session['session_id'] = session_id_from_url
        current_session_id = session_id_from_url
    else:
        # Priority 2: Use the existing session from cookie or create a new one
        current_session_id = get_session_id()

    history = load_session_history(current_session_id)
    
    # Convert message dicts to LangChain message objects for the template if needed
    # (Assuming template can handle dicts with 'type' and 'content' keys)
    
    return render_template('index.html', history=history, session_id=current_session_id)

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    sessions = []
    for filename in os.listdir(SESSION_HISTORY_PATH):
        if filename.endswith(".json"):
            session_id = filename[:-5]
            history = load_session_history(session_id)
            first_human_message = next((m['content'] for m in history if m['type'] == 'human'), 'New Chat')
            sessions.append({"id": session_id, "title": first_human_message[:50]})
    return jsonify(sorted(sessions, key=lambda s: os.path.getmtime(os.path.join(SESSION_HISTORY_PATH, f"{s['id']}.json")), reverse=True))

@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session_history(session_id):
    history = load_session_history(session_id)
    return jsonify(history)

@app.route('/api/new_session', methods=['POST'])
def new_session():
    """Tạo session mới bằng cách xóa session_id hiện tại"""
    # Xóa session_id hiện tại để Flask sẽ tạo một cái mới
    if 'session_id' in session:
        session.pop('session_id')
    
    # Tạo và lưu session ID mới
    new_session_id = str(uuid.uuid4())
    session['session_id'] = new_session_id
    
    # Tạo history trống cho session mới
    save_session_history(new_session_id, [])
    
    return jsonify({"success": True, "session_id": new_session_id})

@app.route('/api/chat', methods=['POST'])
async def chat():
    session_id = get_session_id()

    # Reset or initialize graph state for the new request
    session['graph_state'] = {'nodes': {}, 'status': 'running'}
    session.modified = True

    try:
        is_json = request.is_json
        data = request.json if is_json else request.form
        
        message = data.get('message', '')
        image_file = request.files.get('file')
        
        if not message and not image_file:
            return jsonify({"error": "Message or image must be provided."}), 400
        
        print(f"Processing chat request with session_id: {session_id}")

        # Load message history
        messages_json = load_session_history(session_id)
        
        # Handle image if provided
        if image_file:
            temp_image_path = None
            try:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
                
                # Tạo file tạm thời với tên UUID để tránh trùng lặp
                temp_image_path = os.path.join('uploads', f"{session_id}_{uuid.uuid4()}.jpg")
                os.makedirs('uploads', exist_ok=True)
                
                # Ghi file
                with open(temp_image_path, 'wb') as f:
                    f.write(base64.b64decode(image_data))
                
                # Gọi API Vision
                image_report = await get_gemini_vision_report(temp_image_path, prompt=VISION_PROMPT)
                
                if image_report:
                    # Add the image report as a SystemMessage
                    image_system_message = {"type": "system", "content": f"[Image Analysis Report]:\n{image_report}"}
                    messages_json.append(image_system_message)
                    print(f"Added image report to history: {image_report[:100]}...")
                    
                    if not message:
                        message = "Analyze the materials in the image and provide a quote."

            except Exception as e:
                # Ghi lại lỗi chi tiết
                import traceback
                print(f"Error processing image: {e}")
                print(traceback.format_exc())
                return jsonify({"error": f"Image analysis failed: {e}"}), 500
            finally:
                # Xử lý việc xóa file một cách an toàn
                if temp_image_path and os.path.exists(temp_image_path):
                    try:
                        # Thử xóa file
                        os.remove(temp_image_path)
                    except PermissionError:
                        # Nếu không xóa được, đánh dấu file để dọn dẹp sau
                        print(f"Could not delete file {temp_image_path}, will clean up later.")
                        # Tạo thư mục để lưu các file cần dọn dẹp
                        cleanup_dir = os.path.join('uploads', 'to_cleanup')
                        os.makedirs(cleanup_dir, exist_ok=True)
                        # Thêm file vào danh sách dọn dẹp sau
                        with open(os.path.join(cleanup_dir, 'files_to_delete.txt'), 'a') as f:
                            f.write(f"{temp_image_path}\n")

        # Preprocess user input to detect room dimensions and calculate areas
        processed_message = preprocess_user_input(message)
        
        # Append human message
        messages_json.append({"type": "human", "content": processed_message})
        
        # Convert JSON messages to LangChain message objects
        messages_for_graph = []
        for msg in messages_json:
            if msg["type"] == "human":
                messages_for_graph.append(HumanMessage(content=msg["content"]))
            elif msg["type"] == "ai":
                messages_for_graph.append(AIMessage(content=msg["content"]))
            elif msg["type"] == "system":
                messages_for_graph.append(SystemMessage(content=msg["content"]))
        
        # Load area_map from session if it exists
        area_map = session.get('area_map', None)
        initial_state = {"messages": messages_for_graph, "area_map": area_map}
        
        # Execute the graph and stream updates
        final_state = None
        async for output in graph.astream(initial_state):
            node_name = list(output.keys())[0]
            node_output = output[node_name]
            
            print(f"--- Just ran node: {node_name} ---")
            
            # Sanitize output for session storage and visualization
            sanitized_output = {}
            if node_name == "history_summarizer":
                sanitized_output['Summary'] = node_output.get('history_summary', 'N/A')
            elif node_name == "strategist_router":
                sanitized_output['Decision'] = node_output.get('decision', 'N/A')
                sanitized_output['Reason'] = node_output.get('response_reason')
                sanitized_output['Task'] = node_output.get('task_description')
            elif node_name == "executor_agent":
                tool_results = node_output.get('tool_results', 'N/A')
                # Truncate long tool results for display
                summary = tool_results[:250] + '...' if isinstance(tool_results, str) and len(tool_results) > 250 else tool_results
                sanitized_output['Tool Results Summary'] = summary
            elif node_name == "final_responder":
                sanitized_output['Status'] = 'Generated final response.'

            if 'graph_state' in session:
                session['graph_state']['nodes'][node_name] = {
                    'status': 'completed',
                    'output': {k: v for k, v in sanitized_output.items() if v is not None} # Clean None values
                }
                session.modified = True

            final_state = node_output
        
        # Persist area_map for next turn
        if final_state and final_state.get('area_map'):
            session['area_map'] = final_state.get('area_map')

        # Mark graph as finished
        if 'graph_state' in session:
            session['graph_state']['status'] = 'finished'
            session.modified = True
        
        result = final_state
        
        if result and isinstance(result, dict) and result.get("messages"):
            all_messages = result["messages"]
            
            # Find the last AI message for the response
            ai_messages = [msg for msg in all_messages if isinstance(msg, AIMessage)]
            if ai_messages:
                assistant_response = ai_messages[-1].content
            else:
                assistant_response = "Sorry, I encountered an issue and couldn't process your request."

            # Save ALL messages to history, including SystemMessages
            updated_messages_json = []
            for msg in all_messages:
                if isinstance(msg, HumanMessage):
                    updated_messages_json.append({"type": "human", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    updated_messages_json.append({"type": "ai", "content": msg.content})
                elif isinstance(msg, SystemMessage):
                    updated_messages_json.append({"type": "system", "content": msg.content})
            
            # Log the number of messages by type
            human_count = sum(1 for msg in updated_messages_json if msg["type"] == "human")
            ai_count = sum(1 for msg in updated_messages_json if msg["type"] == "ai")
            system_count = sum(1 for msg in updated_messages_json if msg["type"] == "system")
            print(f"Saving history with {human_count} human, {ai_count} AI, and {system_count} system messages")

            # Save the updated history
            save_session_history(session_id, updated_messages_json)

            return jsonify(parse_thought_and_response(assistant_response))
        else:
            return jsonify({"error": "No response from agent"}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000) 