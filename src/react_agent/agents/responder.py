"""Responder agent for the AI interior design quotation system."""

import json
from typing import Dict, Any, List

from langchain_core.messages import AIMessage

from ..prompts import FINAL_RESPONDER_PROMPT_TOOL_RESULTS, FINAL_RESPONDER_PROMPT_DIRECT_RESPONSE
from ..utils import load_chat_model
from ..configuration import Configuration

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
    """Convert tool results to a string for the prompt."""
    if not tool_results:
        return ""
    
    parts = []
    for res in tool_results:
        if isinstance(res, str):
            parts.append(res)
        elif isinstance(res, list):
            # Nếu là list các dict (ví dụ kết quả search), chuyển thành markdown table hoặc JSON
            if res and isinstance(res[0], dict):
                # Markdown table
                headers = res[0].keys()
                table = '| ' + ' | '.join(headers) + ' |\n'
                table += '| ' + ' | '.join(['---'] * len(headers)) + ' |\n'
                for item in res:
                    row = '| ' + ' | '.join(str(item.get(h, '')) for h in headers) + ' |'
                    table += row + '\n'
                parts.append(table)
            else:
                parts.append(json.dumps(res, ensure_ascii=False, indent=2))
        elif isinstance(res, dict):
            # Handle the new format with subtask information
            if "subtask" in res and "result" in res:
                subtask = res["subtask"]
                result = res["result"]
                parts.append(f"Subtask: {subtask}\nResult: {result}")
            else:
                parts.append(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            parts.append(str(res))
    return '\n\n'.join(parts)

async def responder_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node that provides the final response."""
    print("---NODE: Responder---")
    
    messages = state["messages"]
    tool_results = state.get("tool_results")
    response_reason = state.get("response_reason", "")
    chat_history = _format_history(messages)
    
    if not tool_results:
        tool_results = []
    if tool_results:
        # Sử dụng hàm helper để chuẩn hóa tool_results thành string
        tool_results_str = str(_stringify_tool_results(tool_results))
        assert isinstance(tool_results_str, str), f"tool_results_str is not string: {type(tool_results_str)}"
        tool_results_str = tool_results_str.replace('{', '{{').replace('}', '}}')
        prompt = FINAL_RESPONDER_PROMPT_TOOL_RESULTS.format(
            chat_history=chat_history,
            tool_results=tool_results_str
        )
    else:
        prompt = FINAL_RESPONDER_PROMPT_DIRECT_RESPONSE.format(
            chat_history=chat_history,
            response_reason=response_reason
        )
    
    llm = MODELS["LLM_RESPONDER"]
    response = await llm.ainvoke(prompt)
    
    all_messages = list(messages)
    all_messages.append(AIMessage(content=response.content))
    
    return {"messages": all_messages}
