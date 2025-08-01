"""Define the state structures for the agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict, List, Optional, Any, Dict, Sequence

from langchain_core.messages import BaseMessage, AnyMessage
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep
from typing_extensions import Annotated


@dataclass
class InputState:
    """Defines the input state for the agent, representing a narrower interface to the outside world.

    This class is used to define the initial state and structure of incoming data.
    """

    conversation_id: Optional[str] = None
    messages: Annotated[Sequence[AnyMessage], add_messages] = field(
        default_factory=list
    )
    """
    Messages tracking the primary execution state of the agent.

    Typically accumulates a pattern of:
    1. HumanMessage - user input
    2. AIMessage with .tool_calls - agent picking tool(s) to use to collect information
    3. ToolMessage(s) - the responses (or errors) from the executed tools
    4. AIMessage without .tool_calls - agent responding in unstructured format to the user
    5. HumanMessage - user responds with the next conversational turn

    Steps 2-5 may repeat as needed.

    The `add_messages` annotation ensures that new messages are merged with existing ones,
    updating by ID to maintain an "append-only" state unless a message with the same ID is provided.
    """


class State(TypedDict):
    messages: Annotated[list, add_messages]
    
    # A concise summary of the conversation history
    history_summary: Optional[str]
    
    # The action plan (list of tool calls) generated by the Strategist.
    plan: Optional[List[Dict[str, Any]]]
    
    # The results from the executed tools, synthesized into a single string.
    tool_results: Optional[str]

    # A map of surfaces to their areas, persisted across turns
    area_map: Optional[Dict[str, Any]]
    quotes: Optional[List[Dict[str, Any]]]
    
    # User's budget for construction
    budget: Optional[float]
    
    # Summary of important events in chronological order
    events_summary: Optional[List[str]]
    
    # Reason for direct response (when no tools are executed)
    response_reason: Optional[str]
    
    # Summary of tool execution results
    execution_summary: Optional[str]
