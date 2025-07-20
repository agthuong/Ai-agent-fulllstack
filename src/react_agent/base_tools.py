"""
Defines the basic, foundational tools for the agent.
These tools have no internal dependencies on other parts of the agent logic.
"""
import os
import re
import requests
import base64
import json
import datetime
from typing import Any, Callable, List, Optional, cast

from langchain_core.tools import tool
from langchain_tavily import TavilySearch
import httpx

from react_agent.configuration import Configuration
from react_agent.memory import memory_manager
from react_agent.vision import get_gemini_vision_report
from langchain_core.messages import SystemMessage

# --- Path setup for data files ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_current_dir, '..', '..', 'data_new')

# Create directory to save quotes if it doesn't exist
QUOTES_DIR = "saved_quotes"
os.makedirs(QUOTES_DIR, exist_ok=True)

# ==============================================================================
# === BASIC TOOL IMPLEMENTATIONS ===============================================
# ==============================================================================

@tool
def material_price_query(material_type: str, type: Optional[str] = None, mode: str = 'range') -> str:
    """
    Looks up the construction price for a given material from the company's database.
    - material_type: The category of the material (e.g., 'gỗ', 'đá', 'sơn').
    - type: The specific variant of the material (e.g., 'gỗ óc chó', 'đá marble').
    - mode: 'range' (default) returns a price range, 'full_list' returns all variants and prices.
    """
    filename = os.path.join(_data_dir, f'{material_type.lower()}_prices.json')

    if not os.path.exists(filename):
        return f"Không tìm thấy dữ liệu giá cho loại vật liệu '{material_type}'."

    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if mode == 'full_list':
        price_list_str = f"Bảng giá thi công chi tiết cho {material_type}:\n"
        for item_type, details in data.items():
            price_list_str += f"\n## {item_type}\n"
            for variant, price in details.get("variants", {}).items():
                price_list_str += f"- {variant}: {price:,.0f} VND/m²\n"
        return price_list_str.strip()

    # Default to 'range' mode
    if type:
        for item_type, details in data.items():
            if type.lower() in item_type.lower():
                min_price = min(details.get("variants", {}).values())
                max_price = max(details.get("variants", {}).values())
                return f"Giá thi công cho {item_type} dao động từ {min_price:,.0f} VND/m² đến {max_price:,.0f} VND/m²."
        return f"Không tìm thấy loại cụ thể '{type}' trong danh mục '{material_type}'. Giá chung cho {material_type} là: ..." # Fallback logic can be added
    else:
        # Generic range for the whole material type
        all_prices = [p for d in data.values() for p in d.get("variants", {}).values()]
        if not all_prices:
            return f"Không có giá chi tiết cho loại vật liệu '{material_type}'."
        min_price = min(all_prices)
        max_price = max(all_prices)
        return f"Giá thi công cho {material_type} dao động từ {min_price:,.0f} VND/m² đến {max_price:,.0f} VND/m²."


@tool
def search(query: str) -> str:
    """Performs a web search to find market prices or other construction-related information.
    Use this if the internal database (material_price_query) does not have the required information.
    Example query: "giá thi công gỗ sồi trên thị trường Hà Nội".
    """
    try:
        tavily = TavilySearch()
        results = tavily.invoke(query)
        return json.dumps(results, ensure_ascii=False)
    except httpx.ConnectError:
        return "Lỗi kết nối: Không thể truy cập dịch vụ tìm kiếm. Vui lòng kiểm tra kết nối mạng."
    except Exception as e:
        return f"Đã xảy ra lỗi không mong muốn khi tìm kiếm: {e}"

@tool
async def ask_vision_model_about_image(
    image_bytes: bytes,
    user_id: str,
    human_prompt: str = "Vật liệu trong ảnh là gì",
) -> str:
    """Shows an image to the Gemini vision model and asks a question about it."""
    # ... (implementation remains the same) ...

@tool
def get_historical_image_report(user_id: str, minutes_ago: int = 15) -> str:
    """
    Retrieves a past image analysis report for a user if it was created within a specified timeframe.
    """
    # ... (implementation remains the same) ...

@tool
def save_quote(project_name: str, quote_details: str) -> str:
    """
    Saves a detailed quote to a file for future reference.
    - project_name: A unique name for the project or quote (e.g., "Du_an_Vinhome_A").
    - quote_details: The full text of the quote to be saved.
    """
    # ... (implementation remains the same) ...

@tool
def get_saved_quotes() -> str:
    """Lists all previously saved quotes."""
    # ... (implementation remains the same) ...

@tool
def calculator_tool(expression: str) -> str:
    """
    Calculates the result of a mathematical expression that can include price ranges.
    Price ranges must be formatted as '(min-max)'.
    Example: "30 * (225000-380000) + 20 * (350000-7500000)"
    """
    # ... (implementation remains the same) ... 