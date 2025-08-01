from .database_utils import (
    get_all_categories,
    get_material_types,
    get_material_subtypes,
    get_material_variants,
    get_material_price,
    search_materials,
    get_price_range
)
from typing import Any, Dict, List, Optional, Tuple
def get_internal_price_new(
    category: str,
    material_type: Optional[str] = None,
    subtype: Optional[str] = None,
    variant: Optional[str] = None,
    cost_type: str = "combined"
) -> str:
    """
    Tra cứu giá vật liệu nội bộ với logic linh hoạt theo mức độ chi tiết được cung cấp.
    
    Ưu tiên:
    - Nếu có variant: tra giá chính xác
    - Nếu có subtype: tra khoảng giá subtype
    - Nếu chỉ có material_type: tra khoảng giá toàn bộ loại vật liệu
    - Nếu không có đủ thông tin: báo lỗi
    """

    cost_type_vn = {
        "material": "vật tư",
        "labor": "nhân công",
        "combined": "tổng hợp"
    }.get(cost_type, "tổng hợp")

    if variant and subtype and material_type:
        # Tra giá chính xác cho variant
        price = get_material_price(category, material_type, subtype, variant, cost_type)
        if price is not None:
            return f"Giá {cost_type_vn} cho {variant} ({subtype}, {material_type}, {category}) là {price:,.0f} VND/m²."
        else:
            return f"Không tìm thấy giá cho {variant} ({subtype}, {material_type}, {category})."
        
    elif subtype and material_type:
        # Tra khoảng giá theo subtype
        min_price, max_price = get_price_range(category, material_type, subtype, cost_type)
        if min_price is not None and max_price is not None:
            return f"Giá {cost_type_vn} cho {subtype} ({material_type}, {category}) dao động từ {min_price:,.0f} VND/m² đến {max_price:,.0f} VND/m²."
        else:
            return f"Không tìm thấy dữ liệu giá cho {subtype} ({material_type}, {category})."
        
    elif material_type:
        # Tra khoảng giá theo material_type (không cần subtype)
        subtypes = get_material_subtypes(category, material_type)
        if not subtypes:
            return f"Không tìm thấy phân loại nào cho {material_type} trong danh mục {category}."
        
        all_prices = []
        for st in subtypes:
            min_price, max_price = get_price_range(category, material_type, st, cost_type)
            if min_price is not None and max_price is not None:
                all_prices.append((min_price, max_price))

        if all_prices:
            min_all = min(p[0] for p in all_prices)
            max_all = max(p[1] for p in all_prices)
            return f"Giá {cost_type_vn} cho {material_type} ({category}) dao động từ {min_all:,.0f} VND/m² đến {max_all:,.0f} VND/m²."
        else:
            return f"Không có dữ liệu giá cho {material_type} ({category})."
    
    else:
        return "Vui lòng cung cấp ít nhất loại vật liệu (material_type) để tra cứu giá."

def main():
    print("Test 1: Đủ thông tin variant")
    print(get_internal_price_new(
        category="Sàn",
        material_type="Sàn gạch",
        subtype="Gạch men",
        variant="Gạch 300x300mm",
        cost_type="material"
    ))
    print()

    print("Test 2: Chỉ subtype + material_type")
    print(get_internal_price_new(
        category="Sàn",
        material_type="Sàn gạch",
        subtype="Gạch men"
    ))
    print()

    print("Test 3: Chỉ material_type")
    print(get_internal_price_new(
        category="Sàn",
        material_type="Sàn gạch"
    ))
    print()

    print("Test 4: Thiếu tất cả")
    print(get_internal_price_new(
        category="Sàn"
    ))
    print()

if __name__ == "__main__":
    main()