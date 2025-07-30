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
from .agents.planner import history_summarizer_node, planner_node
from .agents.executor import executor_node
from .agents.responder import responder_node
from .new_tools import execute_tool

def should_execute_tools(state: State) -> Literal["executor", "responder"]:
    """Conditional edge based on the plan."""
    print(f"---ROUTING: Based on plan---")
    plan = state.get("plan")
    if plan is not None and plan != []:
        print("Decision: Execute tools.")
        return "executor"
    print("Decision: Generate final response.")
    return "responder"

def create_graph():
    """Creates the LangGraph instance with all the nodes and edges."""
    
    builder = StateGraph(State)
    
    builder.add_node("history_summarizer", history_summarizer_node)
    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("responder", responder_node)
    
    builder.set_entry_point("history_summarizer")
    builder.add_edge("history_summarizer", "planner")
    
    builder.add_conditional_edges(
        "planner",
        should_execute_tools,
        {
            "executor": "executor",
            "responder": "responder",
        }
    )
    
    builder.add_edge("executor", "responder")
    builder.add_edge("responder", END)
    
    print("[DEBUG] Compiling graph with new Planner-Executor-Responder architecture.")
    return builder.compile()

# Initialize the graph instance
graph = create_graph()