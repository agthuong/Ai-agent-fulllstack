"""
Main graph definition for the Simplified Agent.
This graph orchestrates the flow between a central router and two main paths:
a single-step tool call or a multi-step ReAct plan.
"""
import json
import re
from typing import Dict, Any, Literal, List, Optional, Tuple, Union, cast

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, ToolMessage, ToolCall, SystemMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from react_agent.configuration import Configuration
from react_agent.state import State
from react_agent.tools import TOOLS, get_available_materials_string # Unified tools
from react_agent.utils import load_chat_model, cleanup_llm_output
from react_agent.prompts import (
    CENTRAL_ROUTER_PROMPT, RESPONSE_PROMPT, PLAN_PROMPT, EXECUTOR_PROMPT,
    CONVERSE_PROMPT
)

def _format_history_for_prompt(messages: list) -> str:
    """Format the conversation history for inclusion in prompts."""
    history_lines = []
    
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history_lines.append(f"USER: {msg.content}")
        elif isinstance(msg, AIMessage):
            content = msg.content
            # Skip the internal planning sections
            if "<think>" in content.lower():
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            history_lines.append(f"ASSISTANT: {content}")
        elif isinstance(msg, SystemMessage):
            if "[Image Analysis Report]:" in msg.content:
                # Hiển thị đầy đủ Image Analysis Report
                report_content = msg.content.replace("[Image Analysis Report]:", "").strip()
                history_lines.append(f"SYSTEM: [Image Analysis Report]: {report_content}")
            elif "[Quote Parameters]:" in msg.content or "[Quote Parameters" in msg.content:
                # Extract and parse quote parameters
                try:
                    # Strip the prefix
                    params_text = re.sub(r'\[Quote Parameters\]?:?\s*', '', msg.content).strip()
                    # Try to parse as JSON
                    params_dict = json.loads(params_text)
                    
                    # Create a friendly display version of the quote parameters
                    history_lines.append("SYSTEM: [Previous Quote Parameters]")
                    
                    # Extract and display area_map
                    if "area_map" in params_dict:
                        history_lines.append("AREAS PROVIDED:")
                        for surface, details in params_dict["area_map"].items():
                            material = details.get("material_type", "")
                            mat_type = f", type: {details.get('type', 'not specified')}" if "type" in details else ""
                            area = details.get("area", "")
                            history_lines.append(f"- {surface}: {material}{mat_type}, area: {area}")
                    
                    # Extract and display budget
                    if "budget" in params_dict:
                        history_lines.append(f"BUDGET: {params_dict['budget']}")
                    
                    # Extract and display material_list
                    if "material_list" in params_dict:
                        history_lines.append("MATERIALS REQUESTED:")
                        for material in params_dict["material_list"]:
                            mat_type = material.get("type", "not specified")
                            mat_name = material.get("material_type", "unknown")
                            history_lines.append(f"- {mat_name}, type: {mat_type}")
                    
                except (json.JSONDecodeError, ValueError) as e:
                    # Fall back to displaying a simplified version
                    history_lines.append(f"SYSTEM: [Previous Quote Parameters available]")
                    print(f"Error parsing quote parameters: {e}")
            else:
                history_lines.append(f"SYSTEM: {msg.content}")
        else:
            # Handle other message types
            history_lines.append(f"{msg.type}: {msg.content}")
    
    # Return the formatted history as a string
    return "\n".join(history_lines)

def _parse_image_report_for_memory(report_text: Optional[str]) -> List[Dict[str, Optional[str]]]:
    """
    A self-contained and robust helper to parse the image report string for memory saving.
    It processes the report line by line to handle multi-line inputs correctly.
    """
    if not isinstance(report_text, str):
        return []
    
    items = []
    # This simpler regex parses a single line of the report.
    line_pattern = re.compile(
        r"Material:\\s*(?P<material>.*?)\\s*-\\s*Type:\\s*(?P<type>.*?)\\s*-\\s*Position:\\s*(?P<position>.+)"
    )

    for line in report_text.strip().split('\n'):
        match = line_pattern.match(line.strip())
        if not match:
            continue

        material_type = match.group('material').strip()
        specific_type = match.group('type').strip()
        # Clean the position string by removing any trailing " - InStock..." part.
        position_full = match.group('position').strip()
        position = position_full.split(' - InStock:')[0].strip()

        final_type = specific_type if specific_type.lower() not in ['null', 'none', 'không xác định'] else None
        
        items.append({
            "material_type": material_type,
            "type": final_type,
            "position": position
        })
        
    return items

