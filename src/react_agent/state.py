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
    
    # Context extracted by the Strategist to be used by the Executor
    context_for_executor: Optional[str]
    
    # The decision made by the Strategist (EXECUTE_TOOL or GENERATE_RESPONSE)
    decision: Optional[str]
    
    # If the Strategist decides not to use a tool, this field will contain the reason
    response_reason: Optional[str]
    
    # The results from the executed tools
    tool_results: Optional[str]

    # A map of surfaces to their areas, persisted across turns
    area_map: Optional[Dict[str, Any]]
