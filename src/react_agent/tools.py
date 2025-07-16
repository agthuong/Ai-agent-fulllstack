from langchain_core.tools import tool
import requests
import base64
import json
import os
import datetime
from typing import Any, Callable, List, Optional, cast, Dict
import re

from langchain_tavily import TavilySearch  # type: ignore[import-not-found]
import httpx  # Hoặc exception cụ thể mà Tavily SDK raise
from react_agent.configuration import Configuration
# FIX: Now importing from a central store to avoid circular dependencies.
from react_agent.memory import memory_manager
from react_agent.vision import get_gemini_vision_report

# --- Path setup for data files ---
# Get the absolute path to the directory where this script (tools.py) is located.
# This ensures that the data path is resolved correctly, regardless of the execution directory.
_current_dir = os.path.dirname(os.path.abspath(__file__))
# Construct the path to the 'data_new' directory, which is two levels up from 'src/react_agent'.
_data_dir = os.path.join(_current_dir, '..', '..', 'data_new')


# Tạo thư mục để lưu báo giá nếu chưa tồn tại
QUOTES_DIR = "saved_quotes"
os.makedirs(QUOTES_DIR, exist_ok=True)

@tool
async def material_price_query(material_type: str, type: Optional[str] = None, mode: str = 'range') -> str:
    """
    Use this tool to look up the official construction price from DBPlus for various materials.

    **MODES:**
    - `mode='range'`: (Default) Returns the min-max price range for the specified material type. Use this for initial quotes.
    - `mode='full_list'`: Returns a detailed list of all variants and their specific prices. Use this ONLY when the user needs to select a specific option based on a budget or detailed requirements.

    **RULES:**
    - Always use `mode='range'` first.
    - If the user provides a specific `type` (e.g., "gỗ sồi"), the range will be for the variants within that type.
    - If `type` is not provided, the range will be for the entire material category (e.g., all "wood").
    - From an [IMAGE REPORT], use `Type chính` for `material_type` and `Loại cụ thể` for `type`.

    **Parameters:**
    - `material_type`: The material category (`wood`, `stone`, `paint`, `wallpaper`).
    - `type`: The specific material type (e.g., `Marble`, `Oak`).
    - `mode`: The operational mode, either `'range'` (default) or `'full_list'`.
    """

    # Helper function to parse price strings robustly
    def _parse_price(price_str: str) -> Optional[float]:
        try:
            # Take the first part of the string before any space and remove non-digits
            price_part = price_str.split(' ')[0]
            cleaned_str = re.sub(r'[^\d]', '', price_part)
            if cleaned_str:
                return float(cleaned_str)
            return None
        except (ValueError, TypeError, IndexError):
            return None

    # --- Step 1: Standardize material_type ---
    material_mapping = {
        "gỗ": "wood",
        "đá": "stone",
        "sơn": "paint",
        "giấy dán tường": "wallpaper",
        "giấy dán": "wallpaper",
        "wood": "wood",
        "stone": "stone",
        "paint": "paint",
        "wallpaper": "wallpaper"
    }
    material_lower = material_type.lower()
    material = material_mapping.get(material_lower, material_lower)
    
    valid_materials = ["wood", "stone", "paint", "wallpaper"]
    if material not in valid_materials:
        return f"Invalid material type '{material_type}'. Please use one of {valid_materials}."


    # --- Step 2: Load data and determine scope based on 'type' ---
    try:
        # Use the absolute path to the data file
        filepath = os.path.join(_data_dir, f"{material.capitalize()}.json")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return f"Không tìm thấy file dữ liệu cho vật liệu: {material_type}"
    except Exception as e:
        return f"Đã xảy ra lỗi khi đọc file dữ liệu cho '{material_type}': {str(e)}"

    # Map aliases to standardized types
    if isinstance(type, list):
        # If type is a list, take the first element. This can happen with complex tool inputs.
        type = type[0] if type else None
        
    type_lower = type.lower() if type else None
    type_mapping = {
        # Đá (Stone)
        "marble": "Marble", "đá marble": "Marble", "đá cẩm thạch": "Marble", "cẩm thạch": "Marble",
        "granite": "Granite", "đá granite": "Granite",
        "onyx": "Onyx", "đá onyx": "Onyx",
        "quartz": "Quartz", "đá quartz": "Quartz",

        # Gỗ (Wood)
        "oak": "Oak", "gỗ oak": "Oak", "gỗ sồi": "Oak", "sồi": "Oak",
        "walnut": "Walnut", "gỗ walnut": "Walnut", "gỗ óc chó": "Walnut", "óc chó": "Walnut",
        "ash": "Ash", "gỗ ash": "Ash", "gỗ tần bì": "Ash", "tần bì": "Ash",
        "xoan đào": "Xoan đào", "gỗ xoan đào": "Xoan đào",
        "lim": "Lim", "gỗ lim": "Lim",
        "gỗ đỏ": "Gỗ đỏ",
        "mdf": "MDF", "gỗ mdf": "MDF",
        "plywood": "Plywood", "gỗ plywood": "Plywood", "gỗ ván ép": "Plywood", "ván ép": "Plywood",

        # Sơn (Paint)
        "color paint": "Sơn màu", 
        "sơn màu": "Sơn màu", "sơn gốc nước": "Sơn màu", "sơn gốc dầu": "Sơn màu", "sơn nhũ tương": "Sơn màu", "sơn epoxy": "Sơn màu",
        "texture effect paint": "Sơn giả hiệu ứng bề mặt", 
        "sơn giả hiệu ứng": "Sơn giả hiệu ứng bề mặt", "sơn giả xi măng": "Sơn giả hiệu ứng bề mặt", "sơn giả đá": "Sơn giả hiệu ứng bề mặt", "sơn vân mây": "Sơn giả hiệu ứng bề mặt", "sơn ánh kim": "Sơn giả hiệu ứng bề mặt",

        # Giấy dán tường (Wallpaper)
        "floral": "Floral", "hoa": "Floral", "giấy dán tường hoa": "Floral",
        "stripes": "Stripes", "sọc": "Stripes", "giấy dán tường sọc": "Stripes",
        "plain / texture": "Plain / Texture", "trơn": "Plain / Texture", "giấy dán tường trơn": "Plain / Texture", "texture": "Plain / Texture", "giấy dán tường texture": "Plain / Texture",
        "geometric": "Geometric", "hình học": "Geometric", "giấy dán tường hình học": "Geometric",
        "classic / vintage": "Classic / Vintage", "cổ điển": "Classic / Vintage", "giấy dán tường cổ điển": "Classic / Vintage", "vintage": "Classic / Vintage", "giấy dán tường vintage": "Classic / Vintage",
        "nature / scenic": "Nature / Scenic", "thiên nhiên": "Nature / Scenic", "giấy dán tường thiên nhiên": "Nature / Scenic",
        "material imitation": "Material Imitation", "giả vật liệu": "Material Imitation", "giấy dán tường giả vật liệu": "Material Imitation"
    }
    mapped_type = type_mapping.get(type_lower, None) if type_lower else None

    # Filter data based on the mapped_type. If no type, use all data.
    target_data = {}
    range_title = ""
    if mapped_type and mapped_type in data:
        target_data = {mapped_type: data[mapped_type]}
        range_title = f"{material_type} - {mapped_type}"
    else:
        # If type is null, invalid, or not found, operate on the entire material category
        target_data = data
        range_title = f"{material_type}"
        # If a specific (but invalid) type was passed, notify the user it wasn't found.
        if type:
            # We will proceed with the full category, but the message should be clear.
            range_title = f"{material_type} (không tìm thấy loại '{type}')"


    # --- Step 3: Execute mode ('full_list' or 'range') ---

    # Handle "full_list" mode
    if mode == 'full_list':
        # If the target_data is empty (e.g., invalid type specified), return a clear message
        if not target_data or not any(target_data.values()):
            return f"Không có dữ liệu chi tiết cho loại '{type}' trong danh mục '{material_type}'."
            
        result = f"Bảng giá thi công chi tiết cho {range_title.replace(' (không tìm thấy loại', ' - loại')}:\n\n"
        for category, items in target_data.items():
            result += f"## {category}\n"
            for variant, price in items.items():
                result += f"- {variant}: {price}\n"
            result += "\n"
        return result

    # Handle "range" mode (default)
    all_prices = []
    for category_data in target_data.values():
        if isinstance(category_data, dict):
            for price_str in category_data.values():
                price = _parse_price(price_str)
                if price is not None:
                    all_prices.append(price)

    if not all_prices:
        if type:
             # If a specific type was requested but no prices found, inform the user
             return f"Không tìm thấy thông tin giá cho loại '{type}' trong danh mục '{material_type}'. Cân nhắc kiểm tra toàn bộ danh mục."
        return f"Không tìm thấy thông tin giá có thể phân tích cho danh mục '{material_type}'."

    min_price = min(all_prices)
    max_price = max(all_prices)
    
    # Return a different message if min and max are the same
    if min_price == max_price:
        return f"Giá thi công cho {range_title} của DBPlus là {min_price:,.0f} VND/m²."

    return (f"Giá thi công cho {range_title} của DBPlus dao động từ "
            f"{min_price:,.0f} VND/m² đến {max_price:,.0f} VND/m².")


