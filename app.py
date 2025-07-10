import os
import asyncio
import uuid
import base64
import re
from typing import Dict, Any
from flask import Flask, request, jsonify, render_template
import nest_asyncio
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Enable nested asyncio support for running async functions in Flask
nest_asyncio.apply()

# Import the ReAct agent graph and other necessary modules
from react_agent.graph import graph
from react_agent.configuration import Configuration
from react_agent.prompts import SYSTEM_PROMPT
from react_agent.tools import material_price_query, search
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
    "search": search.__doc__ or "Search for general web results"
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

    if not user_query and not image_file:
        return jsonify({'error': 'No query or image provided'}), 400
    
    data = request.form
    model = data.get('model', 'ollama/qwen3:30b-a3b')
    conversation_id = data.get('conversation_id') or str(uuid.uuid4())
    
    try:
        # 1. Get the full, original history from memory and prune it for the model
        original_history = memory_manager.get_history(conversation_id)
        pruned_history = prune_history_for_model(original_history, 3)

        # 2. Prepare the messages for the graph, starting with the pruned history
        # Chỉ giữ lại [IMAGE REPORT]: nếu có, và các HumanMessage, AIMessage
        image_report_msg = None
        filtered_history = []
        for msg in pruned_history:
            if isinstance(msg, SystemMessage) and '[IMAGE REPORT]:' in str(msg.content):
                image_report_msg = msg
            elif isinstance(msg, (HumanMessage, AIMessage)):
                filtered_history.append(msg)
        messages_to_graph = []
        if image_report_msg:
            messages_to_graph.append(image_report_msg)
        messages_to_graph.extend(filtered_history)
        messages_to_save_this_turn = []
        report_str = "[IMAGE REPORT]:"

        # 3. If a new image is uploaded, remove any old vision reports from the context
        if image_file:
            messages_to_graph = [msg for msg in messages_to_graph if not (isinstance(msg, SystemMessage) and report_str in msg.content)]
            
            # And create a new vision report
            vision_prompt = (
                "Mô tả các vật liệu được sử dụng ở tường, sàn trong hình ảnh vào vật liệu của nội thất. Nếu không phải ảnh nội thất, vẫn mô tả hình ảnh nhưng nói rõ ảnh có vẻ không liên quan đến nội thất."
                "Ví dụ: Ảnh có 1 tường làm bằng gỗ (có vẻ là gỗ sồi), 2 tường bằng đá (có vẻ là marble), sàn nhà làm bằng gỗ (không xác định cụ thể)"
                "Trả lời giống như ví dụ, không nói gì thêm."
                "Lưu ý: Thạch cao và Sơn là 2 loại khác nhau, phân biệt rõ ràng."
                "Đối với các vật liệu mà trong hình có như gỗ, đá, sơn, giấy dán tường thì thêm dòng 'hãy sử dụng tool material_price_query để tra cứu giá các vật liệu gỗ, đá, sơn, giấy dán tường. Nói rõ vật liệu nào dùng cho tường hay sàn' (tương ứng với các vật liệu có trong ảnh, nếu không có thì không cần nói)"
            )
            image_bytes = image_file.read()
            gemini_report = get_gemini_vision_report(image_bytes, vision_prompt)
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            memory_manager.add_image_context(conversation_id, image_base64, gemini_report)
            
            user_input = user_query if user_query else "Báo giá các vật liệu có trong hình ảnh."
            user_message = HumanMessage(content=user_input)
            report_message = SystemMessage(content=f"[IMAGE REPORT]:\n{gemini_report}")
            
            messages_to_graph.extend([user_message, report_message])
            messages_to_save_this_turn.extend([user_message, report_message])
        else:
            user_message = HumanMessage(content=user_query)
            messages_to_graph.append(user_message)
            messages_to_save_this_turn.append(user_message)

        # 4. Clean out <think> blocks from AI messages in the history
        think_regex = re.compile(r"<think>.*?</think>", re.DOTALL)
        ai_prefix_regex = re.compile(r"\[AI\]:.*?(\n|$)", re.DOTALL)
        tool_calls_regex = re.compile(r"Tool Calls: \[.*?\]", re.DOTALL)
        cleaned_messages_to_graph = []
        for msg in messages_to_graph:
            if isinstance(msg, AIMessage) and isinstance(msg.content, str):
                cleaned_content = think_regex.sub("", msg.content).strip()
                cleaned_content = ai_prefix_regex.sub("", cleaned_content).strip()
                cleaned_content = tool_calls_regex.sub("", cleaned_content).strip()
                # Create a new message with the cleaned content
                cleaned_msg = AIMessage(content=cleaned_content, id=msg.id, tool_calls=msg.tool_calls)
                cleaned_messages_to_graph.append(cleaned_msg)
            else:
                cleaned_messages_to_graph.append(msg)
        messages_to_graph = cleaned_messages_to_graph

        # 5. Invoke the agent graph
        input_data = {"messages": messages_to_graph, "conversation_id": conversation_id}
        system_prompt_formatted = custom_system_prompt.format(
            conversation_id=conversation_id,
            system_time=datetime.now(timezone.utc).isoformat()
        )
        config = {"configurable": {"model": model, "system_prompt": system_prompt_formatted}}
        response = run_async(graph.ainvoke(input_data, config=config))
        
        # 6. Save the new messages to memory
        new_messages_from_graph = response["messages"][len(messages_to_graph):]
        messages_to_save_this_turn.extend(new_messages_from_graph)
        memory_manager.add_messages(conversation_id, messages_to_save_this_turn)

        # 7. Prepare the final response for the UI
        ai_message = response["messages"][-1]
        tool_calls = []
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
    return jsonify(history)

@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    memory_manager.clear_history(session_id)
    return jsonify({'message': f'Session {session_id} cleared successfully.'})

@app.route('/api/models', methods=['GET'])
def list_models():
    """API endpoint to list available models."""
    models = [{'id': 'ollama/qwen3:30b-a3b', 'name': 'Qwen3 30B'}]
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