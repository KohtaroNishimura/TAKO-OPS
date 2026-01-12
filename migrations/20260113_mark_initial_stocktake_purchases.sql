-- 初回棚卸入庫を原価率集計から除外するためのタグ付け
UPDATE purchases
SET note = '初回棚卸入庫'
WHERE purchase_id IN (1,4,7,8,9,10,11,12,13,14);