def _parse_room_dimensions_to_area_map(dimensions: str, image_report: Optional[str] = None) -> Dict[str, Any]:
    """
    Parse room dimensions from text and create an area_map with materials from image_report.
    
    Args:
        dimensions: String containing room dimensions like "5x10m", "5m x 10m x 3m", etc.
        image_report: Optional image analysis report to extract materials from
        
    Returns:
        Dictionary with area_map structure
    """
    area_map = {}
    
    # Extract numbers from the dimensions string
    numbers = re.findall(r'(\d+(?:\.\d+)?)', dimensions)
    if len(numbers) < 2:
        return area_map
    
    try:
        # Try to interpret the dimensions
        if len(numbers) >= 3:
            # Assuming format: length x width x height
            length = float(numbers[0])
            width = float(numbers[1])
            height = float(numbers[2])
        elif len(numbers) == 2:
            # Assuming format: length x width
            length = float(numbers[0])
            width = float(numbers[1])
            height = 2.7  # Default ceiling height if not provided
        
        # Calculate areas
        floor_area = length * width
        ceiling_area = floor_area
        wall_area = 2 * (length + width) * height
        
        # Extract materials from image report if available
        floor_material, wall_material, ceiling_material = "gỗ", "sơn", "sơn"  # Defaults
        floor_type, wall_type, ceiling_type = None, None, None
        
        if image_report:
            materials = _parse_image_report_for_memory(image_report)
            for item in materials:
                position = item.get("position", "").lower()
                material_type = item.get("material_type")
                specific_type = item.get("type")
                
                if any(x in position for x in ["sàn", "floor", "nền"]):
                    floor_material = material_type
                    floor_type = specific_type
                elif any(x in position for x in ["tường", "wall"]):
                    wall_material = material_type
                    wall_type = specific_type
                elif any(x in position for x in ["trần", "ceiling"]):
                    ceiling_material = material_type
                    ceiling_type = specific_type
        
        # Create area map
        area_map["sàn"] = {
            "material_type": floor_material,
            "area": f"{floor_area}m2"
        }
        if floor_type:
            area_map["sàn"]["type"] = floor_type
            
        area_map["trần"] = {
            "material_type": ceiling_material,
            "area": f"{ceiling_area}m2"
        }
        if ceiling_type:
            area_map["trần"]["type"] = ceiling_type
            
        area_map["tường"] = {
            "material_type": wall_material,
            "area": f"{wall_area}m2"
        }
        if wall_type:
            area_map["tường"]["type"] = wall_type
            
        return area_map
        
    except (ValueError, IndexError) as e:
        print(f"Error parsing room dimensions: {e}")
        return area_map

