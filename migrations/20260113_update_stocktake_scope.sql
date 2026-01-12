-- 初回棚卸を期首棚卸（月次）扱いに修正
UPDATE stocktakes
SET scope = 'MONTHLY',
    taken_at = '2025-12-31 23:59:59',
    note = '期首棚卸（初回棚卸を転用）'
WHERE stocktake_id = 1;
