"""Daily ETL: CSV + REST API -> Pandas cleaning -> MySQL star schema (incremental upserts)."""
import logging, os, sys
from datetime import datetime

import pandas as pd
import requests

import config

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("logs/etl.log"), logging.StreamHandler()],
)
log = logging.getLogger("etl")


# ---------------------------------------------------------------- EXTRACT
def extract():
    customers = pd.read_csv(f"{config.RAW_DIR}/customers.csv")
    orders = pd.read_csv(f"{config.RAW_DIR}/orders.csv")
    try:
        r = requests.get(config.PRODUCTS_API, timeout=15)
        r.raise_for_status()
        products = (pd.DataFrame(r.json())
                    .rename(columns={"id": "product_id", "title": "name"})
                    [["product_id", "name", "category", "price"]])
        products["updated_at"] = datetime.now()
        log.info("Products pulled from REST API: %d rows", len(products))
    except Exception as exc:                       # network down -> use local file
        log.warning("API failed (%s); falling back to products.csv", exc)
        products = pd.read_csv(f"{config.RAW_DIR}/products.csv")
    log.info("Extracted customers=%d products=%d orders=%d",
             len(customers), len(products), len(orders))
    return customers, products, orders


# -------------------------------------------------------------- TRANSFORM
def transform(customers, products, orders):
    # customers
    c = customers.dropna(subset=["customer_id"]).drop_duplicates("customer_id", keep="last").copy()
    c["name"] = c["name"].fillna("Unknown").str.strip().str.title()
    c["email"] = c["email"].str.strip().str.lower()
    c["city"] = c["city"].fillna("Unknown").str.strip().str.title()
    c["updated_at"] = pd.to_datetime(c["updated_at"], errors="coerce").fillna(pd.Timestamp("1970-01-01"))
    c["customer_id"] = c["customer_id"].astype(int)

    # products
    p = products.dropna(subset=["product_id"]).drop_duplicates("product_id", keep="last").copy()
    p["name"] = p["name"].str.strip().str.title()
    p["category"] = p["category"].str.strip().str.title()
    p["updated_at"] = pd.to_datetime(p["updated_at"], errors="coerce").fillna(pd.Timestamp("1970-01-01"))
    p["product_id"] = p["product_id"].astype(int)

    # orders
    before = len(orders)
    o = orders.drop_duplicates("order_id", keep="last").copy()
    dupes = before - len(o)
    o = o.dropna(subset=["order_id", "customer_id", "product_id", "quantity", "order_date"])
    o["order_date"] = pd.to_datetime(o["order_date"], errors="coerce", format="mixed")
    o["updated_at"] = pd.to_datetime(o["updated_at"], errors="coerce").fillna(o["order_date"])
    price_map = p.set_index("product_id")["price"]
    o["unit_price"] = o["unit_price"].fillna(o["product_id"].map(price_map))   # fill null price

    # data-quality checks
    bad = (o["order_date"].isna() | (o["quantity"] <= 0) | (o["unit_price"].isna())
           | (o["unit_price"] <= 0))
    rejected = int(bad.sum()) + (before - dupes - len(o))
    o = o[~bad].copy()
    ratio = rejected / max(before, 1)
    log.info("DQ: input=%d duplicates=%d rejected=%d clean=%d", before, dupes, rejected, len(o))
    if ratio > config.MAX_REJECT_RATIO:
        raise ValueError(f"Data-quality gate failed: {ratio:.0%} of orders rejected")

    for col in ["order_id", "customer_id", "product_id", "quantity"]:
        o[col] = o[col].astype(int)
    o["total_amount"] = (o["quantity"] * o["unit_price"]).round(2)
    o["date_key"] = o["order_date"].dt.strftime("%Y%m%d").astype(int)
    o = o[["order_id", "customer_id", "product_id", "date_key", "order_date",
           "quantity", "unit_price", "total_amount", "updated_at"]]
    return c, p, o


