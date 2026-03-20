from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime
from app.db import get_conn
from datetime import datetime, timedelta
import redis
import qrcode
import base64
from io import BytesIO

redis_client = redis.Redis(host="192.168.200.203", port=6379, db=0, decode_responses=True)

router = APIRouter()

class GenerateItem(BaseModel):
    productNo: str
    spec: str
    supplierId: int
    supplierName: str
    length: float

def get_today_end_timestamp():
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(tomorrow.timestamp())


def generate_company_goods_number(product_no: str) -> str:
    date_part = datetime.now().strftime("%y%m%d")
    redis_key = f"goods_num_seq:{product_no}:{date_part}"

    seq = redis_client.incr(redis_key)

    if seq == 1:
        redis_client.expireat(redis_key, get_today_end_timestamp())

    seq_part = str(seq).zfill(5)

    return f"{product_no}{date_part}{seq_part}"

def generate_goods_num(product_no:str):
    """生成唯一货物编号"""
    # return f"P{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000,9999)}"
    return generate_company_goods_number(product_no)

def generate_qr_base64(content: str):
    qr = qrcode.QRCode(
        version=2,
        box_size=6,
        border=2
    )

    qr.add_data(content)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")

    return base64.b64encode(buffer.getvalue()).decode()

def get_goods_name(product_no: str, cursor):
    """根据产品编码获取产品名称"""
    cursor.execute(
        "SELECT goods_name as CompanyPurchaseProductName FROM store_company_purchase_goods WHERE product_no=%s LIMIT 1",
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
                # 先列出所有字段，方便计数
                fields = [
                    "goods_num", "product_no", "goods_category_id", "goods_category", 
                    "goods_name", "goods_specification", "goods_unit", "goods_unit_id", 
                    "warehouse_name", "warehouse_id", "length_weight", "goods_location", 
                    "factory_name", "factory_id", "in_stock_time", "goods_status", 
                    "material_type", "is_print", "company_purchase_supplier_id",
                    "company_purchase_supplier_name", "company_purchase_finished_order_id",
                    "create_id", "remark", "standard","create_time"
                ]
                
                print(f"字段数量: {len(fields)}")  # 应该打印出25个字段
                
                # 构建SQL语句
                sql = f"""
                    INSERT INTO store_company_purchase_goods(
                        {', '.join(fields)}
                    ) VALUES ({', '.join(['%s'] * len(fields))})
                """
                
                # 准备参数
                params = [
                    generate_goods_num(item.productNo),  # goods_num
                    item.productNo,        # product_no
                    1981622202218487808,   # goods_category_id
                    "生产材料",             # goods_category
                    get_goods_name(item.productNo, cursor),  # goods_name
                    item.spec,             # goods_specification
                    "米",                   # goods_unit
                    1981622406481092608,   # goods_unit_id
                    shelf_name,             # warehouse_name
                    warehouse_id,           # warehouse_id
                    item.length,            # length_weight
                    shelf_name,             # goods_location
                    None,                   # factory_name
                    None,                   # factory_id
                    datetime.now(),         # in_stock_time
                    2,                      # goods_status
                    1,                      # material_type
                    1,                      # is_print
                    item.supplierId,        # company_purchase_supplier_id
                    item.supplierName,      # company_purchase_supplier_name
                    finished_order_id,      # company_purchase_finished_order_id
                    99999,                  # create_id
                    "加工单助手一键入库",           # remark
                    1,                      # standard
                    datetime.now()         # create_time
                ]
                
                print(f"参数数量: {len(params)}")  # 应该打印出24个参数
                print(f"SQL占位符数量: {sql.count('%s')}")  # 应该打印出24个占位符
                
                # 检查数量和类型
                if len(params) != len(fields):
                    print(f"数量不匹配！参数数量: {len(params)}, 字段数量: {len(fields)}")
                    
                # 检查参数类型
                for i, (field, param) in enumerate(zip(fields, params)):
                    print(f"字段 {i+1}: {field} = {param} (类型: {type(param)})")
                
                # 执行SQL
                cursor.execute(sql, tuple(params))
                
                # 获取刚插入的自增id
                goods_id = cursor.lastrowid
                inserted_ids.append(goods_id)
                goods_num = params[0]
                goods_name = params[4]

                goods_qr_content = f"goods://{goods_id}?productId={goods_num}"

                goods_cards.append({
                    "goodsId": goods_id,
                    "goodsName": goods_name,
                    "productNo": item.productNo,
                    "goodsNum": goods_num,
                    "spec": item.spec,
                    "supplierName": item.supplierName,
                    "qrCode": generate_qr_base64(goods_qr_content),
                    "length": item.length
                })
                if shelf_id not in shelf_cards_map:

                    shelf_qr = f"store://{shelf_id}?x=1&y=1"

                    shelf_cards_map[shelf_id] = {
                        "shelfId": shelf_id,
                        "shelfName": shelf_name,
                        "qrCode": generate_qr_base64(shelf_qr)
                    }

                # 插入货物货架关系
                cursor.execute("""
                    INSERT INTO store_goods_shelf(goods_id, shelf_id, location_x, location_y, update_time)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    goods_id,
                    shelf_id,
                    1,
                    1,
                    datetime.now()
                ))

            conn.commit()
            return {
                "success": True,
                "count": len(inserted_ids),
                "goodsCards": goods_cards,
                "shelfCards": list(shelf_cards_map.values())
            }

    except Exception as e:
        conn.rollback()
        print(f"错误详情: {str(e)}")
        import traceback
        traceback.print_exc()  # 打印完整的错误堆栈
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()