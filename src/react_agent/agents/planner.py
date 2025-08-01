"""Planner agent for the AI interior design quotation system."""

import json
import re
from typing import Dict, Any, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from ..prompts import STRATEGIST_PROMPT, SUMMARIZER_PROMPT
from ..utils import load_chat_model
from ..configuration import Configuration
from ..new_tools import TOOLS  # removed _parse_image_report_to_area_map
from ..debug_utils import log_api_call

# Load models once at the module level
config = Configuration.from_context()
MODELS = {
    "LLM_PLANNER": load_chat_model(config.model),  # Main powerful model for planning
}


def _format_history(messages: list) -> str:
    """Helper to format the history for the prompt."""
    if not messages:
        return "No history."
    # A simple formatting for now, can be improved later
    return "\n".join([f"{msg.type}: {msg.content}" for msg in messages])


async def history_summarizer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Summarizes the chat history to simplify context for the planner.

    NOTE: Image report is intentionally ignored per requirement.
    """
    print("---NODE: History Summarizer---")
    messages = state["messages"]
    if len(messages) <= 1:
        return {"history_summary": "Không có lịch sử.", "area_map": {}}

    chat_history_str = _format_history(messages)

    # ❌ Removed: Any extraction/augmentation from image report
    # We do NOT append image-derived materials info to the summary.

    prompt = SUMMARIZER_PROMPT.format(chat_history=chat_history_str)
    llm = MODELS["LLM_PLANNER"]
    response = await llm.ainvoke(prompt)

    summary = response.content
    print(f"Generated History Summary: {summary}")
    
    # Parse the summary to extract area_map and other info
    try:
        # Find JSON in the response
        start_idx = summary.find('{')
        end_idx = summary.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = summary[start_idx:end_idx]
            parsed_summary = json.loads(json_str)
            
            # Extract components
            events_summary = parsed_summary.get("events_summary", [])
            budget = parsed_summary.get("budget")
            area_map = parsed_summary.get("area_map", [])
            
            # Convert area_map list to dict for easier access
            area_map_dict = {}
            for item in area_map:
                position = item.get("position", "")
                area_map_dict[position] = item
            
            return {
                "history_summary": summary,
                "area_map": area_map_dict,
                "budget": budget,
                "events_summary": events_summary
            }
        else:
            print("Warning: Could not parse JSON from history summary")
            return {"history_summary": summary, "area_map": {}}
    except json.JSONDecodeError as e:
        print(f"Error parsing history summary JSON: {e}")
        return {"history_summary": summary, "area_map": {}}
    
    # Log API call
    log_api_call(
        node_name="history_summarizer",
        prompt=prompt,
        response=response.content,
        additional_info={
            "chat_history_length": len(chat_history_str),
            "messages_count": len(messages)
        }
    )

async def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """The planner node that decides the course of action and creates a plan.

    NOTE: Planner is not given any image report info.
    """
    print("---NODE: Planner---")
    
    # Get the actual user input (not image report)
    messages = state["messages"]
    user_input = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == 'human':
            content = msg.content
            # Skip image reports, get actual user input
            if not content.startswith('[Image Analysis Report]') and not content.startswith('## VAI TRÒ'):
                user_input = content
                break
    
    if not user_input:
        user_input = "Không có yêu cầu cụ thể từ người dùng."
    
    # Get history_summary from state (parsed by history_summarizer)
    history_summary = state.get("history_summary", "Không có tóm tắt.")
    
    # Extract budget and area_map from state
    budget = state.get("budget")
    area_map = state.get("area_map", {})


    prompt = STRATEGIST_PROMPT.format(
        user_input=user_input,
        history_summary=history_summary
    )

    # If we have an area_map, add it to the prompt to inform the planner
    if area_map:
        area_map_str = "\n".join([f"- {k}: {v}" for k, v in area_map.items()])
        prompt += f"\n\nArea Map:\n{area_map_str}"
        
        # Add budget information if available
        if budget:
            prompt += f"\n\nBudget: {budget:,} VND"

    llm = MODELS["LLM_PLANNER"]
    response = await llm.ainvoke(prompt)
    raw_response_text = response.content
    print(f"LLM Raw Response for Planner: {raw_response_text}")
    
    # Log API call
    log_api_call(
        node_name="planner",
        prompt=prompt,
        response=response.content,
        additional_info={
            "user_input": user_input,
            "area_map": area_map,
            "budget": budget
        }
    )

    try:
        valid_json_strings: List[str] = []
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
            plan = parsed_json.get("plan", [])
            response_reason = parsed_json.get("response_reason", "")

            if plan:
                return {"plan": plan}
            else:
                return {"plan": [], "response_reason": response_reason}
        else:
            print("Error: No valid JSON object found in the planner response. Defaulting to no plan.")
            return {"plan": [], "response_reason": "Không thể parse được response từ Planner."}

    except Exception as e:
        print(f"An unexpected error occurred during JSON parsing: {e}")
        return {"plan": [], "response_reason": f"Lỗi khi parse JSON: {e}"}
