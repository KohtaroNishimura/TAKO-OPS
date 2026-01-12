-- 初回棚卸を期首棚卸（月次）扱いに修正
UPDATE stocktakes
SET scope = 'MONTHLY',
    taken_at = '2026-01-12 23:59:59',
    note = '運用開始棚卸（初回棚卸）'
WHERE stocktake_id = 1;

-- STEP 5-1: いったん期首棚卸の行を消す
DELETE FROM stocktake_lines
WHERE stocktake_id = 1;

-- STEP 5-2: 期首棚卸の行を作り直す（FOODのみ）
WITH inv AS (
  SELECT item_id, SUM(qty_delta) AS qty
  FROM inventory_tx
  WHERE happened_at <= '2025-12-31 23:59:59'
  GROUP BY item_id
),
avg_cost AS (
  SELECT
    pl.item_id,
    SUM(
      CASE
        WHEN pl.line_amount IS NOT NULL THEN pl.line_amount
        WHEN pl.unit_price IS NOT NULL THEN pl.qty * pl.unit_price
        ELSE pl.qty * COALESCE(i.ref_unit_price,0)
      END
    ) / NULLIF(SUM(pl.qty), 0) AS avg_unit_cost
  FROM purchase_lines pl
  JOIN purchases p ON p.purchase_id = pl.purchase_id
  JOIN items i ON i.item_id = pl.item_id
  WHERE p.purchased_at <= '2025-12-31 23:59:59'
  GROUP BY pl.item_id
)
INSERT INTO stocktake_lines (stocktake_id, item_id, counted_qty, unit_cost, line_amount)
SELECT
  1,
  i.item_id,
  COALESCE(inv.qty, 0) AS counted_qty,
  COALESCE(avg_cost.avg_unit_cost, i.ref_unit_price, 0) AS unit_cost,
  COALESCE(inv.qty, 0) * COALESCE(avg_cost.avg_unit_cost, i.ref_unit_price, 0) AS line_amount
FROM items i
LEFT JOIN inv ON inv.item_id = i.item_id
LEFT JOIN avg_cost ON avg_cost.item_id = i.item_id
WHERE i.is_active = 1
  AND i.cost_group = 'FOOD';

-- STEP 6: 確認（期首在庫金額が取れているか）
SELECT ROUND(SUM(line_amount),0) AS opening_amount
FROM stocktake_lines sl
JOIN items i ON i.item_id = sl.item_id
WHERE sl.stocktake_id = 1
  AND i.cost_group = 'FOOD';