async def central_router_node(state: State) -> Dict[str, Any]:
    """
    Central router node that analyzes the user's request and decides the next step.
    
    This node is responsible for:
    1. Analyzing the user's request
    2. Considering the conversation history
    3. Deciding whether to:
       - Ask for more information (converse)
       - Execute a single tool
       - Plan and execute multiple tools
    
    Args:
        state: The current state
        
    Returns:
        Updated state with routing decision
    """
    print("====== CENTRAL ROUTER START ======")
    
    # Get the current messages from the state
    messages = state.get("messages", [])
    if not messages:
        print("No messages found in state")
        return {"route": "converse", "reason": "No messages found in state"}
    
    input_message = messages[-1]
    user_input = input_message.content
    
    # Extract image report and quote parameters from history, and clean the history
    history_for_prompt = []
    image_report = None
    
    # First, check if the current message contains an image report
    if isinstance(input_message, SystemMessage) and "[Image Analysis Report]:" in input_message.content:
        image_report = input_message.content.replace("[Image Analysis Report]:", "").strip()
        print(f"FOUND IMAGE REPORT in current message: {image_report[:100]}...")
        history_messages = messages[:-1]
    else:
        history_messages = messages[:-1]

    # ALWAYS search for image report in recent history (last 5 messages) if not found in current turn
    if not image_report:
        # Get last 10 messages from history to search for image report
        recent_history = history_messages[-10:] if len(history_messages) > 10 else history_messages
        for msg in recent_history:
            if isinstance(msg, SystemMessage) and "[Image Analysis Report]:" in msg.content:
                image_report = msg.content.replace("[Image Analysis Report]:", "").strip()
                print(f"FOUND IMAGE REPORT in history: {image_report[:100]}...")
                break
    
    # Now, iterate through the "true" history to find quote parameters and build the prompt history
    quote_params_str = "No previous quote parameters found."
    quote_params_msg = None
    
    # Search through ALL history messages for quote parameters
    for msg in history_messages:
        # More flexible matching for Quote Parameters tags - match both formats
        if isinstance(msg, SystemMessage) and (
            "[Quote Parameters]:" in msg.content or 
            "[Quote Parameters" in msg.content
        ):
            # Support both new and old formats
            quote_params_str = re.sub(r'\[Quote Parameters\]?:?\s*', '', msg.content).strip()
            quote_params_msg = msg
            print(f"FOUND QUOTE PARAMETERS: {quote_params_str}")
            break
    
    # Ensure we include important context in history_for_prompt
    for msg in history_messages:
        # Skip messages we've already processed
        if msg == quote_params_msg:
            continue
            
        # Add all other messages to history
        history_for_prompt.append(msg)
    
    # Add quote parameters message at the end if found
    if quote_params_msg:
        history_for_prompt.append(quote_params_msg)
        
    chat_history = _format_history_for_prompt(history_for_prompt)

    # Thay vì chỉ gửi "Image report is available", truyền toàn bộ nội dung image_report vào prompt
    has_image_info = f"Full Image Report: {image_report}" if image_report else "No image report available."
    if image_report:
        print(f"Using image report in central router: {image_report[:100]}...")
    
    # Generate the materials catalog string to be injected into the prompt
    available_materials_str = get_available_materials_string()
    print(f"Available materials catalog: {available_materials_str}")

    # Check if user input contains room dimensions
    # Look for patterns like "5x10m", "5m x 10m x 3m", etc.
    dimensions_pattern = r'(\d+)\s*[xX×]\s*(\d+)(?:\s*[xX×]\s*(\d+))?'
    room_dimensions_match = re.search(dimensions_pattern, user_input)
    
    # Auto-generate area_map from room dimensions if found AND image report is available
    area_map_from_dimensions = None
    if room_dimensions_match and image_report:
        # Extract the dimensions from the match
        dimensions = room_dimensions_match.group(0)
        print(f"FOUND ROOM DIMENSIONS: {dimensions}")
        
        # Parse dimensions to area_map using materials from image report
        area_map_from_dimensions = _parse_room_dimensions_to_area_map(dimensions, image_report)
        if area_map_from_dimensions:
            print(f"AUTO-GENERATED AREA MAP: {json.dumps(area_map_from_dimensions, ensure_ascii=False)}")

    router_prompt_str = CENTRAL_ROUTER_PROMPT.format(
        input=input_message.content,
        chat_history=chat_history,
        image_info=has_image_info,
        quote_params=quote_params_str,
        available_materials=available_materials_str, # Inject the catalog here
        tools="\n".join([f"- {tool.name}: {tool.description}" for tool in TOOLS])
    )

    print("====== FULL ROUTER PROMPT ======")
    print(router_prompt_str)
    print("===============================")

    print("Sending prompt to router model...")
    config = Configuration.from_context()
    model = load_chat_model(config.model)
    
    response = await model.ainvoke(router_prompt_str)
    print(f"--- RAW ROUTER LLM OUTPUT ---\n{response.content}\n--------------------------")
    
    # Parse the response to get the routing decision
    try:
        # Extract the JSON part of the response
        json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")
            
        json_str = json_match.group(0)
        cleaned_response = json_str.strip()
        print(f"--- EXTRACTED JSON STRING ---\n{cleaned_response}\n--------------------------")
        
        # Parse the JSON
        decision = json.loads(cleaned_response)
        print(f"--- DEBUG: Parsed decision object: {decision}")
    except Exception as e:
        print(f"Error parsing router response: {e}")
        # Fallback to conversation mode if we can't parse the response
        decision = {"route": "converse", "reason": f"Error parsing router response: {e}"}
    
        # Make parsing more robust to handle LLM variations (route vs decision)
        route = decision.get("route") or decision.get("decision")
        
        # Fallback logic: If route is missing but a tool is present, assume single_step
        if not route:
            # Try to infer from the presence of a tool
            tool_name = decision.get("tool_name")

            # Special case: if the LLM hallucinates "converse" as a tool, fix it to be a route.
            if tool_name == "converse":
                route = "converse"
            else:
                route = "single_step"

        if route not in ["single_step", "multi_step", "converse"]:
            raise ValueError(f"Invalid route '{route}'")
        # Create the result dictionary
        result = {"route": route}
        
        # If the route is 'converse', capture the reason.
        if route == "converse":
            # If we have automatically generated an area_map from dimensions, override converse
            # and use quote_materials directly instead of asking for more information
            if area_map_from_dimensions:
                print("OVERRIDING converse route with single_step using auto-generated area_map")
                result = {
                    "route": "single_step",
                    "tool_name": "quote_materials",
                    "tool_args": {
                        "area_map": area_map_from_dimensions
                    }
                }
                if image_report:
                    # Truyền toàn bộ nội dung image_report thay vì chỉ là boolean
                    result["tool_args"]["image_report"] = image_report
            else:
                reason = decision.get("reason", "No reason provided.")
                result["reason"] = reason
        
        # If the route is 'single_step', capture the tool and args.
        elif route == "single_step":
            tool_name = decision.get("tool_name")
            tool_args = decision.get("args", {})
            
            # Nếu không có tool_name nhưng có các tham số khác, giả định là quote_materials
            if not tool_name:
                print("WARNING: No tool_name provided for single_step route. Defaulting to quote_materials.")
                tool_name = "quote_materials"
                
                # Nếu decision có các trường như area, material_type, v.v., chuyển vào area_map
                if any(key in decision for key in ["area", "material_type", "type"]):
                    print(f"Found material parameters in decision: {decision}")
                    area = decision.get("area", "20m2")  # Giá trị mặc định nếu không có
                    material_type = decision.get("material_type", "gỗ")  # Giá trị mặc định
                    material_type_specific = decision.get("type")
                    
                    # Tạo area_map từ các tham số
                    area_map = {
                        "sàn": {
                            "material_type": material_type,
                            "area": area
                        }
                    }
                    
                    # Thêm type nếu có
                    if material_type_specific:
                        area_map["sàn"]["type"] = material_type_specific
                        
                    tool_args["area_map"] = area_map
            
            # Enrich area_map with position data from the image report
            if image_report and tool_name == "quote_materials" and "area_map" in tool_args:
                enriched_map = _enrich_area_map(tool_args["area_map"], image_report)
                tool_args["area_map"] = enriched_map
            
            # Always add image_report to tool arguments if available
            if image_report and tool_name in ["quote_materials", "run_image_quote"]:
                # Kiểm tra nếu tool_args đã có image_report dạng boolean hoặc string
                if "image_report" in tool_args:
                    # Nếu là True, yes, 1 thì chuyển thành nội dung đầy đủ
                    if tool_args["image_report"] in [True, "yes", "true", "1", 1]:
                        tool_args["image_report"] = image_report
                else:
                    # Nếu không có thì thêm vào
                    tool_args["image_report"] = image_report
                print("Added full image_report to tool arguments")
            
            if not tool_name:
                raise ValueError("No tool_name provided for single_step route")
                
            result["tool_name"] = tool_name
            result["tool_args"] = tool_args
            print(f"Final decision: route={route}, tool={tool_name}")
        else:
            print(f"Final decision: route={route}")
            
        print("====== CENTRAL ROUTER COMPLETE ======")
        return result
        
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error parsing router response: {e}")
        # Fallback to conversation mode if we can't parse the response
        return {"route": "converse", "reason": f"Error parsing router response: {e}"}

