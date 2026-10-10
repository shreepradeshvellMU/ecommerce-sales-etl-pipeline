USE sales_dw;

-- 1) Monthly revenue with month-over-month growth (CTE + window function)
WITH monthly AS (
  SELECT d.year, d.month, d.month_name, SUM(f.total_amount) AS revenue
  FROM fact_sales f JOIN dim_date d ON d.date_key = f.date_key
  GROUP BY d.year, d.month, d.month_name
)
SELECT year, month_name, ROUND(revenue,2) AS revenue,
       ROUND(100*(revenue - LAG(revenue) OVER (ORDER BY year, month))
             / LAG(revenue) OVER (ORDER BY year, month), 1) AS mom_growth_pct
FROM monthly ORDER BY year, month;

-- 2) Top 5 products per category (RANK window function)
WITH ranked AS (
  SELECT p.category, p.name, SUM(f.total_amount) AS revenue,
         RANK() OVER (PARTITION BY p.category ORDER BY SUM(f.total_amount) DESC) AS rnk
  FROM fact_sales f JOIN dim_product p ON p.product_key = f.product_key
  GROUP BY p.category, p.name
)
SELECT * FROM ranked WHERE rnk <= 5 ORDER BY category, rnk;

-- 3) Customer trend: lifetime value and running total
SELECT c.customer_id, c.name, d.full_date, f.total_amount,
       SUM(f.total_amount) OVER (PARTITION BY c.customer_key ORDER BY d.full_date
                                 ROWS UNBOUNDED PRECEDING) AS running_spend
FROM fact_sales f
JOIN dim_customer c ON c.customer_key = f.customer_key
JOIN dim_date d ON d.date_key = f.date_key
ORDER BY c.customer_id, d.full_date
LIMIT 15;
