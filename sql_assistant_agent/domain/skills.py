from typing import TypedDict


class Skill(TypedDict):
    """可按需逐步暴露给智能体的技能定义。"""

    name: str
    description: str
    tags: list[str]
    content: str


SKILLS: list[Skill] = [
    {
        "name": "sales_analytics",
        "description": "销售分析相关的数据库结构与业务规则，覆盖客户、订单与营收分析。",
        "tags": ["销售", "customers", "orders", "营收"],
        "content": 
"""
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
""",
    },
    {
        "name": "inventory_management",
        "description": "库存管理相关的数据库结构与业务规则，覆盖商品、仓库与库存变化。",
        "tags": ["库存", "products", "inventory", "仓库"],
        "content": """# 库存管理数据结构

## 表结构

### products
- product_id (PRIMARY KEY)
- product_name
- sku
- category
- unit_cost
- reorder_point (minimum stock level before reordering)
- discontinued (boolean)

### warehouses
- warehouse_id (PRIMARY KEY)
- warehouse_name
- location
- capacity

### inventory
- inventory_id (PRIMARY KEY)
- product_id (FOREIGN KEY -> products)
- warehouse_id (FOREIGN KEY -> warehouses)
- quantity_on_hand
- last_updated

### stock_movements
- movement_id (PRIMARY KEY)
- product_id (FOREIGN KEY -> products)
- warehouse_id (FOREIGN KEY -> warehouses)
- movement_type (inbound/outbound/transfer/adjustment)
- quantity (positive for inbound, negative for outbound)
- movement_date
- reference_number

## 业务规则

**可用库存**：inventory 表中 quantity_on_hand > 0 的记录。

**需要补货的商品**：跨仓汇总 quantity_on_hand 小于等于商品 reorder_point。

**只看在售商品**：默认排除 discontinued = true 的商品，除非明确要求分析停售商品。

**库存估值**：每个商品按 quantity_on_hand * unit_cost 计算。

## 示例查询

-- 查询跨仓汇总后低于补货点的商品
SELECT
    p.product_id,
    p.product_name,
    p.reorder_point,
    SUM(i.quantity_on_hand) as total_stock,
    p.unit_cost,
    (p.reorder_point - SUM(i.quantity_on_hand)) as units_to_reorder
FROM products p
JOIN inventory i ON p.product_id = i.product_id
WHERE p.discontinued = false
GROUP BY p.product_id, p.product_name, p.reorder_point, p.unit_cost
HAVING SUM(i.quantity_on_hand) <= p.reorder_point
ORDER BY units_to_reorder DESC;
""",
    },
]