def _enrich_area_map(area_map: Dict[str, Any], image_report: str) -> Dict[str, Any]:
    """Helper function to add position info from image report to area_map."""
    print("Enriching area_map with position data from image report...")
    pattern = re.compile(r"Material:\s*(?P<material>.*?)\s*-\s*Type:\s*.*?\s*-\s*Position:\s*(?P<position>.*?)\s*-")
    matches = pattern.finditer(image_report)
    
    position_map = {match.group("material").strip().lower(): match.group("position").strip() for match in matches}
    
    for material, details in area_map.items():
        material_lower = material.lower()
        if material_lower in position_map and isinstance(details, dict) and "position" not in details:
            details["position"] = position_map[material_lower]
            print(f"Added position '{details['position']}' to material '{material}'")
            
    return area_map

def _extract_price_ranges(quote_result: str) -> Dict[str, Dict[str, Any]]:
    """
    Extract min-max price ranges from the quote output.
    This has been simplified to return an empty dict to avoid parsing issues.
    """
    # Return an empty dictionary to disable price range extraction
    return {}

# --- Conditional Routing Logic ---
def route_logic(state: State) -> Literal["direct_tool_executor", "plan_step_node", "conversational_responder"]:
    """Determines the next node based on the router's decision."""
    route = state.get("route")
    print(f"--- ROUTE LOGIC --- \nRoute: {route}")
    
    if route == "single_step":
        return "direct_tool_executor"
    if route == "multi_step":
        return "plan_step_node"
    return "conversational_responder"

