"""Creates messy sample CSVs. Run once; run with --append to simulate a new day of data."""
import argparse, os, random
from datetime import datetime, timedelta
import pandas as pd

random.seed(42)
RAW = "data/raw"
CITIES = ["chennai", "bangalore", "mumbai", "delhi", "salem"]
CATS = ["electronics", "jewelery", "men's clothing", "women's clothing"]
FMT = "%Y-%m-%d %H:%M:%S"


def initial():
    os.makedirs(RAW, exist_ok=True)
    customers = pd.DataFrame({
        "customer_id": range(1, 51),
        "name": [f"  customer {i} " for i in range(1, 51)],
        "email": [f"Customer{i}@Example.com " for i in range(1, 51)],
        "city": [random.choice(CITIES) for _ in range(50)],
        "updated_at": "2025-01-01 00:00:00",
    })
    customers.loc[[3, 7], "city"] = None

    products = pd.DataFrame({
        "product_id": range(1, 21),
        "name": [f"Product {i}" for i in range(1, 21)],
        "category": [random.choice(CATS) for _ in range(20)],
        "price": [round(random.uniform(5, 300), 2) for _ in range(20)],
        "updated_at": "2025-01-01 00:00:00",
    })

    rows = []
    for oid in range(1, 501):
        d = datetime(2025, 1, 1) + timedelta(days=random.randint(0, 180))
        pid = random.randint(1, 20)
        rows.append({
            "order_id": oid, "customer_id": random.randint(1, 50), "product_id": pid,
            "quantity": random.randint(1, 5), "unit_price": products.loc[pid - 1, "price"],
            "order_date": d.strftime(random.choice(["%Y-%m-%d", "%Y/%m/%d"])),
            "updated_at": d.strftime(FMT),
        })
    orders = pd.DataFrame(rows)
    orders.loc[[10, 20, 30, 40, 50], "unit_price"] = None      # nulls to fill
    orders.loc[[60, 61, 62], "quantity"] = None                # nulls to drop
    orders.loc[[70, 71], "quantity"] = -1                      # bad values
    orders.loc[[80, 81], "customer_id"] = None                 # nulls to drop
    orders = pd.concat([orders, orders.iloc[:10]], ignore_index=True)  # 10 duplicates

    customers.to_csv(f"{RAW}/customers.csv", index=False)
    products.to_csv(f"{RAW}/products.csv", index=False)
    orders.to_csv(f"{RAW}/orders.csv", index=False)
    print(f"customers={len(customers)} products={len(products)} orders={len(orders)}")


def append():
    now = datetime.now().strftime(FMT)
    orders = pd.read_csv(f"{RAW}/orders.csv")
    customers = pd.read_csv(f"{RAW}/customers.csv")
    start = int(orders["order_id"].max()) + 1
    new = [{"order_id": start + i, "customer_id": random.randint(1, 50),
            "product_id": random.randint(1, 20), "quantity": random.randint(1, 3),
            "unit_price": 99.0, "order_date": f"2025-07-{random.randint(1, 28):02d}",
            "updated_at": now} for i in range(20)]
    orders = pd.concat([orders, pd.DataFrame(new)], ignore_index=True)
    mask = customers["customer_id"].isin([1, 2, 3])            # 3 customers changed city
    customers.loc[mask, "city"] = "pune"
    customers.loc[mask, "updated_at"] = now
    customers.to_csv(f"{RAW}/customers.csv", index=False)
    orders.to_csv(f"{RAW}/orders.csv", index=False)
    print("appended 20 new orders and updated 3 customers")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--append", action="store_true")
    append() if ap.parse_args().append else initial()
