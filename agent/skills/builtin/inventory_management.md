# skills.md

## Skill: inventory_management
Description: 库存管理相关的数据库结构与业务规则，覆盖商品、仓库与库存变化。
Tags: 库存, products, inventory, 仓库

### Content
# 库存管理数据结构

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
