PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT    NOT NULL,
  phone       TEXT,
  note        TEXT,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO suppliers VALUES(1,'Aプライス',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(2,'かねひで大宮',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(3,'みつわ',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(4,'イオン系列',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(5,'オリジナル',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(6,'コッコハウス玉城',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(7,'サンエー',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(8,'ビッグ１',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(9,'ファーマーズ',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(10,'上間商事',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(11,'各店',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(12,'山川商店',NULL,NULL,'2026-01-10 12:27:51');
INSERT INTO suppliers VALUES(13,'粉もん専科',NULL,NULL,'2026-01-10 12:27:51');
CREATE TABLE IF NOT EXISTS items (
  item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id     INTEGER,
  name            TEXT    NOT NULL,
  category        TEXT,
  unit_base       TEXT    NOT NULL,                 -- 例: g / ml / pcs
  reorder_point   REAL    NOT NULL DEFAULT 0,
  ref_unit_price  REAL    NOT NULL DEFAULT 0,       -- 参考価格（目安表示用）
  is_active       INTEGER NOT NULL DEFAULT 1,       -- 0/1（SQLiteにはboolがない）
  created_at      TEXT    NOT NULL DEFAULT (datetime('now')), is_fixed INTEGER NOT NULL DEFAULT 0, cost_group TEXT NOT NULL DEFAULT 'SUPPLIES'
CHECK(cost_group IN ('FOOD','SUPPLIES')), note TEXT,
  FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
    ON UPDATE CASCADE
    ON DELETE SET NULL
);
INSERT INTO items VALUES(1,13,'たこ',NULL,'kg',6.4,2834,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(2,5,'粉袋（450g）',NULL,'pcs',20,258,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(3,1,'カツオ500',NULL,'pcs',2,1674,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(4,1,'揚げ玉',NULL,'pcs',3.3,646,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(5,1,'タコ焼きソース（おたふく）',NULL,'pcs',2.5,819,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(6,1,'マヨネーズAベストセフェ',NULL,'pcs',2.5,689,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(7,3,'マヨネーズBホテルマヨ',NULL,'pcs',0,538,0,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(8,3,'4個　おりぎりパック',NULL,'pcs',1,586,1,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(9,1,'８個フードパック特中浅',NULL,'pcs',2,578,1,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(10,1,'10個フードパック大深',NULL,'pcs',1,583,1,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(11,4,'サラダ油',NULL,'pcs',3,257,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(12,3,'青のり',NULL,'pcs',1,1210,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(13,1,'紅生姜（刻み）',NULL,'pcs',1,613,1,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(14,3,'ふくろ220mm',NULL,'pcs',2,231,1,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(15,3,'箸',NULL,'pcs',4,153,1,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(16,8,'ガスボンベ(3本セット)',NULL,'pcs',4,405,1,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(17,10,'たこせん',NULL,'pcs',1,498,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(18,11,'卵 M',NULL,'pcs',8,200,1,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(19,6,'卵',NULL,'pcs',0,0,0,'2026-01-10 12:27:51',0,'FOOD',NULL);
INSERT INTO items VALUES(20,11,'山芋',NULL,'g',3400,0.98,1,'2026-01-10 12:27:51',1,'FOOD',replace(replace('第1候補かねひで大宮（大宮市場以外の店舗推奨しない）\r\n第2候補ファーマーズ\r\n第3候補サンエー','\r',char(13)),'\n',char(10)));
INSERT INTO items VALUES(23,7,'キッコーマン白だし',NULL,'pcs',1.4,473,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
INSERT INTO items VALUES(24,7,'SBゆず七味',NULL,'pcs',1,279,1,'2026-01-10 12:27:51',1,'SUPPLIES',NULL);
INSERT INTO items VALUES(25,1,'ガーリックあらびき',NULL,'pcs',1,1534,1,'2026-01-10 12:27:51',1,'SUPPLIES',NULL);
INSERT INTO items VALUES(26,1,'からしマヨネーズ',NULL,'pcs',1,991,1,'2026-01-10 12:27:51',1,'SUPPLIES',NULL);
INSERT INTO items VALUES(27,8,'キッチンペーパー',NULL,'pcs',2,205,1,'2026-01-10 12:27:51',0,'SUPPLIES',NULL);
INSERT INTO items VALUES(28,3,'輪ゴム(赤など)',NULL,'pcs',1,781,1,'2026-01-10 12:27:51',0,'SUPPLIES',NULL);
INSERT INTO items VALUES(29,1,'糸切り唐辛子',NULL,'pcs',1,724,1,'2026-01-10 12:27:51',0,'SUPPLIES',NULL);
INSERT INTO items VALUES(30,1,'サランラップ45cm',NULL,'pcs',1,460,1,'2026-01-10 12:27:51',0,'SUPPLIES',NULL);
INSERT INTO items VALUES(31,3,'ビニール手袋青LL',NULL,'pcs',1,253,1,'2026-01-10 12:27:51',0,'SUPPLIES',NULL);
INSERT INTO items VALUES(32,3,'アルコール',NULL,'pcs',1,2538,1,'2026-01-10 12:27:51',0,'SUPPLIES',NULL);
INSERT INTO items VALUES(33,3,'バーガーペーパー',NULL,'pcs',1,330,1,'2026-01-10 12:27:51',0,'SUPPLIES',NULL);
INSERT INTO items VALUES(34,12,'魔法のしょうゆ',NULL,'pcs',1,820,1,'2026-01-10 12:27:51',1,'FOOD',NULL);
CREATE TABLE IF NOT EXISTS batch_config (
  batch_config_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name              TEXT    NOT NULL,
  pieces_per_batch  INTEGER NOT NULL DEFAULT 80,
  is_active         INTEGER NOT NULL DEFAULT 1,
  created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO batch_config VALUES(1,'標準（80個/バッチ）',80,1,'2026-01-11 10:44:51');
CREATE TABLE IF NOT EXISTS recipe_batch (
  recipe_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_config_id  INTEGER NOT NULL,
  item_id          INTEGER NOT NULL,
  qty_per_batch    REAL    NOT NULL DEFAULT 0,
  auto_consume     INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (batch_config_id) REFERENCES batch_config(batch_config_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  FOREIGN KEY (item_id) REFERENCES items(item_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  UNIQUE (batch_config_id, item_id)
);
INSERT INTO recipe_batch VALUES(1,1,1,0.32,1);
INSERT INTO recipe_batch VALUES(2,1,2,1,1);
INSERT INTO recipe_batch VALUES(3,1,3,0.1,1);
INSERT INTO recipe_batch VALUES(4,1,4,0.161,1);
INSERT INTO recipe_batch VALUES(5,1,5,0.125,1);
INSERT INTO recipe_batch VALUES(6,1,6,0.125,1);
INSERT INTO recipe_batch VALUES(7,1,11,0.142,1);
INSERT INTO recipe_batch VALUES(8,1,18,0.2,1);
INSERT INTO recipe_batch VALUES(10,1,23,0.014,1);
INSERT INTO recipe_batch VALUES(11,1,20,170,1);
CREATE TABLE IF NOT EXISTS daily_reports (
  daily_report_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  report_date          TEXT    NOT NULL,            -- YYYY-MM-DD
  sold_batches         REAL    NOT NULL DEFAULT 0,  -- 0.1刻みOK
  waste_pieces         INTEGER NOT NULL DEFAULT 0,
  production_minutes   INTEGER NOT NULL DEFAULT 0,
  sales_amount         REAL    NOT NULL DEFAULT 0,
  impression           TEXT,
  created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (report_date)
);
INSERT INTO daily_reports VALUES(1,'2026-01-11',0,0,0,0,'日報テスト','2026-01-11 11:27:02');
CREATE TABLE IF NOT EXISTS purchases (
  purchase_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id   INTEGER,
  purchased_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  note          TEXT,
  total_amount  REAL,
  FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
    ON UPDATE CASCADE
    ON DELETE SET NULL
);
INSERT INTO purchases VALUES(1,10,'2026-01-10 09:00:00',NULL,996);
INSERT INTO purchases VALUES(4,8,'2026-01-11 09:00:00','買い物リストから作成',4900);
INSERT INTO purchases VALUES(7,7,'2026-01-12 09:00:00','買い物リストから作成',5666.219999999999);
INSERT INTO purchases VALUES(8,3,'2026-01-12 09:00:00','買い物リストから作成',7231);
INSERT INTO purchases VALUES(9,4,'2026-01-12 06:11:53','買い物リストから作成',771);
INSERT INTO purchases VALUES(10,7,'2026-01-12 07:02:21','買い物リストから作成',946);
INSERT INTO purchases VALUES(11,1,'2026-01-12 07:04:00','買い物リストから作成',13831);
INSERT INTO purchases VALUES(12,3,'2026-01-12 07:27:49','買い物リストから作成',962);
INSERT INTO purchases VALUES(13,13,'2026-01-12 09:00:00',NULL,28340);
INSERT INTO purchases VALUES(14,5,'2026-01-12 07:51:53',NULL,6450);
CREATE TABLE IF NOT EXISTS purchase_lines (
  purchase_line_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_id       INTEGER NOT NULL,
  item_id           INTEGER NOT NULL,
  qty               REAL    NOT NULL,
  unit_price        REAL,
  line_amount       REAL,                           -- 任意：qty*unit_price を保存したい場合
  FOREIGN KEY (purchase_id) REFERENCES purchases(purchase_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  FOREIGN KEY (item_id) REFERENCES items(item_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
);
INSERT INTO purchase_lines VALUES(9,1,17,2,498,996);
INSERT INTO purchase_lines VALUES(12,4,16,4,405,1620);
INSERT INTO purchase_lines VALUES(13,4,27,16,205,3280);
INSERT INTO purchase_lines VALUES(28,8,8,1,586,586);
INSERT INTO purchase_lines VALUES(29,8,14,2,231,462);
INSERT INTO purchase_lines VALUES(30,8,32,1,2538,2538);
INSERT INTO purchase_lines VALUES(31,8,33,1,330,330);
INSERT INTO purchase_lines VALUES(32,8,31,1,253,253);
INSERT INTO purchase_lines VALUES(33,8,15,4,153,612);
INSERT INTO purchase_lines VALUES(34,8,28,1,781,781);
INSERT INTO purchase_lines VALUES(35,8,12,1,1210,1210);
INSERT INTO purchase_lines VALUES(36,8,13,1,459,459);
INSERT INTO purchase_lines VALUES(39,7,18,8,246,1968);
INSERT INTO purchase_lines VALUES(40,7,20,3489,0.98,3419.22);
INSERT INTO purchase_lines VALUES(41,7,24,1,279,279);
INSERT INTO purchase_lines VALUES(42,9,11,3,257,771);
INSERT INTO purchase_lines VALUES(43,10,23,2,473,946);
INSERT INTO purchase_lines VALUES(44,11,10,1,583,583);
INSERT INTO purchase_lines VALUES(45,11,26,1,991,991);
INSERT INTO purchase_lines VALUES(46,11,3,2,1814,3628);
INSERT INTO purchase_lines VALUES(47,11,25,1,1534,1534);
INSERT INTO purchase_lines VALUES(48,11,30,1,460,460);
INSERT INTO purchase_lines VALUES(49,11,5,3,896,2688);
INSERT INTO purchase_lines VALUES(50,11,6,3,689,2067);
INSERT INTO purchase_lines VALUES(51,11,29,1,724,724);
INSERT INTO purchase_lines VALUES(52,11,9,2,578,1156);
INSERT INTO purchase_lines VALUES(53,12,4,1,962,962);
INSERT INTO purchase_lines VALUES(55,13,1,10,2834,28340);
INSERT INTO purchase_lines VALUES(56,14,2,25,258,6450);
CREATE TABLE IF NOT EXISTS stocktakes (
  stocktake_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  taken_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  scope         TEXT    NOT NULL CHECK (scope IN ('WEEKLY','MONTHLY')),
  location      TEXT    NOT NULL CHECK (location IN ('STORE','Warehouse','WAREHOUSE')),
  note          TEXT
);
INSERT INTO stocktakes VALUES(1,'2026-01-12 09:00:00','MONTHLY','WAREHOUSE','');
CREATE TABLE IF NOT EXISTS stocktake_lines (
  stocktake_line_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  stocktake_id       INTEGER NOT NULL,
  item_id            INTEGER NOT NULL,
  counted_qty        REAL    NOT NULL DEFAULT 0,
  FOREIGN KEY (stocktake_id) REFERENCES stocktakes(stocktake_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  FOREIGN KEY (item_id) REFERENCES items(item_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  UNIQUE (stocktake_id, item_id)
);
INSERT INTO stocktake_lines VALUES(1,1,10,1);
INSERT INTO stocktake_lines VALUES(2,1,8,1);
INSERT INTO stocktake_lines VALUES(3,1,1,10);
INSERT INTO stocktake_lines VALUES(4,1,17,2);
INSERT INTO stocktake_lines VALUES(5,1,14,2);
INSERT INTO stocktake_lines VALUES(6,1,3,2);
INSERT INTO stocktake_lines VALUES(7,1,16,4);
INSERT INTO stocktake_lines VALUES(8,1,23,2);
INSERT INTO stocktake_lines VALUES(9,1,11,3);
INSERT INTO stocktake_lines VALUES(10,1,5,3);
INSERT INTO stocktake_lines VALUES(11,1,6,3);
INSERT INTO stocktake_lines VALUES(12,1,18,8);
INSERT INTO stocktake_lines VALUES(13,1,20,3489);
INSERT INTO stocktake_lines VALUES(14,1,4,1);
INSERT INTO stocktake_lines VALUES(15,1,15,4);
INSERT INTO stocktake_lines VALUES(16,1,2,25);
INSERT INTO stocktake_lines VALUES(17,1,13,1);
INSERT INTO stocktake_lines VALUES(18,1,12,1);
INSERT INTO stocktake_lines VALUES(19,1,34,0);
INSERT INTO stocktake_lines VALUES(20,1,9,2);
CREATE TABLE IF NOT EXISTS inventory_tx (
  tx_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  happened_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  item_id      INTEGER NOT NULL,
  qty_delta    REAL    NOT NULL,  -- +入庫 / -出庫
  tx_type      TEXT    NOT NULL CHECK (tx_type IN ('PURCHASE','CONSUME','WASTE','ADJUST','STOCKTAKE')),
  location     TEXT    NOT NULL CHECK (location IN ('STORE','Warehouse','WAREHOUSE')),
  ref_type     TEXT    CHECK (ref_type IN ('DAILY_REPORT','PURCHASE','STOCKTAKE')),
  ref_id       INTEGER,
  note         TEXT,
  FOREIGN KEY (item_id) REFERENCES items(item_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
);
INSERT INTO inventory_tx VALUES(9,'2026-01-10 09:00:00',17,2,'PURCHASE','WAREHOUSE','PURCHASE',1,NULL);
INSERT INTO inventory_tx VALUES(12,'2026-01-11 09:00:00',16,4,'PURCHASE','WAREHOUSE','PURCHASE',4,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(13,'2026-01-11 09:00:00',27,16,'PURCHASE','WAREHOUSE','PURCHASE',4,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(28,'2026-01-12 09:00:00',8,1,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(29,'2026-01-12 09:00:00',14,2,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(30,'2026-01-12 09:00:00',32,1,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(31,'2026-01-12 09:00:00',33,1,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(32,'2026-01-12 09:00:00',31,1,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(33,'2026-01-12 09:00:00',15,4,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(34,'2026-01-12 09:00:00',28,1,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(35,'2026-01-12 09:00:00',12,1,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(36,'2026-01-12 09:00:00',13,1,'PURCHASE','WAREHOUSE','PURCHASE',8,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(39,'2026-01-12 09:00:00',18,8,'PURCHASE','WAREHOUSE','PURCHASE',7,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(40,'2026-01-12 09:00:00',20,3489,'PURCHASE','WAREHOUSE','PURCHASE',7,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(41,'2026-01-12 09:00:00',24,1,'PURCHASE','WAREHOUSE','PURCHASE',7,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(42,'2026-01-12 06:11:54',11,3,'PURCHASE','WAREHOUSE','PURCHASE',9,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(43,'2026-01-12 07:02:22',23,2,'PURCHASE','WAREHOUSE','PURCHASE',10,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(44,'2026-01-12 07:04:01',10,1,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(45,'2026-01-12 07:04:02',26,1,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(46,'2026-01-12 07:04:02',3,2,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(47,'2026-01-12 07:04:03',25,1,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(48,'2026-01-12 07:04:04',30,1,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(49,'2026-01-12 07:04:05',5,3,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(50,'2026-01-12 07:04:06',6,3,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(51,'2026-01-12 07:04:06',29,1,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(52,'2026-01-12 07:04:07',9,2,'PURCHASE','WAREHOUSE','PURCHASE',11,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(53,'2026-01-12 07:27:50',4,1,'PURCHASE','WAREHOUSE','PURCHASE',12,'買い物リストから作成');
INSERT INTO inventory_tx VALUES(55,'2026-01-12 09:00:00',1,10,'PURCHASE','WAREHOUSE','PURCHASE',13,NULL);
INSERT INTO inventory_tx VALUES(56,'2026-01-12 07:51:54',2,25,'PURCHASE','WAREHOUSE','PURCHASE',14,NULL);
CREATE TABLE IF NOT EXISTS transfers (
  transfer_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  moved_at       TEXT NOT NULL DEFAULT (datetime('now')),
  from_location  TEXT NOT NULL CHECK(from_location IN ('STORE','WAREHOUSE')),
  to_location    TEXT NOT NULL CHECK(to_location IN ('STORE','WAREHOUSE')),
  note           TEXT
);
CREATE TABLE IF NOT EXISTS transfer_lines (
  transfer_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
  transfer_id      INTEGER NOT NULL,
  item_id          INTEGER NOT NULL,
  qty              REAL    NOT NULL,
  FOREIGN KEY (transfer_id) REFERENCES transfers(transfer_id),
  FOREIGN KEY (item_id) REFERENCES items(item_id)
);
CREATE TABLE IF NOT EXISTS _sync_check (id INTEGER PRIMARY KEY, note TEXT);
INSERT INTO _sync_check VALUES(1,'sync-test');
DELETE FROM sqlite_sequence;
INSERT INTO sqlite_sequence VALUES('suppliers',13);
INSERT INTO sqlite_sequence VALUES('items',34);
INSERT INTO sqlite_sequence VALUES('purchases',14);
INSERT INTO sqlite_sequence VALUES('purchase_lines',56);
INSERT INTO sqlite_sequence VALUES('inventory_tx',56);
INSERT INTO sqlite_sequence VALUES('batch_config',1);
INSERT INTO sqlite_sequence VALUES('recipe_batch',11);
INSERT INTO sqlite_sequence VALUES('daily_reports',1);
INSERT INTO sqlite_sequence VALUES('stocktakes',1);
INSERT INTO sqlite_sequence VALUES('stocktake_lines',20);
CREATE INDEX idx_items_supplier_id ON items(supplier_id);
CREATE INDEX idx_items_name ON items(name);
CREATE INDEX idx_recipe_batch_batch_config_id ON recipe_batch(batch_config_id);
CREATE INDEX idx_recipe_batch_item_id ON recipe_batch(item_id);
CREATE INDEX idx_daily_reports_report_date ON daily_reports(report_date);
CREATE INDEX idx_purchases_supplier_id ON purchases(supplier_id);
CREATE INDEX idx_purchases_purchased_at ON purchases(purchased_at);
CREATE INDEX idx_purchase_lines_purchase_id ON purchase_lines(purchase_id);
CREATE INDEX idx_purchase_lines_item_id ON purchase_lines(item_id);
CREATE INDEX idx_stocktakes_taken_at ON stocktakes(taken_at);
CREATE INDEX idx_stocktake_lines_stocktake_id ON stocktake_lines(stocktake_id);
CREATE INDEX idx_stocktake_lines_item_id ON stocktake_lines(item_id);
CREATE INDEX idx_inventory_tx_item_id ON inventory_tx(item_id);
CREATE INDEX idx_inventory_tx_happened_at ON inventory_tx(happened_at);
CREATE INDEX idx_inventory_tx_type ON inventory_tx(tx_type);
CREATE INDEX idx_inventory_tx_ref ON inventory_tx(ref_type, ref_id);
COMMIT;
