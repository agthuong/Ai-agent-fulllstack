"""Responder agent for the AI interior design quotation system."""

import json
from typing import Dict, Any, List

from langchain_core.messages import AIMessage

from ..prompts import FINAL_RESPONDER_PROMPT_TOOL_RESULTS, FINAL_RESPONDER_PROMPT_DIRECT_RESPONSE
from ..utils import load_chat_model
from ..configuration import Configuration
from ..debug_utils import log_api_call

# Load models once at the module level
config = Configuration.from_context()
MODELS = {
    "LLM_RESPONDER": load_chat_model(config.model)  # Main model for final responses
}

def _format_history(messages: list) -> str:
    """Helper to format the history for the prompt."""
    if not messages:
        return "No history."
    # A simple formatting for now, can be improved later
    return "\n".join([f"{msg.type}: {msg.content}" for msg in messages])

def _stringify_tool_results(tool_results: List[Any]) -> str:
    """Enhanced tool results formatting with better structure and readability."""
    if not tool_results:
        return ""
    
    parts = []
    successful_results = []
    failed_results = []
    
    for res in tool_results:
        if isinstance(res, dict):
            # Handle enhanced executor results
            if "subtask" in res:
                subtask = res.get("subtask", "Unknown task")
                success = res.get("success", False)
                result = res.get("result", "No result")
                tool_name = res.get("tool_name", "Unknown tool")
                
                if success:
                    successful_results.append({
                        "subtask": subtask,
                        "result": result,
                        "tool": tool_name
                    })
                else:
                    error = res.get("error", "Unknown error")
                    failed_results.append({
                        "subtask": subtask,
                        "error": error
                    })
            else:
                # Handle other dict formats
                parts.append(json.dumps(res, ensure_ascii=False, indent=2))
                
        elif isinstance(res, list):
            # Handle list results (e.g., search results)
            if res and isinstance(res[0], dict):
                # Create markdown table for structured data
                headers = res[0].keys()
                table = '| ' + ' | '.join(str(h) for h in headers) + ' |\n'
                table += '| ' + ' | '.join(['---'] * len(headers)) + ' |\n'
                for item in res:
                    row_data = []
                    for h in headers:
                        value = item.get(h, '')
                        # Truncate long values
                        if isinstance(value, str) and len(value) > 50:
                            value = value[:47] + "..."
                        row_data.append(str(value))
                    table += '| ' + ' | '.join(row_data) + ' |\n'
                parts.append(table)
            else:
                parts.append(json.dumps(res, ensure_ascii=False, indent=2))
                
        elif isinstance(res, str):
            parts.append(res)
        else:
            parts.append(str(res))
    
    # Format successful results
    if successful_results:
        success_section = "## Kết quả thực hiện thành công:\n\n"
        for i, result in enumerate(successful_results, 1):
            success_section += f"### {i}. {result['subtask']}\n"
            success_section += f"**Công cụ sử dụng:** {result['tool']}\n"
            success_section += f"**Kết quả:**\n{result['result']}\n\n"
        parts.insert(0, success_section)
    
    # Format failed results
    if failed_results:
        error_section = "## Các bước thực hiện gặp lỗi:\n\n"
        for i, error in enumerate(failed_results, 1):
            error_section += f"### {i}. {error['subtask']}\n"
            error_section += f"**Lỗi:** {error['error']}\n\n"
        parts.append(error_section)
    
    return '\n\n'.join(parts)

def _analyze_tool_results(tool_results: List[Any]) -> Dict[str, Any]:
    """Analyze tool results to provide better context for response generation."""
    analysis = {
        "has_pricing_data": False,
        "has_market_data": False,
        "has_internal_data": False,
        "has_errors": False,
        "successful_tasks": 0,
        "failed_tasks": 0,
        "main_results": [],
        "error_summary": []
    }
    
    if not tool_results:
        return analysis
    
    for result in tool_results:
        if isinstance(result, dict):
            if result.get("success"):
                analysis["successful_tasks"] += 1
                tool_name = result.get("tool_name", "")
                
                # Categorize by tool type
                if "internal_price" in tool_name or "price_ranges" in tool_name:
                    analysis["has_internal_data"] = True
                    analysis["has_pricing_data"] = True
                elif "market_price" in tool_name:
                    analysis["has_market_data"] = True
                    analysis["has_pricing_data"] = True
                elif "propose_options" in tool_name:
                    analysis["has_pricing_data"] = True
                    analysis["has_internal_data"] = True
                
                analysis["main_results"].append(result)
            else:
                analysis["failed_tasks"] += 1
                analysis["has_errors"] = True
                analysis["error_summary"].append({
                    "task": result.get("subtask", "Unknown"),
                    "error": result.get("error", "Unknown error")
                })
    
    return analysis

