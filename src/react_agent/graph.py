"""
Main graph definition for the Hybrid Agent.
This graph orchestrates the flow between a central router, super-tools, and a ReAct planner.
"""
import asyncio
import json
from typing import Dict, Any, Literal
import inspect

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from react_agent.configuration import Configuration
from react_agent.state import State
from react_agent.tools import TOOLS
from react_agent.super_tools import SUPER_TOOLS_MAP
from react_agent.utils import load_chat_model, cleanup_llm_output
from react_agent.prompts import (
    CENTRAL_ROUTER_PROMPT, RESPONSE_PROMPT, PLAN_PROMPT, EXECUTOR_PROMPT
)

async def central_router_node(state: State) -> Dict[str, Any]:
    """
    This node acts as the central brain of the agent.
    It analyzes the user's request and decides which path to take:
    - "super_tool": For simple, predefined tasks.
    - "plan": For complex, multi-step tasks requiring ReAct.
    - "converse": For general conversation.
    """
    print("--- CENTRAL ROUTER ---")
    configuration = Configuration.from_context()
    model = load_chat_model(configuration.model)

    # Extract the latest human message and chat history
    input_message = state.messages[-1]
    # Simple history for now, can be improved later
    chat_history = "\n".join(
        [f"{msg.type}: {msg.content}" for msg in state.messages[:-1]]
    )

    # Format the prompt
    router_prompt_str = CENTRAL_ROUTER_PROMPT.format(
        input=input_message.content,
        chat_history=chat_history
    )

    # Invoke the model
    response = await model.ainvoke(router_prompt_str)
    
    # Clean and parse the response
    # Ensure content is a string before cleaning
    content_str = str(response.content)
    cleaned_response = cleanup_llm_output(content_str)
    print(f"Router Decision (JSON):\n{cleaned_response}")
    
    try:
        decision = json.loads(cleaned_response)
        route = decision.get("route")
        tool_name = decision.get("tool_name")
        tool_args = decision.get("args")

        # Validate the decision
        if route not in ["super_tool", "plan", "converse"]:
            raise ValueError(f"Invalid route '{route}'")
        if route == "super_tool" and not tool_name:
            raise ValueError("Route 'super_tool' requires a 'tool_name'.")

        return {
            "route": route,
            "tool_name": tool_name,
            "tool_args": tool_args
        }
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error parsing router decision: {e}")
        # Default to a conversational response on error
        return {"route": "converse"}

# This is the conditional routing logic
def route_logic(state: State) -> Literal["super_tool_executor", "planner", "conversational_responder"]:
    """Determines the next node based on the router's decision."""
    print(f"Routing logic based on state: {state.route}")
    if state.route == "super_tool":
        return "super_tool_executor"
    elif state.route == "plan":
        return "planner"
    else: # Includes "converse" and any error cases
        return "conversational_responder"

# --- Super-Tool Node ---
async def super_tool_executor_node(state: State) -> Dict[str, Any]:
    """
    Executes the chosen super-tool based on the router's decision.
    """
    print("--- SUPER TOOL EXECUTOR ---")
    tool_name = state.tool_name
    tool_args = state.tool_args or {}
    
    if not tool_name or tool_name not in SUPER_TOOLS_MAP:
        error_msg = f"Router selected an invalid or unimplemented super-tool: '{tool_name}'"
        print(f"ERROR: {error_msg}")
        return {"past_steps": [("super_tool_executor", f"Error: {error_msg}")]}

    tool_function = SUPER_TOOLS_MAP[tool_name]
    sig = inspect.signature(tool_function)
    
    final_args = {}
    if "messages" in sig.parameters:
        final_args["messages"] = state.messages
            
    final_args.update(tool_args)

    try:
        result = await tool_function(**final_args)
        print(f"Super-tool '{tool_name}' executed successfully.")
        return {"past_steps": [("super_tool_executor", result)]}
    except Exception as e:
        error_msg = f"Error executing super-tool '{tool_name}': {e}"
        print(f"ERROR: {error_msg}")
        return {"past_steps": [("super_tool_executor", f"Error: {error_msg}")]}

# --- ReAct (Plan and Execute) Nodes ---

async def plan_step_node(state: State) -> Dict[str, Any]:
    """
    Generates a step-by-step plan to address the user's complex query.
    """
    print("--- PLANNER (ReAct) ---")
    configuration = Configuration.from_context()
    model = load_chat_model(configuration.model)

    # Format the prompt
    plan_prompt_str = PLAN_PROMPT.format(
        input=state.messages[-1].content,
        chat_history="\n".join([f"{msg.type}: {msg.content}" for msg in state.messages[:-1]]),
        tools="\n".join([f"- {tool.name}: {tool.description}" for tool in TOOLS])
    )

    response = await model.ainvoke(plan_prompt_str)
    cleaned_response = cleanup_llm_output(str(response.content))
    
    try:
        plan = json.loads(cleaned_response)
        print(f"Generated Plan: {plan}")
        return {"plan": plan, "current_step_index": 0}
    except json.JSONDecodeError as e:
        print(f"Error parsing plan: {e}")
        return {"error": f"Failed to generate a valid plan. Details: {e}"}