# --- Node for Single-Step Execution ---
async def direct_tool_executor_node(state: State) -> Dict[str, Any]:
    """
    Directly executes a single tool call without planning.
    This is used for the "single_step" route.
    """
    print(f"--- DIRECT TOOL EXECUTOR ---")
    tool_name = state.get("tool_name")
    tool_args = state.get("tool_args", {})
    
    if not tool_name:
        # Fallback if the router fails to provide a tool name
        return {"error": "Router decided single_step but no tool_name was provided."}

    tool_call = ToolCall(name=tool_name, args=tool_args, id="tool_call_single_step")
    print(f"Executing single tool: {tool_name} with args: {tool_args}")
    
    # We create an AIMessage with the tool_call to pass to the ToolNode
    # Make sure to preserve the route in the state
    return {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "route": "single_step"  # Explicitly set the route to ensure it's preserved
    }

# --- ReAct (Plan and Execute) Nodes ---
async def plan_step_node(state: State) -> Dict[str, Any]:
    """
    Generates a step-by-step plan to address the user's complex query.
    This is the entry point for the "multi_step" route.
    """
    print("--- PLANNER (ReAct) ---")
    configuration = Configuration.from_context()
    model = load_chat_model(configuration.model)

    messages = state.get("messages", [])
    if not messages:
        return {"error": "No messages found to generate a plan."}

    chat_history = _format_history_for_prompt(messages[:-1])
    
    # Check for an image report in the conversation history
    image_report = None
    for msg in reversed(messages):
        if isinstance(msg, SystemMessage) and "[Image Analysis Report]:" in msg.content:
            image_report = msg.content.replace("[Image Analysis Report]:", "").strip()
            break
    
    image_info = "Image report is available." if image_report else "No image report."

    plan_prompt_str = PLAN_PROMPT.format(
        input=messages[-1].content,
        chat_history=chat_history,
        tools="\n".join([f"- {tool.name}: {tool.description}" for tool in TOOLS]),
        image_info=image_info
    )

    response = await model.ainvoke(plan_prompt_str)
    print(f"--- RAW PLANNER LLM OUTPUT ---\n{response.content}\n--------------------------")
    cleaned_response = cleanup_llm_output(str(response.content))
    
    try:
        plan = json.loads(cleaned_response)
        print(f"Generated Plan: {json.dumps(plan, indent=2, ensure_ascii=False)}")
        
        return {"plan": plan, "current_step_index": 0}
    except json.JSONDecodeError as e:
        print(f"Error parsing plan: {e}")
        return {"error": f"Failed to generate a valid plan. Details: {e}"}

# --- Hybrid ReAct Execution ---
def plan_decider_node(state: State) -> Dict[str, str]:
    """
    Decides the next step in the ReAct loop (continue plan or generate response).
    """
    print("--- PLAN DECIDER ---")
    error = state.get("error")
    current_step_index = state.get("current_step_index", 0)
    plan = state.get("plan", [])
    
    if error or not plan or current_step_index >= len(plan):
        print("Plan finished or error detected. Generating final response.")
        return {"next_step": "response_generator"}
    
    print(f"Continuing to step {current_step_index + 1}.")
    current_step_tasks = plan[current_step_index]

    # Check if any task in the current step is a dictionary (i.e., a tool call).
    has_tool_call = any(isinstance(task, dict) for task in current_step_tasks)

    # Decide whether the next task is a tool call or a reasoning step
    if has_tool_call:
        print("Routing to: LLM-Based Tool Executor")
        return {"next_step": "llm_tool_executor"}
    else:
        print("Routing to: LLM Reasoning Executor")
        return {"next_step": "reasoning_executor"}


async def llm_tool_executor_node(state: State) -> Dict[str, Any]:
    """
    Executes tool calls defined in the plan.
    It can handle parallel calls within a single plan step.
    """
    print(f"--- EXECUTOR (LLM-Based Tools) ---")
    step_index = state.get("current_step_index", 0)
    plan = state.get("plan", [])
    
    if not plan or step_index >= len(plan):
        return {"error": "Invalid plan or step index during tool execution."}
    
    current_step_tasks = plan[step_index]

    # Filter out non-dictionary items to only get tool call tasks
    tool_tasks = [task for task in current_step_tasks if isinstance(task, dict)]

    if not tool_tasks:
        return {"error": f"Step {step_index + 1} was routed to the tool executor, but no valid tool calls (dictionaries) were found."}

    tool_calls = [
        ToolCall(name=task["tool_name"], args=task.get("args", {}), id=f"tool_call_{step_index}_{i}")
        for i, task in enumerate(tool_tasks)
    ]
    
    print(f"Executing Step {step_index + 1}/{len(plan)} with tools: {[task['tool_name'] for task in tool_tasks]}")
    return {"messages": [AIMessage(content="", tool_calls=tool_calls)]}


