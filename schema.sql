CREATE DATABASE IF NOT EXISTS sales_dw;
CREATE USER IF NOT EXISTS 'etl_user'@'%' IDENTIFIED BY 'etl_pass';
GRANT ALL ON sales_dw.* TO 'etl_user'@'%';
USE sales_dw;

CREATE TABLE IF NOT EXISTS dim_customer (
  customer_key INT AUTO_INCREMENT PRIMARY KEY,
  customer_id  INT NOT NULL,
  name VARCHAR(100), email VARCHAR(150), city VARCHAR(60),
  updated_at DATETIME,
  UNIQUE KEY uq_customer_id (customer_id)
);

CREATE TABLE IF NOT EXISTS dim_product (
  product_key INT AUTO_INCREMENT PRIMARY KEY,
  product_id  INT NOT NULL,
  name VARCHAR(200), category VARCHAR(80), price DECIMAL(10,2),
  updated_at DATETIME,
  UNIQUE KEY uq_product_id (product_id)
);

CREATE TABLE IF NOT EXISTS dim_date (
  date_key INT PRIMARY KEY,              -- yyyymmdd
  full_date DATE NOT NULL,
  year SMALLINT, quarter TINYINT, month TINYINT,
  month_name VARCHAR(12), day_of_week VARCHAR(12),
  UNIQUE KEY uq_full_date (full_date)
);

CREATE TABLE IF NOT EXISTS fact_sales (
  sales_key BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL,
  customer_key INT NOT NULL,
  product_key  INT NOT NULL,
  date_key     INT NOT NULL,
  quantity INT, unit_price DECIMAL(10,2), total_amount DECIMAL(12,2),
  updated_at DATETIME,
  UNIQUE KEY uq_order_id (order_id),
  KEY idx_fact_customer (customer_key),
  KEY idx_fact_product (product_key),
  KEY idx_fact_date (date_key),
  CONSTRAINT fk_fact_customer FOREIGN KEY (customer_key) REFERENCES dim_customer(customer_key),
  CONSTRAINT fk_fact_product  FOREIGN KEY (product_key)  REFERENCES dim_product(product_key),
  CONSTRAINT fk_fact_date     FOREIGN KEY (date_key)     REFERENCES dim_date(date_key)
);

CREATE TABLE IF NOT EXISTS etl_watermark (
  table_name VARCHAR(50) PRIMARY KEY,
  last_updated DATETIME NOT NULL
);
