from langchain_core.tools import tool
import requests
import base64
from typing import Any, Callable, List, Optional, cast, Dict

from langchain_tavily import TavilySearch  # type: ignore[import-not-found]
import httpx  # Hoặc exception cụ thể mà Tavily SDK raise
from react_agent.configuration import Configuration
# FIX: Now importing from a central store to avoid circular dependencies.
from react_agent.memory import memory_manager
from react_agent.vision import get_gemini_vision_report

@tool
async def material_price_query(material_type: str) -> str:
    """
    Luôn sử dụng công cụ này mỗi khi người dùng đề cập đến các vật liệu thuộc các danh mục: wood, stone, paint, hoặc wallpaper. Công cụ này cho phép bạn tra cứu thông tin vật liệu có sẵn trong kho của DBplus.
    Các vật liệu được phân loại thành bốn danh mục chính: 'wood', 'stone', 'paint', 'wallpaper'. Mỗi danh mục bao gồm nhiều loại vật liệu cụ thể (ví dụ: trong danh mục gỗ sẽ có nhiều loại gỗ khác nhau).
    Các tham số hợp lệ: 'wood', 'stone', 'paint', 'wallpaper'.
    Để tra cứu chi tiết các loại vật liệu cụ thể hoặc cần các thông tin về chúng, hãy tìm theo danh mục tương ứng.
    """
    valid_materials = ["wood", "stone", "paint", "wallpaper"]
    material = material_type.lower()

    if material not in valid_materials:
        return f"Invalid material type '{material_type}'. Please use one of {valid_materials}."

    try:
        with open(f"data/{material}.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return f"No pricing data found for material: {material}"
    except Exception as e:
        return f"An error occurred: {e}"


@tool
async def search(query: str) -> Optional[Dict[str, Any]]:
    """
    Tìm kiếm thông tin từ web.

    Chức năng này sử dụng công cụ tìm kiếm để tra cứu thông tin đầy đủ, chính xác và cập nhật mới nhất.
    Sử dụng cho các trường hợp sau:
    1. Trả lời các câu hỏi liên quan đến sự kiện thời sự, giá thị trường, giá ngoài thị trường.

    2. Kiểm tra giá thi công thị trường hoặc tham khảo giá bên ngoài đối với các vật liệu không được hỗ trợ bởi công cụ material_price_query.

    3. Cung cấp kiến thức chung hoặc tin tức khi người dùng yêu cầu.

    Lưu ý:
    Keyword search là những từ khóa tiếng việt chung chung, không cần tìm kiếm cụ thể nếu như user không yêu cầu (Ví dụ: User hỏi giá gỗ công ty đối thủ -> Thì search là giá gỗ (vì đâu biết đối thủ là ai))
    Luôn ghi rõ rằng các mức giá từ kết quả tìm kiếm này chỉ mang tính tham khảo theo giá thi công thị trường và kèm theo ngày truy xuất.
    """
    configuration = Configuration.from_context()
    wrapped = TavilySearch(max_results=configuration.max_search_results)

    try:
        result = await wrapped.ainvoke({"query": query})
        return result
    except httpx.HTTPStatusError as e:
        if e.response.status_code in [404, 502]:
            return {
                "message": (
                    "API Tavily đang gặp lỗi (mã lỗi: {}). "
                    "Vui lòng thử lại sau hoặc sử dụng kiến thức có sẵn của tôi để tham khảo. "
                    "Xin lưu ý: API đang lỗi nên giá trị trả về chỉ mang tính tham khảo."
                ).format(e.response.status_code)
            }
        raise  # Nếu lỗi khác thì raise tiếp
    except Exception as e:
        # Nếu muốn, bạn có thể log hoặc trả về 1 thông báo chung cho lỗi không xác định
        return {
            "message": (
                "API Tavily đang gặp sự cố. Vui lòng thử lại sau "
                "hoặc sử dụng kiến thức có sẵn của tôi để tham khảo."
            )
        }

@tool
async def ask_vision_model_about_image(question: str, conversation_id: str) -> str:
    """
    Dùng để hỏi một câu hỏi MỚI và CỤ THỂ về hình ảnh đã được tải lên trong cuộc trò chuyện.
    Chỉ sử dụng công cụ này khi BÁO CÁO PHÂN TÍCH HÌNH ẢNH ban đầu không đủ thông tin để trả lời câu hỏi của người dùng.
    Ví dụ: "Gỗ trong ảnh có phải là gỗ sồi không?".
    Yêu cầu phải có 'conversation_id' từ trạng thái của agent.
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


TOOLS: List[Callable[..., Any]] = [
    search, 
    material_price_query,
    ask_vision_model_about_image
]
