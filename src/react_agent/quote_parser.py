"""
Phân tích báo cáo hình ảnh để trích xuất thông tin về các hạng mục vật liệu
"""
import re
import json
import logging
from typing import List, Dict, Any

# Thiết lập logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_image_report(image_report: str) -> List[Dict[str, Any]]:
    """
    Parses an image analysis report and returns a list of material components.
    Hỗ trợ cả trường hợp nhiều vật liệu trên một dòng (không có xuống dòng).
    """
    if not image_report:
        return []
    components = []
    # Tách các entry bằng regex: mỗi entry bắt đầu bằng 'Material:'
    entries = re.split(r'(?=Material:)', image_report.strip())
    for entry in entries:
        line = entry.strip()
        if not line.startswith("Material:"):
            continue
        # Bỏ qua entry không đủ 4 trường
        if line.count('-') < 3:
            continue
        logger.info(f"Analyzing material line: {line}")
        match = re.search(
            r"Material:\s*(?P<material>.*?)\s*-\s*Type:\s*(?P<type>.*?)\s*-\s*Position:\s*(?P<position>.*?)\s*-\s*InStock:\s*(?P<in_stock>\w+)",
            line
        )
        if not match:
            logger.warning(f"Could not parse line: {line}")
            continue
        data = match.groupdict()
        component = {
            "material_type": data["material"].strip(),
            "type": data["type"].strip() if data["type"].strip().lower() != "null" else None,
            "position": data["position"].strip(),
            "in_stock": data["in_stock"].strip().lower()
        }
        if component["in_stock"] == "true":
            component["in_stock"] = True
        elif component["in_stock"] == "false":
            component["in_stock"] = False
        components.append(component)
    logger.info(f"Extracted {len(components)} components from image report")
    return components

def format_components_for_display(components):
    """
    Định dạng danh sách hạng mục để hiển thị
    
    Args:
        components: Danh sách hạng mục vật liệu
        
    Returns:
        str: Chuỗi thông tin hạng mục đã định dạng
    """
    if not components:
        return "Không có hạng mục nào được nhận diện"
    
    result = "# Các Hạng Mục Nhận Diện\n\n"
    result += "| Vị trí | Vật liệu | Loại | Trạng thái |\n"
    result += "|--------|----------|------|------------|\n"
    
    for comp in components:
        position = comp.get("position", "Không xác định")
        material = comp.get("material_type", "Không xác định")
        material_type = comp.get("type", "Không xác định")
        
        # Xác định trạng thái
        in_stock = comp.get("in_stock", False)
        if in_stock == True:
            status = "Có sẵn ✅"
        elif in_stock == "only_material":
            status = "Chỉ biết loại vật liệu ⚠️"
        else:
            status = "Cần đặt hàng ⏳"
        
        result += f"| {position} | {material} | {material_type} | {status} |\n"
    
    return result 