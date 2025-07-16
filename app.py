import os
import asyncio
import uuid
import base64
import re
from typing import Dict, Any, cast
from flask import Flask, request, jsonify, render_template
import nest_asyncio
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Enable nested asyncio support for running async functions in Flask
nest_asyncio.apply()

# Import the ReAct agent graph and other necessary modules
from react_agent.graph import graph, State
from react_agent.configuration import Configuration
from react_agent.prompts import SYSTEM_PROMPT
from react_agent.tools import material_price_query, search, get_historical_image_report
from react_agent.vision import get_gemini_vision_report
from react_agent.memory import memory_manager

# Initialize Flask app
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'

# Create directories
os.makedirs('templates', exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Store customizable prompts and descriptions
custom_system_prompt = SYSTEM_PROMPT
tool_descriptions = {
    "material_price_query": material_price_query.__doc__ or "Query for material price information",
    "search": search.__doc__ or "Search for general web results",
    "get_historical_image_report": get_historical_image_report.__doc__ or "Get a past image analysis report"
}

def prune_history_for_model(history: list, max_pairs: int) -> list:
    """
    Prunes the history to the last `max_pairs` of user/AI interactions.
    An interaction starts with a HumanMessage.
    """
    if not history:
        return []

    # Prune to the last N user messages
    human_indices = [i for i, msg in enumerate(history) if isinstance(msg, HumanMessage)]
    
    if len(human_indices) <= max_pairs:
        # No pruning needed for length, just return the original history
        return history
    
    # Get the index of the n-th last HumanMessage
    start_index = human_indices[-max_pairs]
    pruned_history = history[start_index:]
    return pruned_history

def run_async(coroutine):
    """Helper function to run async functions in Flask."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coroutine)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/query', methods=['POST'])
def query_agent():
    user_query = request.form.get('query', '')
    image_file = request.files.get('image')
    # Lấy message_id từ request nếu có
    message_id = request.form.get('message_id')

    if not user_query and not image_file:
        return jsonify({'error': 'No query or image provided'}), 400
    
    data = request.form
    model = data.get('model', 'qwen3:30b')
    conversation_id = data.get('conversation_id') or str(uuid.uuid4())
    
    try:
        # 1. Get the full, original history from memory and prune it for the model
        original_history = memory_manager.get_history(conversation_id)
        pruned_history = prune_history_for_model(original_history, 3)

        # 2. Prepare the messages for the graph, starting with the pruned history
        # Chỉ giữ lại các HumanMessage, AIMessage cho history, và xử lý riêng image report
        filtered_history = []
        image_report_msg = None
        for msg in pruned_history:
            if isinstance(msg, SystemMessage) and '[IMAGE REPORT]:' in str(msg.content):
                image_report_msg = msg
            elif isinstance(msg, (HumanMessage, AIMessage)):
                filtered_history.append(msg)
        
        # Khởi tạo danh sách messages để gửi đến graph
        messages_to_graph = []
        messages_to_graph.extend(filtered_history)  # Đầu tiên là history
        messages_to_save_this_turn = []
        report_str = "[IMAGE REPORT]:"
        new_report_str = "[IMAGE REPORT]:"

        # 3. If a new image is uploaded, remove any old vision reports from the context
        if image_file:
            # Xóa image report cũ nếu có
            if image_report_msg:
                image_report_msg = None
            
            # And create a new vision report
            vision_prompt = ("""
Nhiệm vụ: Phân tích và phân loại vật liệu thi công từ ảnh nội thất.

Danh mục vật liệu:
    1. Wood: Oak, Walnut, Ash, Xoan đào, Ván ghép thanh, MDF, Plywood
    2. Wallpaper: Floral, Stripes, Plain / Texture, Geometric, Classic / Vintage, Nature / Scenic, Material Imitation
    3. Stone: Marble, Granite, Onyx, Quartz
    4. Paint: Color paint, Texture effect paint
Mục tiêu:
- Phân loại rõ Tường, Sàn, Trần nếu thấy trong ảnh.
- Mapping rõ Material (Gỗ, Đá, Sơn, Giấy dán tường) và Type cụ thể (Oak, Walnut, Marble, Sơn màu, …).
- Cố gắng mapping theo các vật liệu trong danh mục vật liệu, nếu khác hoàn toàn thì material là null.
- Nếu không rõ loại cụ thể, ghi “null” và “Trong dataset: false”.
- Luôn mô tả đủ 3 tường chính và 1 tường phán đoán nếu thiếu.
- Nếu là ảnh nội thất, không cần mô tả.
Position bao gồm: Tường bên trái, Tường bên phải, Tường đối diện, Tường sau lưng.
Nếu không phải ảnh nội thất, chỉ trả về:
    Nội thất: false
    Mô tả hình ảnh: (mô tả chi tiết hình ảnh)
    Nếu không khớp danh mục, ghi “null” và “Trong dataset: false”.
Quy tắc gộp
    Nếu nhiều vị trí có cùng Material và Type, gộp lại thành 1 dòng, liệt kê Position phân tách dấu phẩy:
    Material: [Material] - Type: [Type] - Position: Tường bên trái, Tường bên phải.
    Luôn đảm bảo đủ 4 tường (tường sau lưng có thể là phán đoán).
Định dạng trả về:
Interior: true/false
Material: ... - Type: ... - Position: Tường bên trái, Tường đối diện, Sàn
Material: ... - Type: ... - Position: Tường bên phải, Trần, Tường sau lưng.
...
Nếu không phải ảnh nội thất:
Nội thất: false
Mô tả: (mô tả chi tiết hình ảnh)
            """)
            image_bytes = image_file.read()
            gemini_report = get_gemini_vision_report(image_bytes, vision_prompt)
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            user_input = user_query if user_query else "Báo giá các vật liệu có trong hình ảnh."
            user_message = HumanMessage(content=user_input)
            
            # Sử dụng message_id từ frontend hoặc tạo mới
            if message_id:
                user_message.id = message_id
            else:
                user_message.id = str(uuid.uuid4())
                
            # Thay đổi định dạng IMAGE REPORT để làm rõ nguồn gốc
            report_message = SystemMessage(content=f"[IMAGE REPORT]:\n{gemini_report}")
            
            # Lưu hình ảnh vào context và liên kết với tin nhắn cụ thể
            memory_manager.add_image_context(conversation_id, image_base64, gemini_report, user_message.id)
            
            # Thêm report message vào sau history và trước câu hỏi hiện tại
            messages_to_graph.append(report_message)
            messages_to_graph.append(user_message)
            
            messages_to_save_this_turn.extend([user_message, report_message])
        else:
            # Nếu có image report cũ, thêm vào sau history và trước câu hỏi hiện tại
            if image_report_msg:
                # Cập nhật định dạng của image report cũ nếu cần
                if isinstance(image_report_msg.content, str) and report_str in image_report_msg.content:
                    # Thay đổi định dạng từ cũ sang mới
                    updated_content = image_report_msg.content.replace(report_str, new_report_str)
                    image_report_msg = SystemMessage(content=updated_content)
                
                messages_to_graph.append(image_report_msg)
            
            # Thêm câu hỏi hiện tại vào cuối cùng
            user_message = HumanMessage(content=user_query)
            # Thêm ID cho tin nhắn nếu không có
            if not hasattr(user_message, "id") or not user_message.id:
                user_message.id = message_id or str(uuid.uuid4())
            messages_to_graph.append(user_message)
            messages_to_save_this_turn.append(user_message)

        # 4. Clean out <think> blocks from AI messages in the history before sending to graph
        think_regex = re.compile(r"<think>.*?</think>", re.DOTALL)
        cleaned_messages_for_graph = []
        for msg in messages_to_graph:
            if isinstance(msg, AIMessage) and isinstance(msg.content, str):
                cleaned_content = think_regex.sub("", msg.content).strip()
                cleaned_msg = AIMessage(content=cleaned_content, id=msg.id, tool_calls=msg.tool_calls)
                cleaned_messages_for_graph.append(cleaned_msg)
            else:
                cleaned_messages_for_graph.append(msg)

        # 5. Invoke the agent graph with the full, cleaned history
        input_data = cast(State, {"messages": cleaned_messages_for_graph, "conversation_id": conversation_id})
        system_prompt_formatted = custom_system_prompt.format(
            conversation_id=conversation_id,
            system_time=datetime.now(timezone.utc).isoformat()
        )
        config: RunnableConfig = {"configurable": {"model": model, "system_prompt": system_prompt_formatted}}
        response = run_async(graph.ainvoke(input_data, config=config))
        
        # 6. Save the new messages to memory
        new_messages_from_graph = response["messages"][len(cleaned_messages_for_graph):]
        messages_to_save_this_turn.extend(new_messages_from_graph)
        memory_manager.add_messages(conversation_id, messages_to_save_this_turn)

        # 7. Prepare the final response: clean up the last AI message
        ai_message = response["messages"][-1]
        
        # Remove any tool call representations from the final content
        if isinstance(ai_message.content, str):
            # General cleanup of residual tool call syntax that might leak
            tool_call_pattern = re.compile(r'Tool Calls:.*', re.DOTALL)
            ai_message.content = tool_call_pattern.sub('', ai_message.content).strip()

        tool_calls = []
        # The tool_calls attribute is still preserved for the UI if needed
        if isinstance(ai_message, AIMessage) and ai_message.tool_calls:
            for tool_call in ai_message.tool_calls:
                tool_calls.append({
                    'tool': tool_call.get('name', 'unknown'),
                    'args': tool_call.get('args', {})
                })
        
        final_history = memory_manager.get_history_serializable(conversation_id)
        return jsonify({
            'response': ai_message.content,
            'tool_calls': tool_calls,
            'conversation_id': conversation_id,
            'history': final_history
        })
        
    except Exception as e:
        app.logger.error(f"Error in /api/query: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    return jsonify(memory_manager.list_sessions())

@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session_history(session_id):
    history = memory_manager.get_history_serializable(session_id)
    
    # Get session metadata
    sessions = memory_manager.list_sessions()
    session_info = next((s for s in sessions if s["id"] == session_id), None)
    
    return jsonify({
        "history": history,
        "metadata": session_info
    })

@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    memory_manager.clear_history(session_id)
    return jsonify({'message': f'Session {session_id} cleared successfully.'})

@app.route('/api/sessions/<session_id>', methods=['PATCH'])
def update_session(session_id):
    data = request.get_json(silent=True) or {}
    
    if 'name' in data:
        success = memory_manager.rename_session(session_id, data['name'])
        if success:
            return jsonify({'message': f'Session renamed to {data["name"]}'})
        else:
            return jsonify({'error': f'Session {session_id} not found'}), 404
    
    return jsonify({'error': 'No valid update parameters provided'}), 400

@app.route('/api/models', methods=['GET'])
def list_models():
    """API endpoint to list available models."""
    models = [{'id': 'ollama/qwen3:30b', 'name': 'qwen3:30b'}]
    return jsonify(models)

@app.route('/api/system-prompt', methods=['GET'])
def get_system_prompt():
    """Get the current system prompt."""
    global custom_system_prompt
    return jsonify({'system_prompt': custom_system_prompt, 'is_default': custom_system_prompt == SYSTEM_PROMPT})

@app.route('/api/system-prompt', methods=['POST'])
def update_system_prompt():
    global custom_system_prompt
    data = request.get_json(silent=True) or {}
    
    if data.get('reset'):
        custom_system_prompt = SYSTEM_PROMPT
        return jsonify({'message': 'System prompt reset to default', 'system_prompt': custom_system_prompt, 'is_default': True})
    
    new_prompt = data.get('system_prompt')
    if new_prompt is None:
         return jsonify({'error': 'No system prompt provided in payload'}), 400

    custom_system_prompt = new_prompt
    return jsonify({'message': 'System prompt updated', 'system_prompt': custom_system_prompt, 'is_default': custom_system_prompt == SYSTEM_PROMPT})

@app.route('/api/tool-descriptions', methods=['GET'])
def get_tool_descriptions():
    """Get the current tool descriptions."""
    global tool_descriptions
    return jsonify({
        'tool_descriptions': tool_descriptions,
        'default_descriptions': {
            "material_price_query": material_price_query.__doc__ or "Query for material price information",
            "search": search.__doc__ or "Search for general web results"
        }
    })

@app.route('/api/tool-descriptions', methods=['POST'])
def update_tool_descriptions():
    global tool_descriptions
    data = request.get_json(silent=True) or {}
    
    if data.get('reset'):
         tool_descriptions = {
            "material_price_query": material_price_query.__doc__ or "Query for material price information",
            "search": search.__doc__ or "Search for general web results"
        }
         return jsonify({'message': 'Tool descriptions reset to default', 'tool_descriptions': tool_descriptions})

    new_descriptions = data.get('tool_descriptions')
    if not new_descriptions:
        return jsonify({'error': 'No tool descriptions provided'}), 400
    
    tool_descriptions.update(new_descriptions)
    return jsonify({'message': 'Tool descriptions updated', 'tool_descriptions': tool_descriptions})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 