async def responder_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced responder node with better context analysis and response generation."""
    print("---NODE: Enhanced Responder---")
    
    messages = state["messages"]
    tool_results = state.get("tool_results", [])
    response_reason = state.get("response_reason", "")
    history_summary = state.get("history_summary", "")
    area_map = state.get("area_map", {})
    quotes = state.get("quotes", [])
    execution_summary = state.get("execution_summary", "")
    budget = state.get("budget")
    events_summary = state.get("events_summary", [])
    
    # Extract user input
    user_input = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == 'human':
            content = msg.content
            if not content.startswith('[Image Analysis Report]') and not content.startswith('## VAI TRÒ'):
                user_input = content
                break
    
    # Ensure we have some history context
    if not history_summary and user_input:
        history_summary = f"Người dùng yêu cầu: {user_input}"
    
    print(f"--- RESPONDER CONTEXT ---")
    print(f"Tool results count: {len(tool_results)}")
    print(f"Response reason: {response_reason}")
    print(f"Has budget: {budget is not None}")
    print(f"Area map items: {len(area_map)}")
    print(f"Quotes count: {len(quotes)}")
    print(f"-------------------------")
    
    # Analyze tool results for better response context
    results_analysis = _analyze_tool_results(tool_results)
    
    try:
        if tool_results:
            # We have tool execution results
            tool_results_str = _stringify_tool_results(tool_results)
            
            # Escape braces for format string
            tool_results_str = tool_results_str.replace('{', '{{').replace('}', '}}')
            
            # Add execution summary if available
            if execution_summary:
                tool_results_str += f"\n\n## Tóm tắt thực hiện:\n{execution_summary}"
            
            # Add quotes context if available
            if quotes:
                quotes_str = json.dumps(quotes, ensure_ascii=False, indent=2)
                tool_results_str += f"\n\n## Báo giá đã lưu:\n{quotes_str}"
            
            prompt = FINAL_RESPONDER_PROMPT_TOOL_RESULTS.format(
                history_summary=history_summary,
                tool_results=tool_results_str
            )
            
        elif quotes:
            # No new tool results but we have historical quotes
            quotes_str = json.dumps(quotes, ensure_ascii=False, indent=2)
            prompt = f"""<system>
Bạn là một AI tư vấn viên chuyên nghiệp của DBplus. 

## Bối cảnh
- **Lịch sử hội thoại:** {history_summary}
- **Yêu cầu người dùng:** {user_input}

## Báo giá đã có từ các lần tra cứu trước:
{quotes_str}

## Hướng dẫn phản hồi
- Nếu người dùng hỏi lại về hạng mục đã có báo giá, trình bày lại thông tin đó
- Nếu người dùng hỏi về hạng mục mới, thông báo cần thêm thông tin để báo giá
- Luôn thân thiện và chuyên nghiệp
- Đề xuất các bước tiếp theo nếu cần

Hãy trả lời người dùng dựa trên context trên.
</system>"""
            
        else:
            # Direct response without tool results
            prompt = FINAL_RESPONDER_PROMPT_DIRECT_RESPONSE.format(
                history_summary=history_summary,
                response_reason=response_reason
            )
        
        llm = MODELS["LLM_RESPONDER"]
        response = await llm.ainvoke(prompt)
        
        # Log API call with enhanced context
        log_api_call(
            node_name="responder",
            prompt=prompt,
            response=response.content,
            additional_info={
                "has_tool_results": bool(tool_results),
                "response_reason": response_reason,
                "history_summary_length": len(history_summary),
                "user_input": user_input,
                "quotes_count": len(quotes),
                "results_analysis": results_analysis,
                "budget": budget,
                "area_map_size": len(area_map)
            }
        )
        
        # Create final message
        all_messages = list(messages)
        all_messages.append(AIMessage(content=response.content))
        
        return {"messages": all_messages}
        
    except Exception as e:
        print(f"Error in responder node: {e}")
        
        # Fallback response
        fallback_message = "Xin lỗi, có lỗi xảy ra khi xử lý phản hồi. Vui lòng thử lại hoặc cung cấp thêm thông tin."
        
        if response_reason:
            fallback_message = f"Dựa trên yêu cầu của bạn: {response_reason}"
        elif user_input:
            fallback_message = f"Tôi đã nhận được yêu cầu '{user_input}' của bạn. Vui lòng cung cấp thêm thông tin để tôi có thể hỗ trợ tốt hơn."
        
        all_messages = list(messages)
        all_messages.append(AIMessage(content=fallback_message))
        
        return {"messages": all_messages}
