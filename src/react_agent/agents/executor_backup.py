"""Executor agent for the AI interior design quotation system."""

import json
from typing import Dict, Any, List, Optional
import re
import asyncio
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..new_tools import execute_tool, TOOLS
from .planner import MODELS

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate

from ..new_tools import TOOLS, execute_tool
from ..prompts import FINAL_RESPONDER_PROMPT_TOOL_RESULTS, FINAL_RESPONDER_PROMPT_DIRECT_RESPONSE
from ..debug_utils import log_api_call

def _log_debug_info(subtask: str, tools_description: str, tool_results: List[Any], step_id: str):
    """Log debug information to file for troubleshooting."""
    debug_dir = "debug_logs"
    os.makedirs(debug_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{debug_dir}/debug_{timestamp}_{step_id}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("=== DEBUG LOG ===\n")
        f.write(f"Timestamp: {datetime.now()}\n")
        f.write(f"Step ID: {step_id}\n\n")
        
        f.write("=== SUBTASK ===\n")
        f.write(f"{subtask}\n\n")
        
        f.write("=== TOOLS DESCRIPTION ===\n")
        f.write(f"{tools_description}\n\n")
        
        f.write("=== TOOL RESULTS ===\n")
        for i, result in enumerate(tool_results):
            f.write(f"Result {i+1}:\n")
            f.write(f"Type: {type(result)}\n")
            f.write(f"Content: {result}\n")
            f.write("-" * 50 + "\n")
        
        f.write("\n=== END DEBUG LOG ===\n")
    
    print(f"Debug info logged to: {filename}")

def _parse_surfaces_from_step(subtask: str) -> List[Dict]:
    """
    Parse surfaces information from a complex step containing multiple surfaces.
    Expected format: "position (category - material_type - subtype, area)"
    """
    surfaces = []
    
    # Pattern to match: position (category - material_type - subtype, area)
    # Example: sàn (Sàn - Sàn gỗ - Gỗ công nghiệp, 20m2)
    pattern = r'(\w+(?:\s+\w+)*)\s*\(([^)]+)\)'
    
    matches = re.findall(pattern, subtask)
    
    for position, details in matches:
        position = position.strip()
        
        # Split details by comma to separate material info from area
        parts = details.split(',')
        if len(parts) != 2:
            continue
            
        material_info = parts[0].strip()
        area_info = parts[1].strip()
        
        # Parse material info: "category - material_type - subtype"
        material_parts = material_info.split(' - ')
        
        surface = {
            "position": position,
            "area": _extract_area(area_info)
        }
        
        if len(material_parts) >= 1:
            surface["category"] = material_parts[0].strip()
        if len(material_parts) >= 2:
            surface["material_type"] = material_parts[1].strip()
        if len(material_parts) >= 3:
            surface["subtype"] = material_parts[2].strip()
        
        surfaces.append(surface)
    
    return surfaces

def _extract_area(area_text: str) -> int:
    """Extract area value from text like '20m2', '20 m2', '20'"""
    # Remove common area units and extract number
    area_text = area_text.replace('m2', '').replace('m²', '').replace(' ', '')
    try:
        return int(float(area_text))
    except:
        return 0

def _extract_budget_from_step(subtask: str) -> Optional[float]:
    """Extract budget value from step text"""
    # Look for budget patterns like "300 triệu", "300000000", etc.
    budget_patterns = [
        r'(\d+)\s*triệu',
        r'(\d+)\s*trăm\s*nghìn',
        r'(\d+)\s*nghìn',
        r'(\d{6,})'  # Large numbers that could be budget
    ]
    
    for pattern in budget_patterns:
        matches = re.findall(pattern, subtask)
        if matches:
            try:
                value = int(matches[0])
                if 'triệu' in subtask:
                    return value * 1000000
                elif 'trăm nghìn' in subtask:
                    return value * 100000
                elif 'nghìn' in subtask:
                    return value * 1000
                else:
                    # Assume it's already in VND if it's a large number
                    if value > 1000000:  # More than 1 million
                        return float(value)
            except:
                continue
    
    return None

async def _convert_subtask_to_tool_call(subtask: str, previous_results: List[Any]) -> Dict[str, Any]:
    """Converts a natural language subtask to a tool call."""
    # Create detailed tools description with parameter information (same as planner)
    tools_description = []
    for name, tool in TOOLS.items():
        import inspect

        # Lấy function gốc từ tool wrapper
        if hasattr(tool, 'func'):
            original_func = tool.func
        else:
            original_func = tool

        sig = inspect.signature(original_func)
        params = []
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            annotation = (
                param.annotation.__name__
                if hasattr(param.annotation, '__name__')
                else str(param.annotation) if param.annotation is not inspect._empty
                else "Any"
            )
            param_info = f"{param_name}: {annotation}"
            if param.default != inspect.Parameter.empty:
                param_info += f" = {param.default!r}"
            params.append(param_info)

        doc = original_func.__doc__ or ""
        tool_info = f"- {name}: {doc}\n  Parameters: {', '.join(params)}"
        tools_description.append(tool_info)

    tools_description_str = "\n".join(tools_description)
    
    prompt = f"""<system>
Bạn là một AI chuyên gia chuyển đổi các subtask bằng ngôn ngữ tự nhiên thành các lệnh gọi công cụ cụ thể.

## Công cụ có sẵn
{tools_description_str}

## Subtask cần chuyển đổi
{subtask}

## Hướng dẫn mapping (QUAN TRỌNG)
- **Tập trung vào chức năng:** Phân tích subtask để hiểu chức năng cần thực hiện, sau đó chọn tool phù hợp.
- **Mapping theo chức năng:**
  - "Tra cứu giá nội bộ" → get_internal_price
  - "Tra cứu giá cho [vị trí]: [category] - [material_type]" → get_internal_price
  - "Tìm kiếm vật liệu" → search_materials  
  - "Lấy danh mục" → get_categories
  - "Lấy loại vật liệu" → get_material_types
  - "Lấy phân loại" → get_material_subtypes
  - "Tra cứu giá thị trường" → get_market_price
  - "Đề xuất phương án vật liệu phù hợp với ngân sách" (có ngân sách + area_map) → propose_options_for_budget (tự động parse surfaces từ step với format: position (category - material_type - subtype, area))
  - "Cung cấp khoảng giá vật liệu" hoặc "Báo giá sơ bộ" (có area_map, không cần ngân sách) → get_material_price_ranges
  - "Lấy báo giá đã lưu" → get_saved_quotes
  - "Lưu báo giá" → save_quote_to_file

- **Lưu ý:**
  - Nếu subtask chứa "Cung cấp khoảng giá vật liệu" hoặc "Báo giá sơ bộ" cho nhiều hạng mục, mapping sang get_material_price_ranges.
  - Nếu subtask chứa "Đề xuất phương án vật liệu phù hợp với ngân sách" và có ngân sách, mapping sang propose_options_for_budget.
  - Chỉ mapping tool khi đủ thông tin cần thiết (category, material_type, diện tích, ngân sách nếu cần). Nếu thiếu, trả về yêu cầu bổ sung thông tin.
- **QUAN TRỌNG:** Chỉ thêm subtype vào args khi Planner chỉ định rõ ràng trong subtask. KHÔNG tự động thêm subtype nếu Planner không nhắc đến.
- Nếu subtask có từ khóa như "dùng giá của step N", "so sánh giá của step 1 và step 2", hoặc nhắc đến số step cụ thể, hãy lấy kết quả tương ứng từ previous_results/context và truyền vào args tool (dưới key 'previous_result' hoặc 'compare_values').
- Nếu subtask yêu cầu nhiều giá, truyền đủ các giá đã tra cứu vào args (dưới dạng list).
- Nếu subtask chỉ nói chung chung "dùng giá vừa tra cứu" hoặc "dùng kết quả bước trước", hãy lấy kết quả step trước đó.
- Nếu không có công cụ nào phù hợp, hãy trả về một đối tượng rỗng {{}}.

### Ví dụ 1: Tra cứu giá nội bộ
```json
{{
  "name": "get_internal_price",
  "args": {{ "category": "Sàn", "material_type": "Sàn gỗ" }}
}}
```
### Ví dụ 1b: Tra cứu giá cho vị trí cụ thể
```json
{{
  "name": "get_internal_price",
  "args": {{ "category": "Trần", "material_type": "Trần thạch cao" }}
}}
```
### Ví dụ 1c: Tra cứu giá với subtype được chỉ định rõ ràng
```json
{{
  "name": "get_internal_price",
  "args": {{ "category": "Sàn", "material_type": "Sàn gỗ", "subtype": "Gỗ sồi engineer" }}
}}
```
### Ví dụ 2: Tìm kiếm vật liệu
```json
{{
  "name": "search_materials",
  "args": {{ "query": "gỗ sồi engineer" }}
}}
```
### Ví dụ 3: Lấy danh mục
```json
{{
  "name": "get_categories",
  "args": {{}}
}}
```
### Ví dụ 4: So sánh giá của step 1 và step 2
```json
{{
  "name": "compare_prices",
  "args": {{ "compare_values": [<giá từ step 1>, <giá từ step 2>] }}
}}
```
### Ví dụ 5: Đề xuất theo ngân sách (tự động tạo bảng)
```json
{{
  "name": "propose_options_for_budget",
  "args": {{
    "budget": 300000000,
    "surfaces": [
      {{ "position": "sàn", "category": "Sàn", "material_type": "Sàn gỗ", "subtype": "Gỗ công nghiệp", "area": 20 }},
      {{ "position": "tường trái", "category": "Tường và vách", "material_type": "Gạch ốp tường", "subtype": "Gạch cao cấp", "area": 10 }},
      {{ "position": "tường phải", "category": "Tường và vách", "material_type": "Sơn", "subtype": "Sơn nước", "area": 10 }},
      {{ "position": "tường đối diện", "category": "Tường và vách", "material_type": "Vách thạch cao", "subtype": "Khung xương M29", "area": 15 }},
      {{ "position": "trần", "category": "Trần", "material_type": "Trần thạch cao", "subtype": "Tấm thạch cao 9mm", "area": 20 }}
    ]
  }}
}}
```
### Ví dụ 5b: Đề xuất với diện tích tổng
```json
{{
  "name": "propose_options_for_budget",
  "args": {{ "budget": 300000000, "area": "100" }}
}}
```
### Ví dụ 5c: Đề xuất với surfaces chi tiết (tự động parse từ step)
```json
{{
  "name": "propose_options_for_budget",
  "args": {{ 
    "budget": 300000000, 
    "surfaces": [
      {{ "position": "sàn", "category": "Sàn", "material_type": "Sàn gỗ", "subtype": "An Cường", "area": 20 }},
      {{ "position": "tường đối diện", "category": "Tường và vách", "material_type": "Giấy dán tường", "subtype": "Hàn Quốc", "area": 10 }},
      {{ "position": "tường trái", "category": "Tường và vách", "material_type": "Sơn", "area": 10 }},
      {{ "position": "trần", "category": "Trần", "material_type": "Trần thạch cao", "area": 20 }}
    ]
  }}
}}

/think
```
"""
    
    llm = MODELS["LLM_PLANNER"]
    response = await llm.ainvoke(prompt)
    raw_response_text = response.content
    print(f"LLM Raw Response for Subtask Conversion: {raw_response_text}")
    
    # Log API call
    log_api_call(
        node_name="executor_subtask_conversion",
        prompt=prompt,
        response=response.content,
        additional_info={
            "subtask": subtask,
            "previous_results_count": len(previous_results)
        }
    )
    
    # Parse the response
    import re
    try:
        clean_response = raw_response_text
        # Ưu tiên parse JSON trong block code
        json_block = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", clean_response)
        if json_block:
            clean_response = json_block.group(1)
        else:
            # Nếu không có block code, lấy đoạn sau </think>
            if "<think>" in clean_response and "</think>" in clean_response:
                start = clean_response.find("</think>") + len("</think>")
                clean_response = clean_response[start:].strip()
        response_dict = json.loads(clean_response)
        
        # Special handling for propose_options_for_budget with complex surfaces
        if response_dict.get("name") == "propose_options_for_budget":
            # Check if we need to parse surfaces from the step
            if "surfaces" not in response_dict.get("args", {}):
                surfaces = _parse_surfaces_from_step(subtask)
                budget = _extract_budget_from_step(subtask)
                
                if surfaces and budget:
                    response_dict["args"] = {
                        "budget": budget,
                        "surfaces": surfaces
                    }
        
        return response_dict
    except json.JSONDecodeError:
        print(f"Failed to parse LLM response as JSON: {raw_response_text}")
        return {}

async def executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Executes the planned subtasks and collects results."""
    print("---NODE: Executor---")
    plan = state.get("plan", [])
    response_reason = state.get("response_reason", "")
    history_summary = state.get("history_summary", "")
    quotes = state.get("quotes", []) or []
    if not plan:
        return {
            "tool_results": [],
            "response_reason": response_reason,
            "history_summary": history_summary,
            "quotes": quotes
        }
    results_list = []
    context = {}
    try:
        step_groups = _analyze_step_dependencies(plan)
        for group_idx, step_group in enumerate(step_groups):
            print(f"--- EXECUTING STEP GROUP {group_idx + 1}: {len(step_group)} steps ---")
            if len(step_group) == 1:
                subtask = step_group[0]
                # Kiểm tra nếu đã có báo giá cho subtask này trong quotes
                if any(q.get('subtask') == subtask for q in quotes):
                    # Lấy báo giá đã có
                    quote = next(q for q in quotes if q.get('subtask') == subtask)
                    results_list.append(quote)
                else:
                    result = await _execute_single_step(
                        subtask, group_idx, context, results_list
                    )
                    results_list.append(result)
                    # Nếu là báo giá, thêm vào quotes
                    if 'result' in result and isinstance(result['result'], (int, float, str)):
                        quotes.append({"subtask": subtask, "result": result['result']})
            else:
                parallel_tasks = []
                for step_idx, subtask in enumerate(step_group):
                    if any(q.get('subtask') == subtask for q in quotes):
                        quote = next(q for q in quotes if q.get('subtask') == subtask)
                        results_list.append(quote)
                    else:
                        task = _execute_single_step(
                            subtask, f"{group_idx}_{step_idx}", context, results_list
                        )
                        parallel_tasks.append((subtask, task))
                parallel_results = await asyncio.gather(*(t[1] for t in parallel_tasks), return_exceptions=True)
                for (subtask, _), r in zip(parallel_tasks, parallel_results):
                    if not isinstance(r, Exception):
                        results_list.append(r)
                        if 'result' in r and isinstance(r['result'], (int, float, str)):
                            quotes.append({"subtask": subtask, "result": r['result']})
        return {
            "tool_results": results_list,
            "context": context,
            "response_reason": response_reason,
            "history_summary": history_summary,
            "quotes": quotes
        }
    except Exception as e:
        print(f"Error during subtask execution: {e}")
        return {
            "tool_results": [f"An error occurred during subtask execution: {e}"],
            "response_reason": response_reason,
            "history_summary": history_summary,
            "quotes": quotes
        }

def _analyze_step_dependencies(plan: List[str]) -> List[List[str]]:
    """Phân tích dependencies và nhóm các steps có thể chạy song song."""
    step_groups = []
    current_group = []
    
    for i, subtask in enumerate(plan):
        # Kiểm tra xem step này có phụ thuộc vào step trước không
        has_dependency = _check_step_dependency(subtask, i, plan)
        
        if has_dependency and current_group:
            # Nếu có dependency và đang có group, kết thúc group hiện tại
            step_groups.append(current_group)
            current_group = [subtask]
        else:
            # Thêm vào group hiện tại
            current_group.append(subtask)
    
    # Thêm group cuối cùng
    if current_group:
        step_groups.append(current_group)
    
    return step_groups

def _check_step_dependency(subtask: str, current_index: int, plan: list) -> bool:
    """Kiểm tra xem step hiện tại có phụ thuộc vào step trước không."""
    subtask_lower = subtask.lower()
    
    # 1. Kiểm tra từ khóa dependency (mở rộng hơn)
    dependency_keywords = [
        "dùng giá của step", "so sánh giá của step", "tổng hợp kết quả của step",
        "dùng kết quả của step", "dựa trên kết quả của step", "sử dụng kết quả của step",
        "dựa vào step", "từ step", "của step", "với step", "và step",
        "kết hợp", "tổng hợp", "so sánh", "đối chiếu", "tích hợp"
    ]
    
    for keyword in dependency_keywords:
        if keyword in subtask_lower:
            return True
    
    # 2. Kiểm tra số step cụ thể (cải tiến regex)
    step_patterns = [
        r"step\s*(\d+)",
        r"bước\s*(\d+)", 
        r"kết quả\s*(\d+)",
        r"giá\s*(\d+)",
        r"dữ liệu\s*(\d+)"
    ]
    
    for pattern in step_patterns:
        step_numbers = re.findall(pattern, subtask_lower)
        if step_numbers:
            for step_num in step_numbers:
                try:
                    step_idx = int(step_num) - 1
                    if step_idx < current_index:
                        return True
                except ValueError:
                    continue
    
    # 3. Kiểm tra context từ tools (mới)
    # Nếu step này cần dữ liệu từ step trước dựa trên loại tool
    tool_dependencies = {
        "propose_options_for_budget": ["get_internal_price", "get_market_price"],
        "save_quote_to_file": ["propose_options_for_budget"],
        "compare_prices": ["get_internal_price", "get_market_price"]
    }
    
    # 4. Kiểm tra semantic similarity (đơn giản)
    # Nếu step này có vẻ như xử lý kết quả từ step trước
    semantic_indicators = [
        "tổng hợp", "kết hợp", "so sánh", "đối chiếu", "tích hợp",
        "dựa trên", "sử dụng", "từ", "của", "với"
    ]
    
    for indicator in semantic_indicators:
        if indicator in subtask_lower and current_index > 0:
            # Kiểm tra xem có phải đang xử lý kết quả từ step trước không
            return True
    
    return False

async def _execute_single_step(
    subtask: str, 
    step_id: Any, 
    context: Dict[str, Any], 
    results_list: List[Any]
) -> Dict[str, Any]:
    """Thực hiện một step đơn lẻ."""
    print(f"--- EXECUTING SUBTASK {step_id}: {subtask} ---")
    
    # Kiểm tra xem có phải step tổng hợp không
    if _is_summary_step(subtask):
        return await _execute_summary_step(subtask, context, results_list)
    
    # Parse số step từ subtask để lấy đúng dữ liệu context
    tool_call_context = None
    step_numbers = re.findall(r"step\s*(\d+)", subtask.lower())
    if step_numbers:
        # Nếu subtask nhắc đến nhiều step, lấy đủ các giá trị
        context_values = []
        for step_num in step_numbers:
            price = context.get(f"step_{step_num}_price")
            market_price = context.get(f"step_{step_num}_market_price")
            quote = context.get(f"step_{step_num}_quote")
            context_values.append(price or market_price or quote)
        # Nếu chỉ có 1 step, truyền trực tiếp, nếu nhiều step, truyền list
        if len(context_values) == 1:
            tool_call_context = context_values[0]
        else:
            tool_call_context = context_values
    
    # Mapping subtask → tool call
    tool_call = await _convert_subtask_to_tool_call(
        subtask, results_list
    )
    
    # Log debug info - lấy tools_description đúng từ _convert_subtask_to_tool_call
    tools_description = []
    for name, tool in TOOLS.items():
        import inspect
        
        # Lấy function gốc từ tool wrapper
        if hasattr(tool, 'func'):
            original_func = tool.func
        else:
            original_func = tool
        
        sig = inspect.signature(original_func)
        params = []
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            param_info = f"{param_name}: {param.annotation.__name__ if hasattr(param.annotation, '__name__') else str(param.annotation)}"
            if param.default != inspect.Parameter.empty:
                param_info += f" = {param.default}"
            params.append(param_info)
        
        tool_doc = original_func.__doc__ or ""
        tool_info = f"- {name}: {tool_doc}\n  Parameters: {', '.join(params)}"
        tools_description.append(tool_info)
    
    tools_description_str = "\n".join(tools_description)
    _log_debug_info(subtask, tools_description_str, results_list, str(step_id))
    
    # Log tool_call details
    if tool_call:
        print(f"--- DEBUG: Tool call: {json.dumps(tool_call, ensure_ascii=False, indent=2)} ---")
    else:
        print(f"--- DEBUG: No tool call generated for subtask: {subtask} ---")
    
    # Nếu tool_call cần bổ sung giá từ context, truyền vào args
    if tool_call_context and tool_call and isinstance(tool_call.get("args"), dict):
        tool_call["args"]["previous_result"] = tool_call_context
    
    if tool_call:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        
        if tool_name and tool_name in TOOLS:
            print(f"--- QUEUING: {tool_name} with args {tool_args} ---")
            result = await execute_tool(tool_name, tool_args)
            
            # Lưu kết quả quan trọng vào context
            if tool_name == "get_internal_price":
                context[f"step_{step_id}_price"] = result
            elif tool_name == "get_market_price":
                context[f"step_{step_id}_market_price"] = result
            elif tool_name == "get_material_price_ranges":
                context[f"step_{step_id}_price_ranges"] = result
            
            return {"subtask": subtask, "result": result}
        else:
            error_msg = f"Tool '{tool_name}' not found or invalid."
            return {"subtask": subtask, "result": error_msg}
    else:
        error_msg = f"Could not convert subtask to tool call: {subtask}"
        return {"subtask": subtask, "result": error_msg}

def _is_summary_step(subtask: str) -> bool:
    """Kiểm tra xem có phải step tổng hợp không."""
    summary_keywords = [
        "tổng hợp", "kết hợp", "so sánh", "đối chiếu", "tích hợp",
        "tổng kết", "tổng hợp kết quả", "gửi cho người dùng",
        "trình bày", "báo cáo", "tổng hợp tất cả"
    ]
    
    subtask_lower = subtask.lower()
    for keyword in summary_keywords:
        if keyword in subtask_lower:
            return True
    return False

async def _execute_summary_step(
    subtask: str, 
    context: Dict[str, Any], 
    results_list: List[Any]
) -> Dict[str, Any]:
    """Thực hiện step tổng hợp dữ liệu."""
    print(f"--- EXECUTING SUMMARY STEP: {subtask} ---")
    
    # Tạo prompt tổng hợp
    summary_prompt = f"""<system>
Bạn là một AI chuyên tổng hợp và trình bày kết quả từ các công cụ nội bộ.

## Yêu cầu tổng hợp
{subtask}

## Dữ liệu có sẵn
{json.dumps(context, ensure_ascii=False, indent=2)}

## Kết quả từ các tools
{json.dumps(results_list, ensure_ascii=False, indent=2)}

## Hướng dẫn tổng hợp
1. Phân tích dữ liệu từ context và results_list
2. Tổng hợp thông tin một cách logic và dễ hiểu
3. Trình bày kết quả theo yêu cầu trong subtask
4. Sử dụng ngôn ngữ tự nhiên, chuyên nghiệp
5. Không hiển thị tên tools hoặc JSON raw
6. Giữ nguyên dạng bảng nếu kết quả trả về là một bảng.
Hãy tạo ra một báo cáo tổng hợp hoàn chỉnh.
/no_think
</system>"""
    
    # Gọi LLM để tổng hợp
    llm = MODELS["LLM_PLANNER"]  # Sử dụng cùng model với planner
    response = await llm.ainvoke(summary_prompt)
    
    # Log API call
    log_api_call(
        node_name="executor_summary_step",
        prompt=summary_prompt,
        response=response.content,
        additional_info={
            "subtask": subtask,
            "context_keys": list(context.keys()),
            "results_count": len(results_list)
        }
    )
    
    return {"subtask": subtask, "result": response.content}
