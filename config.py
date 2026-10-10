import os

DB_URL = os.getenv("DB_URL", "mysql+pymysql://etl_user:etl_pass@localhost:3306/sales_dw")
RAW_DIR = "data/raw"
PRODUCTS_API = "https://fakestoreapi.com/products"   # public REST API (20 products)
MAX_REJECT_RATIO = 0.20                               # fail the run if >20% of orders are bad