@tool
async def get_historical_image_report(query: str, conversation_id: str) -> str:
    """
    Use this tool to retrieve and view image reports that have been previously analyzed in the current conversation.  
    This tool is useful when the user asks about images they shared earlier.

    **How to use:**  
    - If the user asks about the “first image” or “oldest image”, set `query = "đầu tiên"`.  
    - If the user asks about the “last image” or “most recent image”, set `query = "cuối cùng"`.  
    - If the user asks for a specific image by order (e.g., “second image”, “third image”), set `query` to the corresponding number (e.g., `"2"`, `"3"`).  
    - If the order cannot be determined, keep the user’s query as-is to search for matching descriptions in the reports.

    **Parameters:**  
    - `query`: A description of the image to find (e.g., `"đầu tiên"`, `"cuối cùng"`, `"2"`, `"ảnh có sàn gỗ"`).  
    - `conversation_id`: The ID of the current conversation. This must always be provided.
    """
    try:
        # Lấy danh sách các tin nhắn HumanMessage có chứa báo cáo hình ảnh đi kèm
        image_messages = memory_manager.get_messages_with_images(conversation_id)

        if not image_messages:
            return "Không tìm thấy báo cáo hình ảnh nào trong lịch sử cuộc trò chuyện này."

        num_images = len(image_messages)

        # Xử lý các truy vấn dựa trên thứ tự
        if query.lower() in ["đầu tiên", "first", "oldest", "1"]:
            target_index = 0
        elif query.lower() in ["cuối cùng", "last", "latest", str(num_images)]:
            target_index = num_images - 1
        else:
            try:
                # Thử chuyển đổi query thành số (ví dụ: "2", "3")
                target_index = int(str(query)) - 1
                if not (0 <= target_index < num_images):
                    return f"Chỉ có {num_images} hình ảnh trong lịch sử. Vui lòng cung cấp một số hợp lệ từ 1 đến {num_images}."
            except ValueError:
                # Nếu không phải là số, tìm kiếm dựa trên nội dung
                if not isinstance(query, str):
                     return "Loại truy vấn không hợp lệ để tìm kiếm nội dung."
                search_term = str(query).lower()
                found_reports = []
                for i, (msg, report) in enumerate(image_messages):
                    if search_term in msg.content.lower() or search_term in report.lower():
                        found_reports.append(f"Kết quả phù hợp #{i+1}:\n- Truy vấn gốc: {msg.content}\n- Báo cáo hình ảnh:\n{report}")
                
                if not found_reports:
                    return f"Không tìm thấy báo cáo hình ảnh nào khớp với mô tả '{query}'."
                
                return "\n\n".join(found_reports)

        # Trả về báo cáo tại chỉ mục đã xác định
        message, report = image_messages[target_index]
        return (f"Đã tìm thấy báo cáo cho hình ảnh thứ {target_index + 1} (trong tổng số {num_images} ảnh):\n"
                f"- Truy vấn gốc của người dùng: {message.content}\n"
                f"- Báo cáo hình ảnh:\n{report}")

    except Exception as e:
        return f"Đã xảy ra lỗi khi truy xuất báo cáo hình ảnh: {str(e)}"