async def llm_reasoning_executor_node(state: State) -> Dict[str, Any]:
    """
    Executes a complex reasoning instruction from the plan using an LLM.
    """
    print(f"--- EXECUTOR (LLM Reasoning) ---")
    configuration = Configuration.from_context()
    model_with_tools = load_chat_model(configuration.fast_model).bind_tools(TOOLS)

    step_index = state.get("current_step_index", 0)
    plan = state.get("plan", [])
    past_steps = state.get("past_steps", [])
    messages = state.get("messages", [])

    if not all([plan, messages]) or step_index >= len(plan):
        return {"error": "Invalid state for reasoning execution (missing plan, messages, or valid step index)."}
    
    current_step_instruction = plan[step_index][0]
    past_steps_str = "\n".join([f"Step {i+1} Result:\n{result}" for i, (_, result) in enumerate(past_steps)])

    prompt = EXECUTOR_PROMPT.format(
        input=messages[0].content,
        current_step=current_step_instruction,
        past_steps=past_steps_str,
        tools="\n".join([f"- {tool.name}: {tool.description}" for tool in TOOLS])
    )
    
    ai_message_with_tool_call = await model_with_tools.ainvoke(prompt)
    print(f"--- RAW REASONING LLM OUTPUT ---\n{ai_message_with_tool_call}\n--------------------------")
    
    return {"messages": [ai_message_with_tool_call]}


def after_tool_execution_node(state: State) -> Dict[str, Any]:
    """
    Aggregates results from tool calls and updates the state.
    
    This node runs after any tool execution and is responsible for:
    1. Parsing the tool results
    2. Updating the state with any new information
    3. Saving quote parameters for future reference
    
    Args:
        state: The current state
        
    Returns:
        Updated state
    """
    print("--- UPDATING STATE AFTER TOOLS ---")
    updates = {}
    messages = state.get("messages", [])
    
    # Check if there are any messages
    if not messages:
        return updates
    
    # Get the last message, which should be a ToolMessage
    last_message = messages[-1]
    if isinstance(last_message, ToolMessage):
        # Extract the tool result
        step_result = last_message.content
        
        # Get tool name from the message
        tool_name = last_message.tool_call_id
        print(f"Processing tool result for: {tool_name}")
        
        # Extract parameters to save for future reference
        params_to_save = {}
        tool_args = {}
        
        # Find the corresponding AI message with the tool args
        found_tool_args = False
        for msg in reversed(messages[:-1]):
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    # Check if tool_call is a dict or an object
                    if isinstance(tool_call, dict):
                        tool_call_id = tool_call.get("id")
                    else:
                        tool_call_id = tool_call.id
                        
                    if tool_call_id == last_message.tool_call_id:
                        try:
                            # Check if args is a dict or a string
                            if isinstance(tool_call, dict):
                                args_str = tool_call.get("args", "{}")
                            else:
                                args_str = tool_call.args
                                
                            tool_args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            found_tool_args = True
                            print(f"Found tool args: {json.dumps(tool_args, ensure_ascii=False)}")
                            break
                        except (json.JSONDecodeError, ValueError) as e:
                            print(f"Error parsing tool args: {e}")
                if found_tool_args:
                    break
        
        # Fallback: Check if the tool args are in the state directly
        if not found_tool_args and "tool_args" in state:
            tool_args = state.get("tool_args", {})
            print(f"Using tool args from state: {json.dumps(tool_args, ensure_ascii=False)}")
        
        # Save the tool result to past_steps for response generation
        route = state.get("route")
        if route == "single_step":
            # Create a description of the tool call
            tool_description = json.dumps({"tool_name": tool_name, "args": tool_args}, ensure_ascii=False)
            # Add the result to past_steps
            updates["past_steps"] = [(tool_description, step_result)]
            print(f"Added tool result to past_steps: {step_result[:100]}...")
        
        # Only save parameters from certain tools
        if tool_name == "quote_materials":
            # Extract area_map from tool arguments
            if tool_args.get("area_map"):
                params_to_save["area_map"] = tool_args["area_map"]
            
            # Extract material_list from tool arguments
            if tool_args.get("material_list"):
                params_to_save["material_list"] = tool_args["material_list"]
            
            # Extract budget from tool arguments
            if tool_args.get("budget"):
                params_to_save["budget"] = tool_args["budget"]

            if params_to_save:
                # Ensure consistent format for Quote Parameters
                summary_str = f"[Quote Parameters]:\n{json.dumps(params_to_save, indent=2, ensure_ascii=False)}"
                quote_params_message = SystemMessage(content=summary_str)
                
                # Insert the quote_params_message BEFORE the last message (the ToolMessage)
                # This ensures it's part of the history and will be found in the next turn
                new_messages = []
                for idx, msg in enumerate(messages):
                    if idx == len(messages) - 1:  # Last message
                        new_messages.append(quote_params_message)  # Insert params first
                        new_messages.append(msg)  # Then the tool message
                    else:
                        new_messages.append(msg)
                
                updates["messages"] = new_messages
                print("--- SAVED QUOTE PARAMETERS ---")
                print(summary_str)
            
    return updates


