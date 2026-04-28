from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime, timedelta
from app.db import get_conn
import redis
import qrcode
import base64
from io import BytesIO
from typing import Optional
from datetime import datetime

router = APIRouter()

# Redis 客户端
redis_client = redis.Redis(host="192.168.200.203", port=6379, db=0, decode_responses=True)

class GenerateItem(BaseModel):
    productNo: str
    spec: str
    supplierId: int
    supplierName: str
    length: float
    coatingDate: Optional[datetime] = None

def get_today_end_timestamp() -> int:
    """获取当天结束时间戳（秒）"""
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(tomorrow.timestamp())

def generate_company_goods_number(product_no: str) -> str:
    """生成货物唯一编号"""
    date_part = datetime.now().strftime("%y%m%d")
    redis_key = f"goods_num_seq:{product_no}:{date_part}"
    seq = redis_client.incr(redis_key)
    if seq == 1:
        redis_client.expireat(redis_key, get_today_end_timestamp())
    seq_part = str(seq).zfill(5)
    return f"{product_no}{date_part}{seq_part}"

def generate_goods_num(product_no: str) -> str:
    return generate_company_goods_number(product_no)

def generate_qr_base64(content: str) -> str:
    """生成二维码 base64"""
    qr = qrcode.QRCode(version=2, box_size=6, border=2)
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()

def get_goods_name(product_no: str, cursor) -> str:
    """根据产品编码获取产品名称"""
    cursor.execute(
        "select CompanyPurchaseProductName from biz_company_purchase_product where  Deleted=false  and  CompanyPurchaseProductNo=%s limit 1",
        (product_no,)
    )
    res = cursor.fetchone()
    return res['CompanyPurchaseProductName'] if res else product_no

@router.post("/generate")
def generate(items: List[GenerateItem], request: Request):
    finished_order_id = request.headers.get("X-FinishedOrderId")
    if not finished_order_id:
        raise HTTPException(status_code=400, detail="缺少 X-FinishedOrderId 请求头")

    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            # 查询仓库信息
            cursor.execute(
                "SELECT WarehouseId FROM biz_company_purchase_finished_order WHERE CompanyPurchaseFinishedOrderId=%s",
                (finished_order_id,)
            )
            warehouse = cursor.fetchone()
            if not warehouse:
                raise HTTPException(status_code=404, detail="加工订单仓库未找到")
            warehouse_id = warehouse["WarehouseId"]

            # 查询货架信息
            cursor.execute(
                "SELECT id AS shelfId, number AS shelfName FROM store_shelf "
                "WHERE warehouse_id=%s AND material_type=3 AND shelf_type=2 AND temp=0 LIMIT 1",
                (warehouse_id,)
            )
            shelf = cursor.fetchone()
            if not shelf:
                raise HTTPException(status_code=404, detail="仓库货架未找到")
            shelf_id = shelf["shelfId"]
            shelf_name = shelf["shelfName"]

            inserted_ids = []
            goods_cards = []
            shelf_cards_map = {}
            for item in items:
                # 插入库存货物
                fields = [
                    "goods_num", "product_no", "goods_category_id", "goods_category", 
                    "goods_name", "goods_specification", "goods_unit", "goods_unit_id", 
                    "warehouse_name", "warehouse_id", "length_weight", "goods_location", 
                    "factory_name", "factory_id", "in_stock_time", "goods_status", 
                    "material_type", "is_print", "company_purchase_supplier_id",
                    "company_purchase_supplier_name", "company_purchase_finished_order_id",
                    "create_id", "remark", "standard", "create_time", "shelf_id","product_date","lamination_time"
                ]
                sql = f"INSERT INTO store_company_purchase_goods({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))})"
                print(item)
                params = [
                    generate_goods_num(item.productNo),
                    item.productNo,
                    1981622202218487808,
                    "生产材料",
                    get_goods_name(item.productNo, cursor),
                    item.spec,
                    "米",
                    1981622406481092608,
                    shelf_name,
                    warehouse_id,
                    item.length,
                    shelf_name,
                    None,
                    None,
                    datetime.now(),
                    2,
                    1,
                    1,
                    item.supplierId,
                    item.supplierName,
                    finished_order_id,
                    99999,
                    "加工单助手一键入库",
                    1,
                    datetime.now(),
                    shelf_id,
                    datetime.now(),
                    item.coatingDate
                ]
                cursor.execute(sql, tuple(params))
                goods_id = cursor.lastrowid
                inserted_ids.append(goods_id)

                goods_cards.append({
                    "goodsId": goods_id,
                    "goodsName": params[4],
                    "productNo": item.productNo,
                    "goodsNum": params[0],
                    "spec": item.spec,
                    "supplierName": item.supplierName,
                    "qrCode": generate_qr_base64(f"goods://{goods_id}?productId={params[0]}"),
                    "length": item.length
                })

                # 货架卡片
                if shelf_id not in shelf_cards_map:
                    shelf_cards_map[shelf_id] = {
                        "shelfId": shelf_id,
                        "shelfName": shelf_name,
                        "qrCode": generate_qr_base64(f"store://{shelf_id}?x=1&y=1")
                    }

                # 插入货物货架关系
                cursor.execute("""
                    INSERT INTO store_goods_shelf(goods_id, shelf_id, location_x, location_y, update_time)
                    VALUES (%s, %s, %s, %s, %s)
                """, (goods_id, shelf_id, 1, 1, datetime.now()))

            conn.commit()
            return {
                "success": True,
                "count": len(inserted_ids),
                "goodsCards": goods_cards,
                "shelfCards": list(shelf_cards_map.values())
            }

    except Exception as e:
        conn.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()