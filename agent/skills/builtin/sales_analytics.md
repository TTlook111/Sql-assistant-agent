# skills.md

## Skill: sales_analytics
Description: 销售分析相关的数据库结构与业务规则，覆盖客户、订单与营收分析。
Tags: 销售, customers, orders, 营收

### Content
# 销售分析数据结构

## 表结构

### customers
- customer_id (PRIMARY KEY)
- name
- email
- signup_date
- status (active/inactive)
- customer_tier (bronze/silver/gold/platinum)

### orders
- order_id (PRIMARY KEY)
- customer_id (FOREIGN KEY -> customers)
- order_date
- status (pending/completed/cancelled/refunded)
- total_amount
- sales_region (north/south/east/west)

### order_items
- item_id (PRIMARY KEY)
- order_id (FOREIGN KEY -> orders)
- product_id
- quantity
- unit_price
- discount_percent

## 业务规则

**活跃客户**：status = 'active' 且 signup_date <= CURRENT_DATE - INTERVAL '90 days'

**营收计算**：仅统计 status = 'completed' 的订单，使用 orders.total_amount（已包含折扣影响）。

**客户生命周期价值（CLV）**：客户所有已完成订单金额之和。

**高价值订单**：total_amount > 1000 的订单。

## 示例查询

-- 查询最近一季度营收前 10 的客户
SELECT
    c.customer_id,
    c.name,
    c.customer_tier,
    SUM(o.total_amount) as total_revenue
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.status = 'completed'
  AND o.order_date >= CURRENT_DATE - INTERVAL '3 months'
GROUP BY c.customer_id, c.name, c.customer_tier
ORDER BY total_revenue DESC
LIMIT 10;