# --- Self-Correction Node ---
def add_error_feedback_node(state: State) -> Dict[str, Any]:
    """
    Adds a system message to the history to inform the LLM of its tool selection error,
    prompting it to self-correct.
    """
    messages = state.get("messages", [])
    last_message = messages[-1]
    error_content = "An unspecified tool error occurred."
    if isinstance(last_message, ToolMessage):
        error_content = str(last_message.content)

    error_feedback = SystemMessage(
        content=f"Your previous attempt failed because you tried to call an invalid tool. "
                f"The error was: '{error_content}'. Please analyze the user's request again and choose a valid tool from the provided list."
    )
    
    print("--- ADDING ERROR FEEDBACK to prompt self-correction ---")
    return {"messages": messages + [error_feedback]}


# --- Final Responder Nodes (REFACTORED for STREAMING) ---

def format_response_input(state: State) -> Dict[str, Any]:
    """Formats the input for the final response generation chain."""
    error = state.get("error")
    if error:
        return {"past_steps": f"An error occurred during execution: {error}"}
    
    past_steps = state.get("past_steps", [])
    if not past_steps:
        return {"past_steps": "No actions were taken. Please respond conversationally."}

    # Defensive check: If this was a single-step tool call but the state has accumulated
    # more than one step, it indicates a state bleed-over. Only use the most recent step.
    route = state.get("route")
    if route == "single_step" and len(past_steps) > 1:
        print(f"WARNING: State accumulation detected in single_step route. "
              f"Found {len(past_steps)} steps, using only the most recent one.")
        past_steps = past_steps[-1:]
        
    past_steps_str = "\n\n".join([f"Step: {step}\nResult: {result}" for step, result in past_steps])
    return {"past_steps": past_steps_str}

def handle_tool_error(state: State) -> Literal["add_error_feedback_node", "response_generator", "plan_decider"]:
    """
    Checks for tool execution errors and decides whether to retry (for single-step) or end.
    """
    route = state.get("route")
    
    if route == "multi_step":
        return "plan_decider"
        
    if route == "single_step":
        messages = state.get("messages", [])
        if not messages:
            return "response_generator"

        last_message = messages[-1]
        if isinstance(last_message, ToolMessage):
            error_content = str(last_message.content)
            if "Invalid tool call" in error_content or "not found" in error_content:
                print("--- TOOL ERROR HANDLER: Invalid tool name detected. Looping back to router for self-correction. ---")
                return "add_error_feedback_node"

    return "response_generator"


def format_converse_input(state: State) -> Dict[str, Any]:
    """Formats the input for the conversational response chain."""
    messages = state.get("messages", [])
    if not messages:
        return {"input": "No message history found.", "reason": "Initial state."}
    
    return {
        "input": messages[-1].content,
        "reason": state.get("reason", "The router decided to converse but did not provide a specific reason.")
    }

# Define response chains using LCEL for native streaming
response_prompt = ChatPromptTemplate.from_template(RESPONSE_PROMPT)
response_generation_chain = (
    RunnableLambda(format_response_input)
    | response_prompt
    | load_chat_model(Configuration().model)
)