def _format_search_results(results: dict) -> str:
    """Formats search results into a readable string."""
    if not results or not results.get("results"):
        return "Không tìm thấy kết quả tìm kiếm nào."

    formatted_lines = []
    for res in results["results"]:
        line = (
            f"Tiêu đề: {res.get('title', 'Không có tiêu đề')}\n"
            f"Nguồn: {res.get('url', 'Không có URL')}\n"
            f"Nội dung: {res.get('content', 'Không có nội dung').strip()}"
        )
        formatted_lines.append(line)

    return "\n\n---\n\n".join(formatted_lines)


@tool
async def search(query: str) -> str:
    """
    Searches for information on the web, especially for market construction prices.

    This function uses a search engine to look up complete, accurate, and up-to-date information.
    Use for the following cases:

        1. Answering questions related to current events, market prices, and over-the-counter prices.

        2. Checking market construction prices or referencing external prices for materials not supported by the material_price_query tool.

        3. Providing general knowledge or news when the user requests it.

    Note:
        1. This tool only returns raw data from the web.

        2. The agent must always clearly state that the prices from these search results are for reference only, based on market prices, and include the retrieval date when responding to the user.

    Parameters:
        - query: The search keyword in Vietnamese, which should be concise and focused on the product or service to be looked up (e.g.: "giá thi công sơn nước", "giá thi công đá marble trắng").
    """
    try:
        # Giảm số lượng kết quả để prompt gọn hơn, tránh làm nhiễu mô hình
        tavily_search = TavilySearch(max_results=3)
        results = await tavily_search.ainvoke(query)
        
        # Xử lý các loại kết quả trả về từ Tavily
        if isinstance(results, str):
            # Nếu là chuỗi, có thể là câu trả lời trực tiếp hoặc lỗi
            return results

        if isinstance(results, dict) and "results" in results:
            # Nếu là dict và có key 'results', đây là định dạng mong muốn
            return _format_search_results(results)

        # Fallback cho các định dạng không mong muốn khác
        return f"Kết quả tìm kiếm không ở định dạng mong muốn: {results}"

    except httpx.ConnectError as e:
        return f"Lỗi kết nối khi tìm kiếm: {e}. Vui lòng kiểm tra kết nối mạng."
    except Exception as e:
        return f"Đã xảy ra lỗi không mong muốn khi tìm kiếm: {str(e)}"

