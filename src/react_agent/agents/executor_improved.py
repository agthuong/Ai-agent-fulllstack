"""Improved Executor agent for the AI interior design quotation system."""

import json
from typing import Dict, Any, List, Optional
import re
import asyncio
import os
from datetime import datetime

from ..new_tools import execute_tool, TOOLS
from .planner import MODELS
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

def _extract_area(area_text: str) -> float:
    """Extract area value from text like '20m2', '20 m2', '20'"""
    # Remove common area units and extract number
    area_text = area_text.replace('m2', '').replace('m²', '').replace(' ', '')
    try:
        return float(area_text)
    except:
        return 0.0

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

async def _convert_subtask_to_tool_call(subtask: str, previous_results: List[Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Converts a natural language subtask to a tool call with improved logic."""
    
    # Create detailed tools description
    tools_description = []
    for name, tool in TOOLS.items():
        import inspect

        # Get original function from tool wrapper
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
    
    # Enhanced prompt with better context handling
    prompt = f"""<system>
Bạn là một AI chuyên gia chuyển đổi các subtask bằng ngôn ngữ tự nhiên thành các lệnh gọi công cụ cụ thể.

## Công cụ có sẵn
{tools_description_str}

## Subtask cần chuyển đổi
{subtask}

## Context từ các steps trước (nếu có)
{json.dumps(context, ensure_ascii=False, indent=2) if context else "Không có context"}

## Previous results (nếu có)
{json.dumps(previous_results[-3:] if previous_results else [], ensure_ascii=False, indent=2)}

## HƯỚNG DẪN MAPPING NÂNG CAO

### 1. Phân tích chức năng chính:
- **"Tra cứu giá nội bộ"** → get_internal_price_new
- **"Tìm kiếm vật liệu"** → search_materials_new  
- **"Lấy danh mục"** → get_categories_new
- **"Lấy loại vật liệu"** → get_material_types_new
- **"Lấy phân loại"** → get_material_subtypes_new
- **"Tra cứu giá thị trường"** → get_market_price_new
- **"Đề xuất phương án vật liệu phù hợp với ngân sách"** → propose_options_for_budget
- **"Cung cấp khoảng giá vật liệu"** → get_material_price_ranges
- **"Lấy báo giá đã lưu"** → get_saved_quotes_new
- **"Lưu báo giá"** → save_quote_to_file_new

### 2. Xử lý surfaces phức tạp:
- Nếu subtask chứa format "position (category - material_type - subtype, area)", tự động parse thành surfaces array
- Ví dụ: "sàn (Sàn - Sàn gỗ, 24m²)" → {{"position": "sàn", "category": "Sàn", "material_type": "Sàn gỗ", "area": 24}}

### 3. Xử lý dependencies:
- Nếu subtask nhắc đến "step X", "kết quả step Y", tìm trong previous_results
- Nếu subtask yêu cầu "so sánh", "tổng hợp", sử dụng dữ liệu từ context

### 4. Xử lý ngân sách:
- Tự động chuyển đổi: "300 triệu" → 300000000
- "50 nghìn" → 50000, "2 tỷ" → 2000000000

### 5. Validation:
- Chỉ mapping khi đủ thông tin cần thiết
- Nếu thiếu thông tin quan trọng, trả về {{"error": "Thiếu thông tin X"}}

## VÍ DỤ MAPPING

### Ví dụ 1: Đề xuất với surfaces phức tạp
Input: "Đề xuất phương án vật liệu phù hợp với ngân sách 300 triệu cho sàn (Sàn - Sàn gỗ, 24m²), trần (Trần - Trần thạch cao, 24m²)"
Output:
```json
{{
  "name": "propose_options_for_budget",
  "args": {{
    "budget": 300000000,
    "surfaces": [
      {{"position": "sàn", "category": "Sàn", "material_type": "Sàn gỗ", "area": 24}},
      {{"position": "trần", "category": "Trần", "material_type": "Trần thạch cao", "area": 24}}
    ]
  }}
}}
```

### Ví dụ 2: Tra cứu giá đơn giản
Input: "Tra cứu giá nội bộ cho Sàn - Sàn gỗ"
Output:
```json
{{
  "name": "get_internal_price_new",
  "args": {{
    "category": "Sàn",
    "material_type": "Sàn gỗ"
  }}
}}
```

### Ví dụ 3: Tổng hợp với context
Input: "Tổng hợp kết quả từ step 1 và step 2"
Output:
```json
{{
  "name": "summarize_results",
  "args": {{
    "previous_results": [<data từ step 1>, <data từ step 2>]
  }}
}}
```

## LƯU Ý QUAN TRỌNG
- LUÔN trả về JSON hợp lệ
- KHÔNG bịa thông tin không có trong subtask
- ƯU TIÊN độ chính xác hơn độ đầy đủ
- Nếu không chắc chắn, trả về {{"error": "Không thể xác định tool phù hợp"}}

Hãy phân tích subtask và trả về JSON tool call phù hợp:
</system>"""
    
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
            "previous_results_count": len(previous_results),
            "context_keys": list(context.keys()) if context else []
        }
    )
    
    # Parse the response
    try:
        clean_response = raw_response_text
        # Look for JSON in code blocks first
        json_block = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", clean_response)
        if json_block:
            clean_response = json_block.group(1)
        else:
            # Look for JSON after </system> or similar markers
            markers = ["</system>", "</think>", "Output:", "Result:"]
            for marker in markers:
                if marker in clean_response:
                    start = clean_response.find(marker) + len(marker)
                    clean_response = clean_response[start:].strip()
                    break
        
        # Try to find the first complete JSON object
        brace_count = 0
        start_idx = clean_response.find('{')
        if start_idx != -1:
            for i in range(start_idx, len(clean_response)):
                if clean_response[i] == '{':
                    brace_count += 1
                elif clean_response[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        clean_response = clean_response[start_idx:i+1]
                        break
        
        response_dict = json.loads(clean_response)
        
        # Enhanced post-processing for specific tools
        if response_dict.get("name") == "propose_options_for_budget":
            # Auto-parse surfaces if not provided but subtask contains surface info
            if "surfaces" not in response_dict.get("args", {}):
                surfaces = _parse_surfaces_from_step(subtask)
                budget = _extract_budget_from_step(subtask)
                
                if surfaces and budget:
                    response_dict["args"] = {
                        "budget": budget,
                        "surfaces": surfaces
                    }
        
        elif response_dict.get("name") == "get_material_price_ranges":
            # Auto-parse surfaces for price ranges
            if "surfaces" not in response_dict.get("args", {}):
                surfaces = _parse_surfaces_from_step(subtask)
                if surfaces:
                    response_dict["args"] = {"surfaces": surfaces}
        
        return response_dict
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM response as JSON: {raw_response_text}")
        print(f"JSON Error: {e}")
        return {"error": f"Không thể parse response: {e}"}
    except Exception as e:
        print(f"Unexpected error in subtask conversion: {e}")
        return {"error": f"Lỗi không mong muốn: {e}"}

async def _execute_single_step(subtask: str, step_id: str, context: Dict[str, Any], previous_results: List[Any]) -> Dict[str, Any]:
    """Execute a single step with improved error handling and result processing."""
    print(f"--- EXECUTING STEP {step_id}: {subtask} ---")
    
    try:
        # Convert subtask to tool call
        tool_call = await _convert_subtask_to_tool_call(subtask, previous_results, context)
        
        if "error" in tool_call:
            return {
                "subtask": subtask,
                "step_id": step_id,
                "error": tool_call["error"],
                "result": f"Lỗi: {tool_call['error']}"
            }
        
        if not tool_call or "name" not in tool_call:
            return {
                "subtask": subtask,
                "step_id": step_id,
                "error": "Không thể xác định tool phù hợp",
                "result": "Không thể thực hiện subtask này"
            }
        
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        
        print(f"Tool call: {tool_name} with args: {tool_args}")
        
        # Execute the tool
        if tool_name in TOOLS:
            result = await execute_tool(tool_name, tool_args)
            
            # Store result in context for future steps
            context[f"step_{step_id}"] = result
            context[f"step_{step_id}_subtask"] = subtask
            
            return {
                "subtask": subtask,
                "step_id": step_id,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "result": result,
                "success": True
            }
        else:
            return {
                "subtask": subtask,
                "step_id": step_id,
                "error": f"Tool '{tool_name}' không tồn tại",
                "result": f"Lỗi: Tool '{tool_name}' không tồn tại"
            }
            
    except Exception as e:
        print(f"Error executing step {step_id}: {e}")
        return {
            "subtask": subtask,
            "step_id": step_id,
            "error": str(e),
            "result": f"Lỗi khi thực hiện: {e}"
        }

def _analyze_step_dependencies(plan: List[str]) -> List[List[str]]:
    """Improved dependency analysis with better keyword detection."""
    step_groups = []
    current_group = []
    
    for i, subtask in enumerate(plan):
        has_dependency = _check_step_dependency(subtask, i, plan)
        
        if has_dependency and current_group:
            # End current group and start new one
            step_groups.append(current_group)
            current_group = [subtask]
        else:
            # Add to current group
            current_group.append(subtask)
    
    # Add final group
    if current_group:
        step_groups.append(current_group)

    return step_groups

def _check_step_dependency(subtask: str, current_index: int, plan: list) -> bool:
    """Enhanced dependency checking with more comprehensive patterns."""
    subtask_lower = subtask.lower()

    # 1. Explicit step references
    step_patterns = [
        r"step\s*(\d+)",
        r"bước\s*(\d+)",
        r"từ\s+step\s*(\d+)",
        r"của\s+step\s*(\d+)",
        r"kết\s+quả\s+step\s*(\d+)"
    ]
    
    for pattern in step_patterns:
        matches = re.findall(pattern, subtask_lower)
        if matches:
            # Check if referenced step is before current step
            for match in matches:
                try:
                    referenced_step = int(match)
                    if referenced_step <= current_index:
                        return True
                except ValueError:
                    continue

    # 2. Dependency keywords
    dependency_keywords = [
        "tổng hợp", "so sánh", "kết hợp", "đối chiếu",
        "dựa trên", "sử dụng kết quả", "từ kết quả",
        "với giá", "và giá", "cùng với",
        "phân tích", "đánh giá", "xem xét"
    ]
    
    for keyword in dependency_keywords:
        if keyword in subtask_lower:
            return True

    # 3. Sequential indicators
    sequential_indicators = [
        "tiếp theo", "sau đó", "cuối cùng", "kết thúc",
        "tổng kết", "hoàn thiện", "finalize"
    ]
    
    for indicator in sequential_indicators:
        if indicator in subtask_lower:
            return True

    return False

def _summarize_results(results_list: List[Dict[str, Any]]) -> str:
    """Create a comprehensive summary of all execution results."""
    if not results_list:
        return "Không có kết quả nào được thực hiện."
    
    summary_parts = []
    successful_steps = 0
    failed_steps = 0
    
    for result in results_list:
        if result.get("success"):
            successful_steps += 1
            subtask = result.get("subtask", "Unknown task")
            tool_result = result.get("result", "No result")
            
            # Format the result nicely
            if isinstance(tool_result, str) and len(tool_result) > 200:
                tool_result = tool_result[:200] + "..."
            
            summary_parts.append(f"✓ {subtask}: {tool_result}")
        else:
            failed_steps += 1
            subtask = result.get("subtask", "Unknown task")
            error = result.get("error", "Unknown error")
            summary_parts.append(f"✗ {subtask}: Lỗi - {error}")
    
    # Create overall summary
    overall_summary = f"Tổng kết thực hiện: {successful_steps} thành công, {failed_steps} thất bại\n\n"
    overall_summary += "\n".join(summary_parts)
    
    return overall_summary

async def executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced executor node with better dependency handling and result aggregation."""
    print("---NODE: Enhanced Executor---")
    
    plan = state.get("plan", [])
    response_reason = state.get("response_reason", "")
    history_summary = state.get("history_summary", "")
    quotes = state.get("quotes", []) or []
    
    if not plan:
        return {
            "tool_results": [],
            "response_reason": response_reason,
            "history_summary": history_summary,
            "quotes": quotes,
            "execution_summary": "Không có kế hoạch nào để thực hiện."
        }
    
    results_list = []
    context = {}
    
    try:
        print(f"--- ANALYZING PLAN DEPENDENCIES ---")
        step_groups = _analyze_step_dependencies(plan)
        print(f"Identified {len(step_groups)} step groups: {[len(group) for group in step_groups]}")
        
        for group_idx, step_group in enumerate(step_groups):
            print(f"--- EXECUTING STEP GROUP {group_idx + 1}: {len(step_group)} steps ---")
            
            if len(step_group) == 1:
                # Single step execution
                subtask = step_group[0]
                
                # Check if we already have a quote for this subtask
                existing_quote = next((q for q in quotes if q.get('subtask') == subtask), None)
                if existing_quote:
                    print(f"Using existing quote for: {subtask}")
                    results_list.append(existing_quote)
                else:
                    result = await _execute_single_step(
                        subtask, f"group_{group_idx}", context, results_list
                    )
                    results_list.append(result)
                    
                    # Store successful results as quotes
                    if result.get("success") and result.get("result"):
                        quotes.append({
                            "subtask": subtask,
                            "result": result["result"],
                            "tool_name": result.get("tool_name"),
                            "timestamp": datetime.now().isoformat()
                        })
            else:
                # Parallel execution for independent steps
                print(f"Executing {len(step_group)} steps in parallel")
                parallel_tasks = []
                
                for step_idx, subtask in enumerate(step_group):
                    existing_quote = next((q for q in quotes if q.get('subtask') == subtask), None)
                    if existing_quote:
                        results_list.append(existing_quote)
                    else:
                        task = _execute_single_step(
                            subtask, f"group_{group_idx}_step_{step_idx}", context, results_list
                        )
                        parallel_tasks.append((subtask, task))
                
                if parallel_tasks:
                    parallel_results = await asyncio.gather(
                        *(task for _, task in parallel_tasks), 
                        return_exceptions=True
                    )
                    
                    for (subtask, _), result in zip(parallel_tasks, parallel_results):
                        if not isinstance(result, Exception):
                            results_list.append(result)
                            
                            if result.get("success") and result.get("result"):
                                quotes.append({
                                    "subtask": subtask,
                                    "result": result["result"],
                                    "tool_name": result.get("tool_name"),
                                    "timestamp": datetime.now().isoformat()
                                })
                        else:
                            # Handle exceptions
                            error_result = {
                                "subtask": subtask,
                                "error": str(result),
                                "result": f"Lỗi thực hiện: {result}",
                                "success": False
                            }
                            results_list.append(error_result)
        
        # Create execution summary
        execution_summary = _summarize_results(results_list)
        
        print(f"--- EXECUTION COMPLETED ---")
        print(f"Total results: {len(results_list)}")
        print(f"Total quotes: {len(quotes)}")
        
        return {
            "tool_results": results_list,
            "context": context,
            "response_reason": response_reason,
            "history_summary": history_summary,
            "quotes": quotes,
            "execution_summary": execution_summary
        }
        
    except Exception as e:
        print(f"Critical error during execution: {e}")
        return {
            "tool_results": [{"error": f"Critical execution error: {e}"}],
            "response_reason": response_reason,
            "history_summary": history_summary,
            "quotes": quotes,
            "execution_summary": f"Thực hiện thất bại: {e}"
        }