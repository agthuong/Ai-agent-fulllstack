import json
import re
from typing import Dict, Any, Literal
import traceback
import asyncio

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from langchain_core.prompts import ChatPromptTemplate

from .state import State
from .prompts import (
    STRATEGIST_PROMPT,
    FINAL_RESPONDER_PROMPT_TOOL_RESULTS,
    FINAL_RESPONDER_PROMPT_DIRECT_RESPONSE,
    SUMMARIZER_PROMPT,
)
from .utils import load_chat_model
from .configuration import Configuration
from .tools import TOOLS, execute_tool

# Load models once at the module level
config = Configuration.from_context()
MODELS = {
    "LLM_STRATEGIST": load_chat_model(config.model),  # Main powerful model for routing
    "LLM_RESPONDER": load_chat_model(config.model)  # Main model for final responses
}

def _format_history(messages: list) -> str:
    """Helper to format the history for the prompt."""
    if not messages:
        return "No history."
    # A simple formatting for now, can be improved later.
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

async def history_summarizer_node(state: State) -> Dict[str, Any]:
    """Summarizes the chat history to simplify context for the strategist."""
    print("---NODE: History Summarizer---")
    messages = state["messages"]
    if len(messages) <= 1:
        return {"history_summary": "Không có lịch sử."}
        
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
    llm = MODELS["LLM_RESPONDER"]
    response = await llm.ainvoke(prompt)
    
    summary = response.content
    print(f"Generated History Summary: {summary}")
    
    return {"history_summary": summary}


async def strategist_node(state: State) -> Dict[str, Any]:
    """The 'master planner' node that decides the course of action."""
    print("---NODE: Strategist---")
    user_input = state["messages"][-1].content
    history_summary = state.get("history_summary", "Không có tóm tắt.")
    
    # Debug: Kiểm tra có image report không
    image_report = None
    for msg in state["messages"]:
        if hasattr(msg, 'content') and "[Image Analysis Report]:" in msg.content:
            image_report = msg.content
            print(f"DEBUG: Found image report in messages")
            break
    
    tools_description = "\n".join([f"- {name}: {tool.__doc__}" for name, tool in TOOLS.items()])

    prompt = STRATEGIST_PROMPT.format(
        user_input=user_input,
        history_summary=history_summary,
        tools=tools_description,
    )
    
    # Nếu có image report, thêm vào prompt
    if image_report:
        prompt += f"\n\nImage Analysis Report:\n{image_report}"
    
    llm = MODELS["LLM_STRATEGIST"]
    response = await llm.ainvoke(prompt)
    raw_response_text = response.content
    print(f"LLM Raw Response for Strategist: {raw_response_text}")

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
            print("Error: No valid JSON object found in the strategist response. Defaulting to no plan.")
            return {"plan": []}
            
    except Exception as e:
        print(f"An unexpected error occurred during JSON parsing: {e}")
        return {"plan": []}

async def tool_executor_node(state: State) -> Dict[str, Any]:
    """Executes the planned tools and collects results."""
    print("---NODE: Tool Executor---")
    
    plan = state.get("plan", [])
    if not plan:
        return {"tool_results": []}
    
    results_list = []
    
    try:
        for tool_call in plan:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            
            if tool_name and tool_name in TOOLS:
                print(f"--- QUEUING: {tool_name} with args {tool_args} ---")
                result = await execute_tool(tool_name, tool_args)
                results_list.append(result)
            else:
                error_msg = f"Tool '{tool_name}' not found or invalid."
                results_list.append(error_msg)
        
        return {"tool_results": results_list}
    except Exception as e:
        print(f"Error during tool execution: {e}")
        return {"tool_results": [f"An error occurred during tool execution: {e}"]}


def _stringify_tool_results(tool_results):
    """
    Chuyển tool_results (list) thành một string duy nhất để truyền vào prompt.
    - Nếu phần tử là string, giữ nguyên.
    - Nếu phần tử là list các dict, chuyển thành markdown hoặc JSON string.
    - Nếu phần tử là dict, chuyển thành JSON string.
    """
    import json
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
            parts.append(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            parts.append(str(res))
    return '\n\n'.join(parts)

async def final_responder_node(state: State) -> Dict[str, Any]:
    """Node that provides the final response."""
    print("---NODE: Final Responder---")
    
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


def should_execute_tools(state: State) -> Literal["tool_executor", "final_responder"]:
    """Conditional edge based on the plan."""
    print(f"---ROUTING: Based on plan---")
    if state.get("plan"):
        print("Decision: Execute tools.")
        return "tool_executor"
    print("Decision: Generate final response.")
    return "final_responder"

def create_graph():
    """Creates the LangGraph instance with all the nodes and edges."""
    
    builder = StateGraph(State)
    
    builder.add_node("history_summarizer", history_summarizer_node)
    builder.add_node("strategist", strategist_node)
    builder.add_node("tool_executor", tool_executor_node)
    builder.add_node("final_responder", final_responder_node)
    
    builder.set_entry_point("history_summarizer")
    builder.add_edge("history_summarizer", "strategist")
    
    builder.add_conditional_edges(
        "strategist",
        should_execute_tools,
        {
            "tool_executor": "tool_executor",
            "final_responder": "final_responder",
        }
    )
    
    builder.add_edge("tool_executor", "final_responder")
    builder.add_edge("final_responder", END)
    
    print("[DEBUG] Compiling graph with new standardized and robust architecture.")
    return builder.compile()

# Initialize the graph instance
graph = create_graph()