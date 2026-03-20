import json
from app.db import get_conn

def get_order_materials(finishedOrderId: int):
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                select a.CompanyPurchaseFinishedOrderDetailId as id , a.UserMaterialBom,b.CompanyPurchaseProductName
                from biz_company_purchase_finished_order_detail a
                inner join biz_company_purchase_product b on a.CompanyPurchaseProductId=b.CompanyPurchaseProductId
                where a.CompanyPurchaseFinishedOrderId=%s and a.Deleted=false
            """, (finishedOrderId,))
            order_details = cursor.fetchall()

            result = []

            for od in order_details:
                od_id = od['id']
                target_product=od['CompanyPurchaseProductName']
                bom_map = {}
                if od["UserMaterialBom"]:
                    arr = json.loads(od["UserMaterialBom"])
                    for item in arr:
                        bom_map[item["bomRecordId"]] = {
                            "spec": item.get("spec"),
                            "supplierId": item.get("supplierId"),
                            "supplierName": item.get("supplierName")
                        }

                materials = []
                for bomRecordId, value in bom_map.items():
                    cursor.execute("""
                        select a.EstimateProductCount,
                               a.CompanyPurchaseProductId,
                               b.CompanyPurchaseProductNo,
                               b.CompanyPurchaseProductName
                        from biz_company_purchase_finished_order_materials a
                        inner join biz_company_purchase_product b
                        on a.CompanyPurchaseProductId=b.CompanyPurchaseProductId
                        where a.CompanyPurchaseBomRecordId=%s and a.Deleted=false and a.CompanyPurchaseFinishedOrderDetailId=%s
                    """, (bomRecordId, od_id))
                    row = cursor.fetchone()
                    if row:
                        materials.append({
                            "bomRecordId": bomRecordId,
                            "productId": row["CompanyPurchaseProductId"],
                            "productNo": row["CompanyPurchaseProductNo"],
                            "productName": row["CompanyPurchaseProductName"],
                            "estimateCount": row["EstimateProductCount"],  # 所需长度
                            "spec": value["spec"],
                            "supplierId": value["supplierId"],
                            "supplierName": value["supplierName"],
                        })

                result.append({
                    "orderDetailId": str(od_id),
                    "targetProduct":target_product,
                    "materials": materials
                })

            return result

    finally:
        conn.close()