async def execute_step_node(state: State) -> Dict[str, Any]:
    """
    Executes a step of the plan using the FAST model.
    """
    print(f"--- EXECUTOR (ReAct) ---")
    configuration = Configuration.from_context()
    # Use the FAST model for tool selection
    model_with_tools = load_chat_model(configuration.fast_model).bind_tools(TOOLS)

    step_index = state.current_step_index
    plan = state.plan
    current_step_tasks = plan[step_index] # This is now a list of tasks
    print(f"Executing Step {step_index + 1}/{len(plan)} with {len(current_step_tasks)} parallel tasks.")
    
    past_steps_str = "\n".join([f"Step {i+1} Result: {result}" for i, result in enumerate(state.past_steps)])

    # Create a coroutine for each task in the current step
    async def run_task(task_description: str):
        prompt = EXECUTOR_PROMPT.format(
            input=state.messages[0].content,
            current_step=task_description,
            past_steps=past_steps_str,
            tools="\n".join([f"- {tool.name}: {tool.description}" for tool in TOOLS])
        )
        return await model_with_tools.ainvoke(prompt)

    # Run all tasks in the current step concurrently
    ai_messages_with_tool_calls = await asyncio.gather(*(run_task(task) for task in current_step_tasks))
    
    return {"messages": ai_messages_with_tool_calls}

def after_tool_execution_node(state: State) -> Dict[str, Any]:
    """
    Aggregates results from parallel tool calls and updates the state.
    """
    print("--- UPDATING STATE AFTER PARALLEL TOOLS---")
    
    # Identify which messages are the results from the last tool execution
    tool_messages = [msg for msg in state.messages if isinstance(msg, ToolMessage)]
    current_tasks = state.plan[state.current_step_index]
    last_step_results = tool_messages[-len(current_tasks):]

    # Combine the content of the latest tool messages into a single result string
    step_result_str = "\n".join([str(msg.content) for msg in last_step_results])
    
    # The "description" of this step is the combination of all tasks run in parallel
    step_description_str = " & ".join(current_tasks)

    # FIX: Append a tuple (description, result) to past_steps to match the expected format
    new_past_steps = state.past_steps + [(step_description_str, step_result_str)]
    
    return {
        "current_step_index": state.current_step_index + 1,
        "past_steps": new_past_steps
    }

def should_continue_node(state: State) -> Literal["execute_step_node", "response_generator"]:
    """
    Decides if the plan has more steps or if it's time to generate the final response.
    """
    print("--- DECIDER (ReAct) ---")
    if state.current_step_index >= len(state.plan):
        print("Plan finished. Generating final response.")
        return "response_generator"
    else:
        print("Plan not finished. Continuing to next step.")
        return "execute_step_node"

# --- Final Responder Nodes (Corrected) ---

async def conversational_responder_node(state: State) -> Dict[str, Any]:
    """
    FIXED: Generates a direct conversational response and puts it in 'final_response' to end the graph.
    """
    print("--- CONVERSATIONAL RESPONDER ---")
    configuration = Configuration.from_context()
    model = load_chat_model(configuration.model)

    # Format the prompt
    response_prompt_str = RESPONSE_PROMPT.format(
        chat_history="\n".join([f"{msg.type}: {msg.content}" for msg in state.messages])
    )

    response = await model.ainvoke(response_prompt_str)
    cleaned_response = cleanup_llm_output(str(response.content))
    print(f"Conversational Response:\n{cleaned_response}")
    
    return {"final_response": cleaned_response}

async def response_generator_node(state: State) -> Dict[str, Any]:
    """
    FIXED: Generates the final response from `past_steps` and puts it in 'final_response'.
    """
    print("--- RESPONSE GENERATOR ---")
    configuration = Configuration.from_context()
    model = load_chat_model(configuration.model)

    results = state.past_steps or []
    past_steps_str = "\n".join([f"Step: {step}\nResult: {result}" for step, result in results])

    response_prompt_str = RESPONSE_PROMPT.format(past_steps=past_steps_str)
    
    response = await model.ainvoke(response_prompt_str)
    cleaned_response = cleanup_llm_output(str(response.content))
    
    print(f"Final response: {cleaned_response}")
    return {"final_response": cleaned_response}

# --- Graph Definition (Corrected) ---
builder = StateGraph(State, config_schema=Configuration)

# Add all nodes
builder.add_node("central_router", central_router_node)
builder.add_node("super_tool_executor", super_tool_executor_node)
builder.add_node("plan_step_node", plan_step_node)
builder.add_node("execute_step_node", execute_step_node)
builder.add_node("after_tool_node", after_tool_execution_node)
builder.add_node("tool_node", ToolNode(TOOLS))
builder.add_node("conversational_responder", conversational_responder_node)
builder.add_node("response_generator", response_generator_node)

# Set entry and connections
builder.set_entry_point("central_router")

builder.add_conditional_edges("central_router", route_logic, {
    "super_tool_executor": "super_tool_executor",
    "planner": "plan_step_node",
    "conversational_responder": "conversational_responder",
})
builder.add_edge("super_tool_executor", "response_generator")

# Define the CORRECTED ReAct Loop
builder.add_edge("plan_step_node", "execute_step_node")
builder.add_edge("execute_step_node", "tool_node")
builder.add_edge("tool_node", "after_tool_node")
builder.add_conditional_edges("after_tool_node", should_continue_node, {
    "execute_step_node": "execute_step_node",
    "response_generator": "response_generator",
})

# Final exit points
builder.add_edge("conversational_responder", END)
builder.add_edge("response_generator", END)

# Compile
graph = builder.compile(name="Hybrid Agent")