"""Planner agent for the AI interior design quotation system."""

import json
import re
from typing import Dict, Any, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from ..prompts import STRATEGIST_PROMPT, SUMMARIZER_PROMPT
from ..utils import load_chat_model
from ..configuration import Configuration
from ..new_tools import TOOLS, _parse_image_report_to_area_map

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

def _parse_area_map_from_message(content: str) -> Dict[str, Any]:
    """Parses a pre-processed message to extract a detailed area_map."""
    area_map = {}
    # Regex patterns now account for optional dimension descriptions like (dài 8m)
    patterns = {
        "sàn": r"- Diện tích sàn: ([\d.]+)m²",
        "trần": r"- Diện tích trần: ([\d.]+)m²",
        "tường 1": r"- Diện tích tường 1(?: \(.*\))?: ([\d.]+)m²",
        "tường 2": r"- Diện tích tường 2(?: \(.*\))?: ([\d.]+)m²",
        "tường 3": r"- Diện tích tường 3(?: \(.*\))?: ([\d.]+)m²",
        "tường 4": r"- Diện tích tường 4(?: \(.*\))?: ([\d.]+)m²",
    }
    
    for surface, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            area_map[surface] = {"area": f"{match.group(1)}m²"}

    return area_map

async def history_summarizer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Summarizes the chat history to simplify context for the planner."""
    print("---NODE: History Summarizer---")
    messages = state["messages"]
    if len(messages) <= 1:
        return {"history_summary": "Không có lịch sử.", "area_map": {}}
        
    chat_history_str = _format_history(messages)
    
    # Kiểm tra có image report không
    image_report = None
    for msg in messages:
        if hasattr(msg, 'content') and "[Image Analysis Report]:" in msg.content:
            image_report = msg.content.replace("[Image Analysis Report]:", "").strip()
            print(f"DEBUG: Found image report in history summarizer")
            break
    
    if image_report:
        chat_history_str += f"\n\nImage Analysis Report:\n{image_report}"
    
    prompt = SUMMARIZER_PROMPT.format(chat_history=chat_history_str)
    llm = MODELS["LLM_PLANNER"]
    response = await llm.ainvoke(prompt)
    
    summary = response.content
    print(f"Generated History Summary: {summary}")
    
    # Extract area_map from image report if available
    area_map = {}
    if image_report:
        try:
            # Parse the image report to extract area map
            parsed_result = _parse_image_report_to_area_map(image_report)
            # The function returns a dict with surfaces, we need to extract the surfaces
            if isinstance(parsed_result, dict) and 'surfaces' in parsed_result:
                area_map = parsed_result['surfaces']
            print(f"Extracted area map: {area_map}")
        except Exception as e:
            print(f"Error parsing image report to area map: {e}")
    
    return {"history_summary": summary, "area_map": area_map}

async def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """The planner node that decides the course of action and creates a plan."""
    print("---NODE: Planner---")
    user_input = state["messages"][-1].content
    history_summary = state.get("history_summary", "Không có tóm tắt.")
    
    # Get area_map from state (extracted by history_summarizer)
    area_map = state.get("area_map", {})
    
    tools_description = "\n".join([f"- {name}: {tool.__doc__}" for name, tool in TOOLS.items()])

    prompt = STRATEGIST_PROMPT.format(
        user_input=user_input,
        history_summary=history_summary,
        tools=tools_description,
    )
    
    # If we have an area_map, add it to the prompt to inform the planner
    if area_map:
        area_map_str = "\n".join([f"- {k}: {v}" for k, v in area_map.items()])
        prompt += f"\n\nArea Map:\n{area_map_str}"
    
    llm = MODELS["LLM_PLANNER"]
    response = await llm.ainvoke(prompt)
    raw_response_text = response.content
    print(f"LLM Raw Response for Planner: {raw_response_text}")

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
            plan = parsed_json.get("plan", [])
            return {"plan": plan}
        else:
            print("Error: No valid JSON object found in the planner response. Defaulting to no plan.")
            return {"plan": []}
            
    except Exception as e:
        print(f"An unexpected error occurred during JSON parsing: {e}")
        return {"plan": []}
