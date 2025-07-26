import json
import re
from typing import Dict, Any, Literal
import traceback

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.prebuilt import ToolNode

from .state import State
from .prompts import (
    STRATEGIST_ROUTER_PROMPT,
    EXECUTOR_AGENT_PROMPT,
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
    "LLM_EXECUTOR": load_chat_model(config.fast_model),  # Faster model for execution
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
            # Use the specific surface key ('sàn', 'trần', 'tường 1', etc.)
            # to preserve individual areas. This is crucial for applying
            # different materials to different walls.
            area_map[surface] = {"area": f"{match.group(1)}m²"}

    return area_map

async def history_summarizer_node(state: State) -> Dict[str, Any]:
    """Summarizes the chat history to simplify context for the strategist."""
    print("---NODE: History Summarizer---")
    messages = state["messages"]
    if len(messages) <= 1:
        # No history to summarize
        return {"history_summary": "Không có lịch sử."}
        
    chat_history_str = _format_history(messages)
    
    prompt = SUMMARIZER_PROMPT.format(chat_history=chat_history_str)
    llm = MODELS["LLM_EXECUTOR"] # Use the faster model for summarization
    response = await llm.ainvoke(prompt)
    
    summary = response.content
    print(f"Generated History Summary: {summary}")
    
    return {"history_summary": summary}


async def strategist_router_node(state: State) -> Dict[str, Any]:
    """
    Decides the next step and extracts necessary context for the executor.
    """
    print("---NODE: Strategist Router---")
    messages = state["messages"]
    user_input = messages[-1].content
    # Use the summary from the new node
    history_summary = state.get("history_summary", "Không có tóm tắt.")

    # 1. Decide on the route
    prompt = STRATEGIST_ROUTER_PROMPT.format(
        user_input=user_input,
        history_summary=history_summary,
    )
    llm = MODELS["LLM_STRATEGIST"]
    response = await llm.ainvoke(prompt)
    print(f"LLM Raw Response for Strategist: {response.content}")

    try:
        # Improved JSON Extraction Logic
        json_str = None
        # Pattern 1: Find JSON within a markdown code block
        match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', response.content)
        if match:
            json_str = match.group(1)
            print("[DEBUG] Found JSON in markdown code block.")
        else:
            # Pattern 2: Find the first and last curly brace to extract the JSON object
            match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if match:
                json_str = match.group(0)
                print("[DEBUG] Found JSON by searching for curly braces.")

        if not json_str:
            raise ValueError("No JSON object found in the LLM response.")
        
        decision_json = json.loads(json_str)
        decision = decision_json.get("decision")

        # 2. If executing tools, extract context
        if decision == "EXECUTE_TOOL":
            context_for_executor = {}
            
            # Find and extract image report from history
            image_report = next((msg.content for msg in reversed(state["messages"]) if isinstance(msg, SystemMessage) and "Image Analysis Report" in msg.content), None)
            if image_report:
                # Normalize the report's position names to align with area_map keys ('tường 1', etc.)
                # This acts as a "translator" between the descriptive vision model output
                # and the structured area_map from the parser.
                
                # First, strip all parenthetical notes like (phán đoán)
                normalized_report = re.sub(r'\s*\(.*\)', '', image_report)

                # Next, map descriptive wall names to programmatic names
                normalization_map = {
                    r"tường trái": "tường 1",
                    r"tường phải": "tường 2",
                    r"tường đối diện": "tường 3",
                    # Match both 'tường sau lưng' and 'tường sau lưỡng' for typo robustness
                    r"tường sau lư(?:ng|ỡng)": "tường 4",
                }
                for pattern, replacement in normalization_map.items():
                    normalized_report = re.sub(pattern, replacement, normalized_report)
                
                context_for_executor["image_report"] = normalized_report
                print("Extracted and normalized image_report for executor.")
            else:
                 print("No image_report found in history for executor.")

            # Find budget in the latest user message
            user_input = state["messages"][-1].content
            budget_pattern = r'(\d+(?:\.\d+)?)\s*(tỷ|tỉ|tr|triệu)'
            budget_match = re.search(budget_pattern, user_input, re.IGNORECASE)
            if budget_match:
                amount_str = budget_match.group(1)
                unit = budget_match.group(2).lower()
                
                # Pass budget as a simple string for the LLM to understand easily
                context_for_executor["budget"] = f"{amount_str} {unit}"
                print(f"Extracted budget for executor: {context_for_executor['budget']}")
            
            # --- AREA MAP LOGIC WITH MEMORY ---
            # 1. Check if area_map already exists in the state from a previous turn.
            final_area_map = state.get("area_map")
            
            # 2. If not in state, try to parse it from the current user message.
            if not final_area_map:
                parsed_map = _parse_area_map_from_message(user_input)
                if parsed_map:
                    final_area_map = parsed_map
                    print(f"Parsed new area_map from user input: {final_area_map}")

            # 3. If we have an area_map (from state or new parse), add it to context.
            if final_area_map:
                context_for_executor["area_map"] = final_area_map
                print(f"Using area_map for executor: {final_area_map}")
            
            return {
                "decision": "EXECUTE_TOOL",
                "task_description": decision_json.get("task_description"),
                "context_for_executor": json.dumps(context_for_executor, ensure_ascii=False),
                "area_map": final_area_map, # Persist to state for next turn
                "tool_results": None, # Clear previous tool results
                "response_reason": None, # Clear previous reason
            }
        else: # decision == "GENERATE_RESPONSE"
            return {
                "decision": "GENERATE_RESPONSE",
                "response_reason": decision_json.get("reason"),
                "tool_results": None, # Clear previous tool results
            }

    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error parsing strategist decision: {e}. Defaulting to GENERATE_RESPONSE.")
        return {
            "decision": "GENERATE_RESPONSE",
            "response_reason": f"Lỗi xử lý đầu ra của mô hình: {e}",
            "tool_results": None,
        }

async def executor_agent_node(state: State) -> Dict[str, Any]:
    """Node in charge of tool execution."""
    print("---NODE: Executor Agent---")
    
    # Extract context from the Strategist
    context_for_executor = json.loads(state.get("context_for_executor", "{}"))
    image_report = context_for_executor.get("image_report", "")
    budget = context_for_executor.get("budget", "")
    area_map = context_for_executor.get("area_map", {})
    
    # Print debug info about the received context
    print(f"[DEBUG] Executor received context: image_report={bool(image_report)}, budget={budget}, area_map={area_map}")
    
    # 1. Decide which tool(s) to use
    executor_prompt = EXECUTOR_AGENT_PROMPT.format(
        task_description=state.get("task_description", ""),
        tools="\n".join([f"- {name}: {tool.__doc__}" for name, tool in TOOLS.items()]),
        context=json.dumps(context_for_executor, ensure_ascii=False)
    )
    
    llm = MODELS["LLM_EXECUTOR"]
    response = await llm.ainvoke(executor_prompt)
    print(f"LLM Raw Response for Executor: {response.content}")
    
    # 2. Extract tool calls
    try:
        content = response.content
        
        # Phương pháp 1: Tìm JSON hoàn chỉnh với regex chính xác hơn
        json_str = None
        # Tìm JSON đầy đủ (full JSON object từ { đến })
        full_json_match = re.search(r'(\{[\s\S]*"tool_calls"[\s\S]*\})', content)
        if full_json_match:
            json_str = full_json_match.group(1)
            print(f"[DEBUG] Found JSON using full object match")
        
        # Phương pháp 2: Tìm trong code block
        if not json_str:
            code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
            if code_block_match:
                json_str = code_block_match.group(1).strip()
                print(f"[DEBUG] Found JSON in code block")
        
        # Phương pháp 3: EMERGENCY MODE - Thủ công tái tạo JSON từ thông tin có sẵn
        if not json_str or "tool_calls" not in json_str:
            # Trong trường hợp khẩn cấp, tạo tool_call thủ công từ context
            print(f"[DEBUG] EMERGENCY MODE: Creating tool_call manually from context")
            emergency_tool_call = {
                "tool_calls": [
                    {
                        "name": "quote_materials",
                        "args": {
                            "image_report": image_report,
                            "budget": budget,
                            "area_map": area_map
                        }
                    }
                ]
            }
            json_str = json.dumps(emergency_tool_call)
        
        # Parse JSON
        try:
            print(f"[DEBUG] Attempting to parse JSON: {json_str[:100]}...")
            parsed_json = json.loads(json_str)
            tool_calls = parsed_json.get("tool_calls", [])
            
            # Bổ sung thông tin quan trọng vào args nếu thiếu
            for tool_call in tool_calls:
                if tool_call.get("name") == "quote_materials":
                    args = tool_call.get("args", {})
                    # Đảm bảo budget và area_map luôn có
                    if "budget" not in args and budget:
                        args["budget"] = budget
                        print(f"[DEBUG] Added missing budget to tool args")
                    if "area_map" not in args and area_map:
                        args["area_map"] = area_map  
                        print(f"[DEBUG] Added missing area_map to tool args")
                    tool_call["args"] = args
            
            print(f"[DEBUG] Successfully parsed {len(tool_calls)} tool calls")
        except json.JSONDecodeError as e:
            print(f"[DEBUG] JSON parse error: {e}")
            # Fallback to emergency mode
            print(f"[DEBUG] Fallback to emergency tool call")
            tool_calls = [{
                "name": "quote_materials",
                "args": {
                    "image_report": image_report,
                    "budget": budget,
                    "area_map": area_map
                }
            }]
        
        if not tool_calls:
            raise ValueError("No tool calls found in parsed JSON")
        
        # 3. Execute the tools
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            
            print(f"--- TOOL: {tool_name} ---")
            result = execute_tool(tool_name, tool_args)
            results.append(result)
        
        # Synthesize the tool results
        synthesized_result = '\n'.join(results)
        print(f"Synthesized tool results: {synthesized_result[:200]}...")
        print(f"[DEBUG] Executor completed, tool_results length: {len(synthesized_result)} characters")
        print(f"[DEBUG] Tool results sample: {synthesized_result[:100]}...")
        
        # Tạo state mới để trả về
        new_state = {
            "tool_results": synthesized_result,
            "decision": state.get("decision", "EXECUTE_TOOL")  # Đảm bảo decision được giữ nguyên
        }
        
        # In ra state trước khi trả về
        print(f"[DEBUG] Executor returning state keys: {list(new_state.keys())}")
        print(f"[DEBUG] Executor tool_results length: {len(new_state['tool_results'])}")
        
        # Trả về cả tool_results và decision để đảm bảo final_responder nhận được đúng thông tin
        return new_state
    
    except Exception as e:
        error_msg = f"Error executing tool: {str(e)}"
        print(f"Error in executor agent: {str(e)}")
        print(f"[DEBUG] Executor FAILED, exception: {repr(e)}")
        traceback_str = traceback.format_exc()
        print(f"[DEBUG] Traceback: {traceback_str}")
        
        # LAST RESORT: Khi mọi thứ thất bại, tạo phản hồi "tử tế" để không làm gián đoạn luồng
        try:
            print(f"[DEBUG] LAST RESORT: Attempting direct tool execution")
            emergency_result = execute_tool("quote_materials", {
                "image_report": image_report,
                "budget": budget,
                "area_map": area_map
            })
            return {
                "tool_results": emergency_result,
                "decision": state.get("decision", "EXECUTE_TOOL")  # Đảm bảo decision được giữ nguyên
            }
        except:
            return {
                "tool_results": "Không thể tạo báo giá do lỗi kỹ thuật. Vui lòng thử lại sau.",
                "decision": state.get("decision", "EXECUTE_TOOL")  # Đảm bảo decision được giữ nguyên
            }


async def final_responder_node(state: State) -> Dict[str, Any]:
    """Node that provides the final response."""
    print("---NODE: Final Responder---")
    print(f"[DEBUG] Final Responder starting with state keys: {list(state.keys())}")
    
    # Thêm debug để kiểm tra nội dung đầy đủ của state
    for key, value in state.items():
        if key != "messages":  # Tránh in quá nhiều dữ liệu
            print(f"[DEBUG] State[{key}] = {str(value)[:100]}{'...' if len(str(value)) > 100 else ''}")
    
    # Extract the necessary components from the state
    messages = state["messages"]
    decision = state.get("decision", "")
    
    # Set up the tool_results information
    tool_results = state.get("tool_results")
    tool_results_len = len(tool_results) if tool_results is not None else 0
    print(f"[DEBUG] Final Responder received tool_results ({tool_results_len} chars): {tool_results[:100] if tool_results else '...'}")
    
    # Set up the response_reason information
    response_reason = state.get("response_reason", "")
    chat_history = _format_history(messages)
    
    # Determine prompt based on decision and tool_results
    if decision == "EXECUTE_TOOL" and tool_results:
        print(f"[DEBUG] Using TOOL_RESULTS prompt with {len(tool_results)} chars of tool results")
        prompt = FINAL_RESPONDER_PROMPT_TOOL_RESULTS.format(
            chat_history=chat_history,
            tool_results=tool_results
        )
    else:
        print(f"[DEBUG] Using DIRECT_RESPONSE prompt with reason: {response_reason[:50] if response_reason else ''}...")
        prompt = FINAL_RESPONDER_PROMPT_DIRECT_RESPONSE.format(
            chat_history=chat_history,
            response_reason=response_reason
        )
    
    # Get the response from the LLM
    llm = MODELS["LLM_RESPONDER"]
    response = await llm.ainvoke(prompt)
    print(f"[DEBUG] Final Responder generated response: {response.content[:100]}...")
    
    # Add the response to the messages
    all_messages = list(messages)
    all_messages.append(AIMessage(content=response.content))
    
    return {"messages": all_messages}


def should_execute_tools(state: State) -> Literal["executor_agent_node", "final_responder_node"]:
    """Conditional edge logic."""
    print(f"---ROUTING: Based on decision '{state['decision']}'---")
    if state["decision"] == "EXECUTE_TOOL":
        return "executor_agent_node"
    return "final_responder_node"

def create_graph():
    """Creates the LangGraph instance with all the nodes and edges."""
    
    # Create the graph with State as the type
    builder = StateGraph(State)
    
    # Add our nodes
    builder.add_node("history_summarizer", history_summarizer_node)
    builder.add_node("strategist_router", strategist_router_node)
    builder.add_node("executor_agent", executor_agent_node)
    builder.add_node("final_responder", final_responder_node)
    
    # Set entry point
    builder.set_entry_point("history_summarizer")
    
    # Connect summarizer to strategist
    builder.add_edge("history_summarizer", "strategist_router")

    # Define edges with conditions using add_conditional_edges
    builder.add_conditional_edges(
        "strategist_router",
        lambda state: state["decision"],
        {
            "EXECUTE_TOOL": "executor_agent",
            "GENERATE_RESPONSE": "final_responder"
        }
    )
    
    # Connect executor to final_responder
    print("[DEBUG] Adding edge from executor_agent to final_responder")
    builder.add_edge("executor_agent", "final_responder")
    
    # Mark final_responder as the end node
    builder.add_edge("final_responder", END)
    
    # Compile the graph
    print("[DEBUG] Compiling graph with new summarizer node.")
    return builder.compile()

# Initialize the graph instance
graph = create_graph() 