"""Define a custom Reasoning and Action agent.

Works with a chat model with tool calling support.
"""

from datetime import UTC, datetime
import uuid
from typing import Dict, List, Literal, cast

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from react_agent.configuration import Configuration
from react_agent.state import InputState, State
from react_agent.tools import TOOLS
from react_agent.utils import load_chat_model

# Tracing has been removed as it was causing issues and the file was deleted.
TRACING_AVAILABLE = False

# Define the function that calls the model


async def call_model(state: State) -> Dict[str, List[AIMessage]]:
    """Call the LLM powering our "agent" asynchronously.

    This function prepares the prompt, initializes the model, and processes the response.

    Args:
        state (State): The current state of the conversation.
        config (RunnableConfig): Configuration for the model run.

    Returns:
        dict: A dictionary containing the model's response message.
    """
    configuration = Configuration.from_context()

    # Initialize the model with tool binding. Change the model or add more tools here.
    model = load_chat_model(configuration.model).bind_tools(TOOLS)

    # Format the system prompt. Customize this to change the agent's behavior.
    system_message = configuration.system_prompt.format(
        system_time=datetime.now(tz=UTC).isoformat()
    )

    # Get the model's response
    messages = [{"role": "system", "content": system_message}, *state.messages]

    # --- Add a reminder message before final generation ---
    # Check if the last message in the state is a ToolMessage, which means we just ran tools.
    if len(state.messages) > 1 and isinstance(state.messages[-1], dict) and state.messages[-1].get('role') == 'tool':
        # Find the last human message to remind the LLM of the user's request
        last_human_message_content = ""
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            is_human = (isinstance(msg, dict) and msg.get('role') == 'user') or \
                       (not isinstance(msg, dict) and getattr(msg, 'type', None) == 'human')
            if is_human:
                last_human_message_content = msg.get('content') if isinstance(msg, dict) else msg.content
                break
        
        if last_human_message_content:
            reminder_text = (
                "--------------------\n"
                "ĐÃ CÓ KẾT QUẢ TỪ TOOL. HÃY TỔNG HỢP VÀ TRẢ LỜI. \n"
                f"NHẮC LẠI YÊU CẦU CUỐI CÙNG CỦA NGƯỜI DÙNG: '{last_human_message_content}'"
                "\n--------------------"
            )
            messages.append({"role": "system", "content": reminder_text})
    # --- End reminder message ---


    # --- LOGGING: Print the prompt being sent to the LLM ---
    print("\n" + "="*50)
    print("🚀 SENDING PROMPT TO LLM 🚀")
    print("="*50)
    for msg in messages:
        # Simplified logging to avoid confusion
        if isinstance(msg, dict):
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')
            print(f"[{role}]:\n{content}")
        else: # It's a BaseMessage object
            msg_type = getattr(msg, 'type', 'unknown').upper()
            content = getattr(msg, 'content', '')
            print(f"[{msg_type}]:\n{content}")
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                print(f"Tool Calls: {msg.tool_calls}")
        print("-" * 20)
    # --- END LOGGING ---
    
    response = cast(AIMessage, await model.ainvoke(messages))

    # --- LOGGING: Print the LLM response and token usage ---
    print("\n" + "="*50)
    print("📊 LLM RESPONSE & TOKEN USAGE 📊")
    print("="*50)
    print(f"[AI RESPONSE]:\n{response.content}")
    if response.tool_calls:
        print(f"Tool Calls: {response.tool_calls}")
    
    # Extract and log token usage from response metadata
    if response.response_metadata and 'token_usage' in response.response_metadata:
        token_usage = response.response_metadata['token_usage']
        print("\n--- TOKEN USAGE ---")
        print(f"  Prompt Tokens: {token_usage.get('prompt_tokens', 'N/A')}")
        print(f"  Completion Tokens: {token_usage.get('completion_tokens', 'N/A')}")
        print(f"  Total Tokens: {token_usage.get('total_tokens', 'N/A')}")
    else:
        print("\n--- TOKEN USAGE ---")
        print("  Token usage data not available in response.")
    print("="*50 + "\n")
    # --- END LOGGING ---

    # Clean the response content
    if response.content and isinstance(response.content, str):
        import re
        # Remove <think>...</think> blocks
        think_regex = re.compile(r"<think>.*?</think>", re.DOTALL)
        # Remove [AI]: prefixes
        ai_prefix_regex = re.compile(r"\[AI\]:.*?(\n|$)", re.DOTALL)
        # Remove Tool Calls: [...] text - match different variations
        tool_calls_regex = re.compile(r"Tool Calls:?\s*\[.*?\]", re.DOTALL)
        # Alternative tool call formats
        alt_tool_calls_regex = re.compile(r"Tool Call[s]?:.*?(\n|$)", re.DOTALL)
        
        cleaned_content = think_regex.sub("", response.content).strip()
        cleaned_content = ai_prefix_regex.sub("", cleaned_content).strip()
        cleaned_content = tool_calls_regex.sub("", cleaned_content).strip()
        cleaned_content = alt_tool_calls_regex.sub("", cleaned_content).strip()
        
        # Create a new response with cleaned content
        response = AIMessage(
            content=cleaned_content,
            id=response.id,
            tool_calls=response.tool_calls,
            response_metadata=response.response_metadata if hasattr(response, 'response_metadata') else None
        )

    # Handle the case when it's the last step and the model still wants to use a tool
    if state.is_last_step and response.tool_calls:
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content="Sorry, I could not find an answer to your question in the specified number of steps.",
                )
            ]
        }

    # Return the model's response as a list to be added to existing messages
    return {"messages": [response]}


def call_model_sync(state: State) -> Dict[str, List[AIMessage]]:
    """Synchronous wrapper around the async call_model function.
    
    This allows the function to be used with the synchronous invoke API.
    
    Args:
        state (State): The current state of the conversation.
        
    Returns:
        dict: A dictionary containing the model's response message.
    """
    import asyncio
    
    # Create a new event loop
    loop = asyncio.new_event_loop()
    
    try:
        # Run the async function in the new loop
        return loop.run_until_complete(call_model(state))
    finally:
        # Clean up the loop
        loop.close()

# Define a new graph
# FIX: Removed `input=InputState` and `executor=threading.Thread`
builder = StateGraph(State, config_schema=Configuration)

# Define the two nodes we will cycle between
builder.add_node("call_model", call_model_sync)
builder.add_node("tools", ToolNode(TOOLS))

# Set the entrypoint as `call_model`
# This means that this node is the first one called
builder.add_edge("__start__", "call_model")


def route_model_output(state: State) -> Literal["__end__", "tools"]:
    """Determine the next node based on the model's output.

    This function checks if the model's last message contains tool calls.

    Args:
        state (State): The current state of the conversation.

    Returns:
        str: The name of the next node to call ("__end__" or "tools").
    """
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError(
            f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
        )
    # If there is no tool call, then we finish
    if not last_message.tool_calls:
        return "__end__"
    # Otherwise we execute the requested actions
    return "tools"


# Add a conditional edge to determine the next step after `call_model`
builder.add_conditional_edges(
    "call_model",
    # After call_model finishes running, the next node(s) are scheduled
    # based on the output from route_model_output
    route_model_output,
)

# Add a normal edge from `tools` to `call_model`
# This creates a cycle: after using tools, we always return to the model
builder.add_edge("tools", "call_model")

# Compile the builder into an executable graph
graph = builder.compile(name="ReAct Agent")