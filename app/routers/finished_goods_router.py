import os
import random
import redis
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional

from app.db import get_conn

router = APIRouter(prefix="/api")

# Redis 客户端（复用加工单助手同一实例）
redis_client = redis.Redis(host="192.168.200.203", port=6379, db=0, decode_responses=True)

# 36 进制字母表，与 WMS GoodsService 保持一致
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# 成品助手生成货物的标识，写入 store_goods.sys_remark，便于在货物流转生命周期中识别/清理
FINISHED_GOODS_MARK = "成品助手"

# 趣味彩蛋配置文件路径（项目根目录 funny.cfg，每行一个 IP 或主机名）
FUNNY_CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "funny.cfg")


def load_funny_targets() -> set:
    """读 funny.cfg，返回 IP/主机名集合（小写、去端口）"""
    targets = set()
    if not os.path.exists(FUNNY_CFG_PATH):
        return targets
    with open(FUNNY_CFG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if not line or line.startswith("#"):
                continue
            targets.add(line)
    return targets


def get_today_end_timestamp() -> int:
    """当天结束时间戳（秒），用于 Redis key 过期"""
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(tomorrow.timestamp())


def encode_warehouse(warehouse_id: int) -> str:
    """仓库 id 转 2 位 36 进制，复刻 WMS GoodsService.encodeWarehouse"""
    if warehouse_id < 0 or warehouse_id > 1295:
        raise HTTPException(status_code=400, detail="仓库ID超出可编码范围(0-1295)")
    return ALPHABET[(warehouse_id // 36) % 36] + ALPHABET[warehouse_id % 36]


def to36(num: int) -> str:
    """整数转 4 位 36 进制（左补 0），复刻 WMS GoodsService.to36"""
    if num <= 0:
        return "0000"
    s = ""
    while num > 0:
        s = ALPHABET[num % 36] + s
        num //= 36
    return s.zfill(4)


def from36(s: str) -> int:
    return int(s, 36)


def generate_goods_number(cursor, warehouse_id: int, specification_id: int, product_date: str) -> str:
    """
    生成 store_goods.number，完全复刻 WMS GoodsService.generateNumber 的编码：
    encodeWarehouse(2) + 日期每位+1(6) + 规格(4) + Redis流水号(4, 36进制)
    其中流水号用 Redis 递增，首次生成时对齐库里已有的最大流水号，避免 UNIQUE 冲突。
    """
    date_prefix = "".join(str((int(c) + 1) % 10) for c in product_date.replace("-", "")[2:])
    number_prefix = encode_warehouse(warehouse_id) + date_prefix
    redis_key = f"store_goods_num_seq:{number_prefix}"

    seq = redis_client.incr(redis_key)
    if seq == 1:
        # 首次生成该前缀，对齐 DB 里已有的最大流水号
        cursor.execute(
            "SELECT MAX(SUBSTR(number, 13, 4)) AS max_seq "
            "FROM store_goods "
            "WHERE number LIKE CONCAT(%s, '%%') "
            "  AND SUBSTR(number, 13, 4) REGEXP '^[0-9A-Z]{4}$'",
            (number_prefix,),
        )
        row = cursor.fetchone()
        if row and row.get("max_seq"):
            db_max = from36(row["max_seq"])
            if db_max > 0:
                redis_client.set(redis_key, db_max)
                seq = redis_client.incr(redis_key)
        redis_client.expireat(redis_key, get_today_end_timestamp())

    return f"{number_prefix}{specification_id:04d}{to36(seq)}"


# ---------------- 查询接口 ----------------

@router.get("/funny")
def funny(request: Request):
    """趣味彩蛋：匹配 funny.cfg 的 IP/主机名访问时，每次请求 1/3 概率触发"""
    client_ip = request.client.host if request.client else ""
    host = request.headers.get("host", "").split(":")[0].lower()
    targets = load_funny_targets()
    if client_ip not in targets and host not in targets:
        return {"triggered": False}
    return {"triggered": random.random() < 1 / 3}


@router.get("/finished-goods/specs")
def list_specs():
    """返回全部启用规格（前端本地过滤搜索）"""
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, color, english_name, type, material, series, length, mark_price "
                "FROM store_specification "
                "WHERE enabled = 1 "
                "ORDER BY id"
            )
            return cursor.fetchall()
    finally:
        conn.close()


@router.get("/finished-goods/brands")
def list_brands():
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM store_brand ORDER BY id")
            return cursor.fetchall()
    finally:
        conn.close()


@router.get("/finished-goods/factories")
def list_factories():
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM store_factory ORDER BY id")
            return cursor.fetchall()
    finally:
        conn.close()


@router.get("/finished-goods/warehouses")
def list_warehouses():
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM store_warehouse WHERE deleted = 0 ORDER BY id")
            return cursor.fetchall()
    finally:
        conn.close()


@router.get("/finished-goods/shelves")
def list_shelves(warehouseId: int):
    """某仓库的成品货架（排除原材料货架 shelf_type=2 与返厂货架）"""
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, number, width, height FROM store_shelf "
                "WHERE warehouse_id = %s AND return_factory = 0 AND shelf_type = 1 AND temp = 0 "
                "ORDER BY id",
                (warehouseId,),
            )
            return cursor.fetchall()
    finally:
        conn.close()


# ---------------- 生成 ----------------

class FinishedGoodsItem(BaseModel):
    specificationId: int
    brandId: int
    factoryId: int
    warehouseId: int
    shelfId: int
    locationX: int  # 层（X），对应 store_goods_shelf.location_x
    locationY: int  # 列/仓位（Y），对应 store_goods_shelf.location_y
    length: float
    count: int
    productDate: str  # YYYY-MM-DD


@router.post("/finished-goods/generate")
def generate(item: FinishedGoodsItem):
    if item.count <= 0:
        raise HTTPException(status_code=400, detail="数量必须大于 0")

    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            # 取规格的 length / mark_price（前端不传时兜底）
            cursor.execute(
                "SELECT length, mark_price FROM store_specification WHERE id = %s",
                (item.specificationId,),
            )
            spec = cursor.fetchone()
            if not spec:
                raise HTTPException(status_code=404, detail="规格不存在")

            length = item.length if item.length else spec["length"]
            mark_price = spec["mark_price"]
            std_length = spec["length"]  # 规格标准长度（米）

            # 查规格+工厂对应的工厂成本价（分，对应标准长度），并按实际长度换算
            cursor.execute(
                """
                SELECT fp.CostPrice
                FROM biz_purchase_specification_factory_price fp
                JOIN biz_purchase_specification ps ON fp.PurchaseSpecificationId = ps.PurchaseSpecificationId
                WHERE ps.SpecificationId = %s AND fp.FactoryId = %s AND fp.Deleted = 0
                LIMIT 1
                """,
                (item.specificationId, item.factoryId),
            )
            price_row = cursor.fetchone()
            if price_row and price_row["CostPrice"] is not None:
                cost_price_fen = price_row["CostPrice"]  # 分
                if std_length and std_length > 0:
                    # 长度非标准时按比例换算，四舍五入保留两位小数
                    cost = round(cost_price_fen * length / (std_length * 100), 2)
                else:
                    cost = round(cost_price_fen / 100, 2)
            else:
                cost = mark_price  # 无工厂价时兜底用建议零售价

            product_date = datetime.strptime(item.productDate, "%Y-%m-%d")

            inserted = 0
            for i in range(item.count):
                number = generate_goods_number(cursor, item.warehouseId, item.specificationId, item.productDate)

                cursor.execute(
                    """
                    INSERT INTO store_goods
                        (warehouse_id, specification_id, brand_id, factory_id, number, length,
                         mark_price, production_cost, cost_price, sell_price, pack, waste, montage, status,
                         product_date, stock_time, create_time, update_time, sys_remark)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 0, 0, 2, %s, %s, %s, %s, %s)
                    """,
                    (
                        item.warehouseId, item.specificationId, item.brandId, item.factoryId,
                        number, length, mark_price, cost, cost, mark_price,
                        product_date, datetime.now(), datetime.now(), datetime.now(),
                        FINISHED_GOODS_MARK,
                    ),
                )
                goods_id = cursor.lastrowid

                # 上架到指定货架的具体层(X)/列(Y)仓位
                cursor.execute(
                    "INSERT INTO store_goods_shelf (goods_id, shelf_id, location_x, location_y, update_time) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (goods_id, item.shelfId, item.locationX, item.locationY, datetime.now()),
                )
                inserted += 1

        conn.commit()
        return {"success": True, "count": inserted}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