@tool
async def ask_vision_model_about_image(question: str, conversation_id: str) -> str:
    """
    Used to ask a NEW and SPECIFIC question about an image that has been uploaded in the conversation.
    Only use this tool when the initial IMAGE ANALYSIS REPORT is insufficient to answer the user's question.
    Example: "Is the wood in the picture oak?".
    Requires the 'conversation_id' from the agent's state.
    """
    if not conversation_id:
        return "Error: Could not ask about the image because the conversation_id was not provided."

    image_context = memory_manager.get_image_context(conversation_id)
    if not image_context or "image_base64" not in image_context:
        return "Error: No image was found for this conversation. The user must upload an image first."
        
    try:
        image_bytes = base64.b64decode(image_context["image_base64"])
        response = get_gemini_vision_report(image_bytes, question)
        return response
    except Exception as e:
        return f"An error occurred while analyzing the image: {e}"

@tool
async def save_quote(quote_content: str, project_name: Optional[str] = None, conversation_id: Optional[str] = None) -> str:
    """
    Store the preliminary quote in the system for future reference.

    IMPORTANT: ONLY use this tool if the user EXPLICITLY requests or confirms that they want to save the quote.  
    DO NOT automatically use this tool if the user only asks for a quote or inquires about prices.

    Use this tool IF AND ONLY IF:  
    - The user EXPLICITLY confirms or finalizes a preliminary quote  
    - The user EXPLICITLY requests to save the generated preliminary quote

    Direct trigger keywords include:  
    "lưu báo giá", "lưu lại báo giá này", "tôi chốt báo giá này",  
    "xác nhận báo giá", "chốt báo giá", "có, lưu giúp tôi", "đồng ý lưu lại"

    Parameters:  
    - `quote_content`: The full content of the preliminary quote to be saved  
    - `project_name`: Project name or note for easier future reference (optional)  
    - `conversation_id`: The current conversation ID (optional, will be used if available)

    Returns a confirmation message that the quote has been saved successfully.
    """

    # Lấy thông tin ngày giờ hiện tại
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    date_formatted = now.strftime("%d/%m/%Y")
    
    # Tạo tên file và thông tin người dùng mẫu
    user_name = "Khách hàng Demo"  # Giả lập người dùng cho demo
    
    # Tạo tên file với định dạng rõ ràng hơn
    time_str = now.strftime("%Y%m%d_%H%M%S")
    
    # Tạo tên dự án mặc định nếu không được cung cấp
    if not project_name:
        # Trích xuất thông tin từ nội dung báo giá để tạo tên có ý nghĩa
        project_name_parts = []
        
        # Kiểm tra nội dung báo giá để tạo tên mô tả
        if "tường" in quote_content.lower():
            project_name_parts.append("Tuong")
        if "sàn" in quote_content.lower():
            project_name_parts.append("San")
        if "trần" in quote_content.lower():
            project_name_parts.append("Tran")
            
        # Thêm thông tin vật liệu nếu có
        if "đá" in quote_content.lower() or "marble" in quote_content.lower():
            project_name_parts.append("Da")
        if "gỗ" in quote_content.lower():
            project_name_parts.append("Go")
        if "sơn" in quote_content.lower():
            project_name_parts.append("Son")
        if "giấy dán" in quote_content.lower():
            project_name_parts.append("Giay")
            
        # Nếu không tìm thấy thông tin cụ thể, sử dụng tên mặc định
        if not project_name_parts:
            project_name = f"BaoGia_{time_str}"
        else:
            project_name = f"BaoGia_{'_'.join(project_name_parts)}_{time_str}"
    
    # Tạo tên file cuối cùng
    file_name = f"{time_str}_{project_name}.json"
    
    # Tạo đối tượng báo giá
    quote_data = {
        "timestamp": timestamp,
        "date": date_formatted,
        "user": user_name,
        "conversation_id": conversation_id,
        "project_name": project_name,
        "content": quote_content
    }
    
    # Lưu vào file
    file_path = os.path.join(QUOTES_DIR, file_name)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(quote_data, f, ensure_ascii=False, indent=2)
            
        # Tạo thông báo chi tiết hơn về báo giá đã lưu
        details = []
        if "tường" in quote_content.lower():
            if "m2" in quote_content.lower() or "m²" in quote_content.lower():
                # Cố gắng trích xuất diện tích tường
                import re
                area_match = re.search(r'tường.*?(\d+)[\s]*(m2|m²)', quote_content.lower())
                if area_match:
                    details.append(f"tường {area_match.group(1)}m²")
                else:
                    details.append("tường")
            else:
                details.append("tường")
                
        if "sàn" in quote_content.lower():
            if "m2" in quote_content.lower() or "m²" in quote_content.lower():
                # Cố gắng trích xuất diện tích sàn
                import re
                area_match = re.search(r'sàn.*?(\d+)[\s]*(m2|m²)', quote_content.lower())
                if area_match:
                    details.append(f"sàn {area_match.group(1)}m²")
                else:
                    details.append("sàn")
            else:
                details.append("sàn")
                
        if "trần" in quote_content.lower():
            details.append("trần")
            
        detail_text = ", ".join(details) if details else "báo giá tổng hợp"
        
        return f"Đã lưu báo giá thành công với tên '{project_name}' vào ngày {date_formatted}.\nChi tiết: Báo giá cho {detail_text}."
    except Exception as e:
        return f"Có lỗi khi lưu báo giá: {str(e)}"

