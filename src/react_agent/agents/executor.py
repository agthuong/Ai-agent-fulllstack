"""Executor agent for the AI interior design quotation system."""

import json
from typing import Dict, Any, List

from ..new_tools import execute_tool, TOOLS
from .planner import MODELS

async def _convert_subtask_to_tool_call(subtask: str, history_summary: str, user_input: str, previous_results: List[Any]) -> Dict[str, Any]:
    """Converts a natural language subtask to a tool call."""
    # Create a prompt for the LLM to convert the subtask to a tool call
    tools_description = "\n".join([f"- {name}: {tool.__doc__}" for name, tool in TOOLS.items()])
    
    prompt = f"""<system>
Bạn là một AI chuyên gia chuyển đổi các subtask bằng ngôn ngữ tự nhiên thành các lệnh gọi công cụ cụ thể.

## Công cụ có sẵn
{tools_description}

## Bối cảnh
- **Lịch sử tóm tắt:** {history_summary}
- **Yêu cầu cuối cùng của người dùng:** {user_input}
- **Subtask cần chuyển đổi:** {subtask}

## Nhiệm vụ của bạn
Dựa trên bối cảnh và subtask, hãy tạo ra một lệnh gọi công cụ phù hợp.
- Chỉ trả về một đối tượng JSON DUY NHẤT chứa các khóa "name" và "args".
- Nếu không có công cụ nào phù hợp, hãy trả về một đối tượng rỗng {{}}.

### Ví dụ 1: Lấy giá nội bộ
```json
{{
  "name": "get_internal_price",
  "args": {{ "category": "Sàn", "material_type": "Sàn gỗ" }}
}}
```

### Ví dụ 2: Tìm giá thị trường
```json
{{
  "name": "get_market_price",
  "args": {{ "material": "gỗ" }}
}}
```

### Ví dụ 3: Phân tích báo cáo hình ảnh
```json
{{
  "name": "generate_quote_from_image",
  "args": {{ "image_report": "Material: gỗ - Type: null - Position: sàn - InStock: only_material\nMaterial: đá - ..." }}
}}
```
/no_think"""
    
    llm = MODELS["LLM_PLANNER"]
    response = await llm.ainvoke(prompt)
    raw_response_text = response.content
    print(f"LLM Raw Response for Subtask Conversion: {raw_response_text}")
    
    try:
        valid_json_strings = []
        start_index = 0
        while start_index < len(raw_response_text):
            first_brace = raw_response_text.find('{', start_index)
            if first_brace == -1:
                break

            brace_level = 1
            for i in range(first_brace + 1, len(raw_response_text)):
                char = raw_response_text[i]
                if char == '{':
                    brace_level += 1
                elif char == '}':
                    brace_level -= 1
                    if brace_level == 0:
                        potential_json = raw_response_text[first_brace:i + 1]
                        try:
                            json.loads(potential_json)
                            valid_json_strings.append(potential_json)
                        except json.JSONDecodeError:
                            pass
                        start_index = i + 1
                        break
            else:
                break
        
        if valid_json_strings:
            json_str = valid_json_strings[-1]
            print(f"--- DEBUG: Taking the LAST valid JSON found ---\n{json_str}\n-------------------------------------------------")
            parsed_json = json.loads(json_str)
            return parsed_json
        else:
            print("Error: No valid JSON object found in the subtask conversion response.")
            return {}
            
    except Exception as e:
        print(f"An unexpected error occurred during subtask conversion: {e}")
        return {}

async def executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Executes the planned subtasks and collects results."""
    print("---NODE: Executor---")
    
    plan = state.get("plan", [])
    if not plan:
        return {"tool_results": []}
    
    results_list = []
    
    # Get the history summary and user input for context
    history_summary = state.get("history_summary", "")
    user_input = state.get("messages", [""].content if state.get("messages") else "")
    
    try:
        for i, subtask in enumerate(plan):
            print(f"--- EXECUTING SUBTASK {i+1}: {subtask} ---")
            
            # Convert natural language subtask to tool call
            tool_call = await _convert_subtask_to_tool_call(subtask, history_summary, user_input, results_list)
            
            if tool_call:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("args", {})
                
                if tool_name and tool_name in TOOLS:
                    print(f"--- QUEUING: {tool_name} with args {tool_args} ---")
                    result = await execute_tool(tool_name, tool_args)
                    results_list.append({"subtask": subtask, "result": result})
                else:
                    error_msg = f"Tool '{tool_name}' not found or invalid."
                    results_list.append({"subtask": subtask, "result": error_msg})
            else:
                error_msg = f"Could not convert subtask to tool call: {subtask}"
                results_list.append({"subtask": subtask, "result": error_msg})
        
        return {"tool_results": results_list}
    except Exception as e:
        print(f"Error during subtask execution: {e}")
        return {"tool_results": [f"An error occurred during subtask execution: {e}"]}
