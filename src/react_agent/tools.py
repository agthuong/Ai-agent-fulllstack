"""
This module aggregates all available tools for the agent.
It combines basic, low-level tools with high-level, business-logic "super-tools".
This unified list is provided to the ReAct planner.
"""
from typing import Any, Callable, List

# Import all base tools
from .base_tools import (
    material_price_query,
    search,
    ask_vision_model_about_image,
    get_historical_image_report,
    save_quote,
    get_saved_quotes,
    calculator_tool
)

# Import all super-tools
from .super_tools import (
    run_preliminary_quote,
    run_detailed_quote,
    run_market_comparison,
    run_image_quote
)

# The final, comprehensive list of tools available to the ReAct planner.
# This unified approach gives the planner maximum flexibility.
TOOLS: List[Callable[..., Any]] = [
    # High-level "super-tools"
    run_detailed_quote,
    run_preliminary_quote,
    run_market_comparison,
    run_image_quote,
    # Basic, foundational tools
    material_price_query,
    calculator_tool,
    search, 
    save_quote,
    get_saved_quotes,
    ask_vision_model_about_image,
]