@tool
async def get_saved_quotes(time_period: Optional[str] = None, project_keyword: Optional[str] = None) -> str:
    """
    Look up and display previously saved preliminary quotes.

    Use this tool when:  
    - The user requests to review previously saved quotes  
    - The user wants to find a quote by time period or project keyword  
    - The user needs to check their quote history

    Common trigger keywords:  
    "xem báo giá cũ", "báo giá đã lưu", "lịch sử báo giá", "báo giá trước đó"

    Parameters:  
    - `time_period`: The time range to search for (e.g., "today", "this week", "this month") — optional  
    - `project_keyword`: A keyword related to the project name — optional

    Returns a list of saved quotes or the details of a specific quote if found.
    """
    # Kiểm tra thư mục báo giá
    if not os.path.exists(QUOTES_DIR) or not os.listdir(QUOTES_DIR):
        return "Không tìm thấy báo giá nào đã được lưu trước đó."
    
    # Lấy tất cả file báo giá
    quote_files = [f for f in os.listdir(QUOTES_DIR) if f.endswith('.json')]
    
    if not quote_files:
        return "Không tìm thấy báo giá nào đã được lưu trước đó."
    
    # Lọc theo thời gian nếu được chỉ định
    today = datetime.datetime.now().date()
    filtered_quotes = []
    
    for file_name in quote_files:
        file_path = os.path.join(QUOTES_DIR, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                quote_data = json.load(f)
                
            # Chuyển đổi timestamp thành datetime để so sánh
            if 'timestamp' in quote_data:
                quote_date = datetime.datetime.strptime(
                    quote_data['timestamp'].split('_')[0], "%Y-%m-%d"
                ).date()
                
                # Lọc theo thời gian nếu được chỉ định
                if time_period:
                    time_period_lower = time_period.lower()
                    if "hôm nay" in time_period_lower and quote_date != today:
                        continue
                    elif "tuần này" in time_period_lower:
                        start_of_week = today - datetime.timedelta(days=today.weekday())
                        if quote_date < start_of_week:
                            continue
                    elif "tháng này" in time_period_lower:
                        if quote_date.month != today.month or quote_date.year != today.year:
                            continue
                
                # Lọc theo từ khóa dự án nếu được chỉ định
                if project_keyword and 'project_name' in quote_data:
                    if project_keyword.lower() not in quote_data['project_name'].lower():
                        continue
                
                filtered_quotes.append(quote_data)
        except Exception as e:
            print(f"Error reading quote file {file_name}: {e}")
    
    # Nếu không có báo giá nào sau khi lọc
    if not filtered_quotes:
        return f"Không tìm thấy báo giá nào phù hợp với điều kiện tìm kiếm của [HUMAN]."
    
    # Sắp xếp báo giá theo thời gian, mới nhất lên đầu
    filtered_quotes.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Nếu chỉ có một báo giá phù hợp, hiển thị đầy đủ với định dạng dễ đọc hơn
    if len(filtered_quotes) == 1:
        quote = filtered_quotes[0]
        project_name = quote.get('project_name', 'Không có tên')
        date = quote.get('date', 'Không rõ')
        user = quote.get('user', 'Không rõ')
        content = quote.get('content', 'Không có nội dung')
        
        # Tạo mô tả chi tiết về báo giá
        content_lower = content.lower()
        details = []
        
        # Xác định các hạng mục trong báo giá
        if "tường" in content_lower:
            # Cố gắng trích xuất số lượng tường và diện tích
            import re
            wall_count_match = re.search(r'(\d+)\s*tường', content_lower)
            wall_area_match = re.search(r'tường.*?(\d+)[\s]*(m2|m²)', content_lower)
            
            wall_info = "tường"
            if wall_count_match:
                wall_info = f"{wall_count_match.group(1)} {wall_info}"
            if wall_area_match:
                wall_info += f" ({wall_area_match.group(1)}m²)"
                
            details.append(wall_info)
            
        if "sàn" in content_lower:
            # Cố gắng trích xuất diện tích sàn
            import re
            floor_area_match = re.search(r'sàn.*?(\d+)[\s]*(m2|m²)', content_lower)
            
            floor_info = "sàn"
            if floor_area_match:
                floor_info += f" ({floor_area_match.group(1)}m²)"
                
            details.append(floor_info)
            
        if "trần" in content_lower:
            details.append("trần")
            
        # Xác định các vật liệu trong báo giá
        materials = []
        if "đá" in content_lower or "marble" in content_lower:
            materials.append("đá")
        if "gỗ" in content_lower:
            materials.append("gỗ")
        if "sơn" in content_lower:
            materials.append("sơn")
        if "giấy dán" in content_lower:
            materials.append("giấy dán tường")
            
        detail_text = ", ".join(details) if details else "báo giá tổng hợp"
        if materials:
            detail_text += f" (vật liệu: {', '.join(materials)})"
            
        return f"""Đã tìm thấy 1 báo giá:

                Tên dự án: {project_name}
                Ngày tạo: {date}
                Người dùng: {user}
                Mô tả: Báo giá cho {detail_text}

                Chi tiết báo giá:
                {content}
                """
            
    # Nếu có nhiều báo giá, hiển thị danh sách tóm tắt với thông tin chi tiết hơn
    summary = f"Đã tìm thấy {len(filtered_quotes)} báo giá:\n\n"
    
    for i, quote in enumerate(filtered_quotes, 1):
        project_name = quote.get('project_name', 'Báo giá không tên')
        date = quote.get('date', 'Không rõ')
        
        # Trích xuất thông tin chi tiết từ nội dung báo giá
        content = quote.get('content', '')
        details = "Báo giá sơ bộ"
        
        # Cố gắng xác định loại báo giá từ nội dung
        if content:
            content_lower = content.lower()
            items = []
            
            # Kiểm tra các hạng mục
            if "tường" in content_lower:
                items.append("tường")
            if "sàn" in content_lower:
                items.append("sàn")
            if "trần" in content_lower:
                items.append("trần")
                
            # Kiểm tra vật liệu
            materials = []
            if "đá" in content_lower or "marble" in content_lower:
                materials.append("đá")
            if "gỗ" in content_lower:
                materials.append("gỗ")
            if "sơn" in content_lower:
                materials.append("sơn")
            if "giấy dán" in content_lower:
                materials.append("giấy dán tường")
                
            if items:
                details = f"Báo giá cho {', '.join(items)}"
                if materials:
                    details += f" ({', '.join(materials)})"
        
        summary += f"{i}. {project_name}\n   Ngày: {date}\n   Chi tiết: {details}\n"
    
    summary += "\nĐể xem chi tiết một báo giá cụ thể, vui lòng yêu cầu với tên dự án hoặc ngày tạo."
    
    return summary


TOOLS: List[Callable[..., Any]] = [
    search, 
    material_price_query,
    ask_vision_model_about_image,
    save_quote,
    get_saved_quotes
]