# ------------------------------------------------------------------- LOAD
def get_watermark(conn, table):
    from sqlalchemy import text
    row = conn.execute(text("SELECT last_updated FROM etl_watermark WHERE table_name=:t"),
                       {"t": table}).fetchone()
    return pd.Timestamp(row[0]) if row else pd.Timestamp("1970-01-01")


def set_watermark(conn, table, ts):
    from sqlalchemy import text
    conn.execute(text("""INSERT INTO etl_watermark (table_name, last_updated) VALUES (:t, :ts)
                         ON DUPLICATE KEY UPDATE last_updated = :ts"""),
                 {"t": table, "ts": ts.to_pydatetime()})


UPSERT_CUSTOMER = """
INSERT INTO dim_customer (customer_id, name, email, city, updated_at)
SELECT customer_id, name, email, city, updated_at FROM stg_customers
ON DUPLICATE KEY UPDATE name=VALUES(name), email=VALUES(email),
                        city=VALUES(city), updated_at=VALUES(updated_at)"""

UPSERT_PRODUCT = """
INSERT INTO dim_product (product_id, name, category, price, updated_at)
SELECT product_id, name, category, price, updated_at FROM stg_products
ON DUPLICATE KEY UPDATE name=VALUES(name), category=VALUES(category),
                        price=VALUES(price), updated_at=VALUES(updated_at)"""

UPSERT_FACT = """
INSERT INTO fact_sales (order_id, customer_key, product_key, date_key,
                        quantity, unit_price, total_amount, updated_at)
SELECT s.order_id, c.customer_key, p.product_key, s.date_key,
       s.quantity, s.unit_price, s.total_amount, s.updated_at
FROM stg_orders s
JOIN dim_customer c ON c.customer_id = s.customer_id
JOIN dim_product  p ON p.product_id  = s.product_id
ON DUPLICATE KEY UPDATE customer_key=VALUES(customer_key), product_key=VALUES(product_key),
    date_key=VALUES(date_key), quantity=VALUES(quantity), unit_price=VALUES(unit_price),
    total_amount=VALUES(total_amount), updated_at=VALUES(updated_at)"""


def load(engine, c, p, o):
    from sqlalchemy import text
    with engine.begin() as conn:
        batches = {}
        for name, df in [("customers", c), ("products", p), ("orders", o)]:
            wm = get_watermark(conn, name)
            new = df[df["updated_at"] > wm]
            log.info("%s: watermark=%s -> %d new/changed of %d", name, wm, len(new), len(df))
            batches[name] = new

        # dimensions first, so fact rows can find their keys
        if len(batches["customers"]):
            batches["customers"].to_sql("stg_customers", conn, if_exists="replace", index=False)
            conn.execute(text(UPSERT_CUSTOMER))
        if len(batches["products"]):
            batches["products"].to_sql("stg_products", conn, if_exists="replace", index=False)
            conn.execute(text(UPSERT_PRODUCT))

        if len(batches["orders"]):
            dates = batches["orders"]["order_date"].dt.normalize().drop_duplicates()
            conn.execute(text("""INSERT IGNORE INTO dim_date
                (date_key, full_date, year, quarter, month, month_name, day_of_week)
                VALUES (:k, :d, :y, :q, :m, :mn, :dw)"""),
                [{"k": int(d.strftime("%Y%m%d")), "d": d.date(), "y": d.year, "q": d.quarter,
                  "m": d.month, "mn": d.strftime("%B"), "dw": d.strftime("%A")} for d in dates])
            batches["orders"].drop(columns=["order_date"]).to_sql(
                "stg_orders", conn, if_exists="replace", index=False)
            res = conn.execute(text(UPSERT_FACT))
            log.info("fact_sales upserted rows affected=%s", res.rowcount)

        for name, new in batches.items():
            if len(new):
                set_watermark(conn, name, new["updated_at"].max())


def main():
    from sqlalchemy import create_engine
    try:
        c, p, o = transform(*extract())
        load(create_engine(config.DB_URL), c, p, o)
        log.info("ETL finished OK")
    except Exception:
        log.exception("ETL failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
