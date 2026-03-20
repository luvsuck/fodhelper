import json
from app.db import get_conn

def get_spec(productNo: str):

    conn = get_conn()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                select Attribute
                from biz_company_purchase_product
                where CompanyPurchaseProductNo=%s
                """,
                (productNo,),
            )

            row = cursor.fetchone()

            if not row or not row["Attribute"]:
                return []

            attr = json.loads(row["Attribute"])

            spec_list = attr.get("specList", [])

            result = []
            seen = set()

            for s in spec_list:
                if s not in seen:
                    seen.add(s)
                    result.append(s)

            return result

    finally:
        conn.close()


def get_supplier(productNo: str):

    conn = get_conn()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                select c.CompanyPurchaseSupplierId,c.SupplierName
                from biz_company_purchase_product a
                inner join biz_company_purchase_price b
                on a.CompanyPurchaseProductId=b.CompanyPurchaseProductId
                inner join biz_company_purchase_supplier c
                on c.CompanyPurchaseSupplierId=b.CompanyPurchaseSupplierId
                where a.CompanyPurchaseProductNo=%s
                """,
                (productNo,),
            )

            rows = cursor.fetchall()

            m = {}

            for r in rows:
                r["CompanyPurchaseSupplierId"] = str(r["CompanyPurchaseSupplierId"])
                m[r["CompanyPurchaseSupplierId"]] = r

            return list(m.values())

    finally:
        conn.close()