async def converse_node(state: State) -> State:
    """Node for the conversation pathway."""
    print("--- CONVERSE NODE START ---")
    
    # Create a conversation prompt using messages and reason for conversation
    config = Configuration.from_context()
    model = load_chat_model(config.model)
    
    # Get conversation parameters from state
    reason = state.get("reason", "No reason provided")
    messages = state.get("messages", [])
    
    if not messages:
        print("No messages found in state")
        return state
    
    input_message = messages[-1].content
    
    # Prompt the conversation model for a response
    converse_prompt_str = CONVERSE_PROMPT.format(
        reason=reason,
        input=input_message
    )
    
    print("====== FULL CONVERSE PROMPT ======")
    print(converse_prompt_str)
    print("===============================")
    
    print("Sending prompt to converse model...")
    response = await model.ainvoke(converse_prompt_str)
    print(f"--- RAW CONVERSE LLM OUTPUT ---\n{response.content}\n--------------------------")
    
    # Update the state with the assistant's response
    messages.append(AIMessage(content=response.content))
    return {"messages": messages}

converse_prompt = ChatPromptTemplate.from_template(CONVERSE_PROMPT)
converse_generation_chain = (
    RunnableLambda(format_converse_input)
    | converse_prompt # Use the dedicated converse prompt
    | load_chat_model(Configuration().model)
)

async def response_generator_node(state: State) -> Dict[str, Any]:
    """Generates the final response and appends it to the message history."""
    ai_message = await response_generation_chain.ainvoke(state)
    print(f"--- RAW FINAL RESPONSE LLM OUTPUT ---\n{ai_message.content}\n--------------------------")
    final_content = cleanup_llm_output(str(ai_message.content))
    return {
        "messages": state["messages"] + [AIMessage(content=final_content)],
        "final_response": final_content
    }
    
async def conversational_responder_node(state: State) -> Dict[str, Any]:
    """Generates a conversational response and appends it to the message history."""
    ai_message = await converse_generation_chain.ainvoke(state)
    print(f"--- RAW CONVERSE LLM OUTPUT ---\n{ai_message.content}\n--------------------------")
    final_content = cleanup_llm_output(str(ai_message.content))
    return {
        "messages": state["messages"] + [AIMessage(content=final_content)],
        "final_response": final_content
    }


# --- Graph Definition (Simplified Architecture) ---
builder = StateGraph(State, config_schema=Configuration)

# Add all nodes
builder.add_node("central_router", central_router_node)
builder.add_node("direct_tool_executor", direct_tool_executor_node) # New for single_step
builder.add_node("plan_step_node", plan_step_node)
builder.add_node("llm_tool_executor", llm_tool_executor_node) # Replaces direct_tool_executor in plan
builder.add_node("reasoning_executor", llm_reasoning_executor_node) # Replaces llm_executor
builder.add_node("after_tool_node", after_tool_execution_node)
builder.add_node("tool_node", ToolNode(TOOLS))
# Replace old nodes with the new state-aware node functions
builder.add_node("conversational_responder", conversational_responder_node)
builder.add_node("response_generator", response_generator_node)
builder.add_node("plan_decider", plan_decider_node) # New unified decider
builder.add_node("add_error_feedback_node", add_error_feedback_node) # Node for self-correction

# Set entry point
builder.set_entry_point("central_router")

# Define edges from the central router
builder.add_conditional_edges("central_router", route_logic, {
    "direct_tool_executor": "direct_tool_executor",
    "plan_step_node": "plan_step_node",
    "conversational_responder": "conversational_responder",
})

# Path for single-step execution
builder.add_edge("direct_tool_executor", "tool_node")

# Path for multi-step (ReAct) execution
builder.add_edge("plan_step_node", "plan_decider") # Plan now goes to the new decider
builder.add_conditional_edges(
    "plan_decider",
    lambda x: x["next_step"], # Read the decision from the state's 'next_step' field
    {
        "llm_tool_executor": "llm_tool_executor",
        "reasoning_executor": "reasoning_executor",
        "response_generator": "response_generator",
    }
)
builder.add_edge("llm_tool_executor", "tool_node")
builder.add_edge("reasoning_executor", "tool_node")

# Unified path after any tool execution
builder.add_edge("tool_node", "after_tool_node")

# Path for multi-step loop and single-step exit/retry
builder.add_conditional_edges(
    "after_tool_node",
    handle_tool_error,
    {
        "plan_decider": "plan_decider",
        "add_error_feedback_node": "add_error_feedback_node",
        "response_generator": "response_generator",
    }
)

# The new self-correction loop
builder.add_edge("add_error_feedback_node", "central_router")

# Final exit points
builder.add_edge("conversational_responder", END)
builder.add_edge("response_generator", END)

# Compile
graph = builder.compile(name="Simplified Agent")