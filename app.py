from __future__ import annotations

import os
import sqlite3
from flask import Flask, g, redirect, render_template, request, url_for, flash, abort

APP_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(APP_DIR, "takoyaki_inventory.db")

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"  # flash用（あとで環境変数にするのが理想）


# -----------------------------
# DB helpers
# -----------------------------
def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        g.db = conn
    return g.db  # type: ignore[return-value]


@app.teardown_appcontext
def close_db(exception: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _to_float(value: str, default: float = 0.0) -> float:
    value = (value or "").strip()
    if value == "":
        return default
    return float(value)


def fetch_suppliers() -> list[sqlite3.Row]:
    db = get_db()
    return db.execute(
        "SELECT supplier_id, name FROM suppliers ORDER BY name ASC"
    ).fetchall()


def fetch_item(item_id: int) -> sqlite3.Row | None:
    db = get_db()
    return db.execute(
        """
        SELECT
          i.item_id,
          i.cost_group,
          i.supplier_id,
          i.name,
          i.unit_base,
          i.reorder_point,
          i.ref_unit_price,
          i.is_fixed,
          i.is_active,
          s.name AS supplier_name
        FROM items i
        LEFT JOIN suppliers s ON s.supplier_id = i.supplier_id
        WHERE i.item_id = ?
        """,
        (item_id,),
    ).fetchone()


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def index():
    return redirect(url_for("items_list"))


@app.get("/items")
def items_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT
          i.item_id,
          i.name,
          i.unit_base,
          i.reorder_point,
          i.ref_unit_price,
          i.is_fixed,
          i.cost_group,
          i.is_active,
          s.name AS supplier_name
        FROM items i
        LEFT JOIN suppliers s ON s.supplier_id = i.supplier_id
        ORDER BY i.item_id DESC
        """
    ).fetchall()
    return render_template("items_list.html", items=rows)


@app.get("/items/new")
def item_new_form():
    suppliers = fetch_suppliers()
    return render_template("item_new.html", suppliers=suppliers)


@app.post("/items")
def item_create():
    supplier_id_raw = request.form.get("supplier_id", "").strip()
    supplier_id = int(supplier_id_raw) if supplier_id_raw else None

    name = (request.form.get("name") or "").strip()
    unit_base = (request.form.get("unit_base") or "").strip()
    reorder_point = _to_float(request.form.get("reorder_point", ""), 0.0)
    ref_unit_price = _to_float(request.form.get("ref_unit_price", ""), 0.0)
    is_fixed = 1 if request.form.get("is_fixed") == "1" else 0
    cost_group = (request.form.get("cost_group") or "SUPPLIES").strip()
    if cost_group not in ("FOOD", "SUPPLIES"):
        cost_group = "SUPPLIES"
    is_active = 1 if request.form.get("is_active") == "1" else 0

    # バリデーション（最低限）
    errors: list[str] = []
    if not name:
        errors.append("材料名（name）は必須です。")
    if not unit_base:
        errors.append("単位（unit_base）は必須です。（例: g / ml / pcs）")
    if reorder_point < 0:
        errors.append("発注目安（reorder_point）は0以上にしてください。")
    if ref_unit_price < 0:
        errors.append("参考価格（ref_unit_price）は0以上にしてください。")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("item_new_form"))

    db = get_db()
    try:
        # category は使わないので NULL で入れる（列が存在してもOK）
        db.execute(
            """
            INSERT INTO items (
              supplier_id, name, category, unit_base,
              reorder_point, ref_unit_price, is_fixed, cost_group, is_active
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
            """,
            (supplier_id, name, unit_base, reorder_point, ref_unit_price, is_fixed, cost_group, is_active),
        )
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        flash(f"登録に失敗しました（整合性エラー）: {e}", "error")
        return redirect(url_for("item_new_form"))
    except Exception as e:
        db.rollback()
        flash(f"登録に失敗しました: {e}", "error")
        return redirect(url_for("item_new_form"))

    flash("材料を登録しました。", "success")
    return redirect(url_for("items_list"))


# =============================
# Suppliers（登録・編集）
# =============================
def fetch_supplier(supplier_id: int) -> sqlite3.Row | None:
    db = get_db()
    return db.execute(
        """
        SELECT supplier_id, name, phone, note, created_at
        FROM suppliers
        WHERE supplier_id = ?
        """,
        (supplier_id,),
    ).fetchone()


@app.get("/suppliers")
def suppliers_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT supplier_id, name, phone, note, created_at
        FROM suppliers
        ORDER BY supplier_id DESC
        """
    ).fetchall()
    return render_template("suppliers_list.html", suppliers=rows)


@app.get("/suppliers/new")
def supplier_new_form():
    return render_template("supplier_new.html")


@app.post("/suppliers")
def supplier_create():
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip() or None
    note = (request.form.get("note") or "").strip() or None

    errors: list[str] = []
    if not name:
        errors.append("仕入れ先名（name）は必須です。")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("supplier_new_form"))

    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO suppliers (name, phone, note)
            VALUES (?, ?, ?)
            """,
            (name, phone, note),
        )
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        flash(f"登録に失敗しました（整合性エラー）: {e}", "error")
        return redirect(url_for("supplier_new_form"))
    except Exception as e:
        db.rollback()
        flash(f"登録に失敗しました: {e}", "error")
        return redirect(url_for("supplier_new_form"))

    flash("仕入れ先を登録しました。", "success")
    return redirect(url_for("suppliers_list"))


@app.get("/suppliers/<int:supplier_id>/edit")
def supplier_edit_form(supplier_id: int):
    supplier = fetch_supplier(supplier_id)
    if supplier is None:
        abort(404)
    return render_template("supplier_edit.html", supplier=supplier)


@app.post("/suppliers/<int:supplier_id>/update")
def supplier_update(supplier_id: int):
    supplier = fetch_supplier(supplier_id)
    if supplier is None:
        abort(404)

    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip() or None
    note = (request.form.get("note") or "").strip() or None

    errors: list[str] = []
    if not name:
        errors.append("仕入れ先名（name）は必須です。")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("supplier_edit_form", supplier_id=supplier_id))

    db = get_db()
    try:
        db.execute(
            """
            UPDATE suppliers
            SET name = ?, phone = ?, note = ?
            WHERE supplier_id = ?
            """,
            (name, phone, note, supplier_id),
        )
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        flash(f"更新に失敗しました（整合性エラー）: {e}", "error")
        return redirect(url_for("supplier_edit_form", supplier_id=supplier_id))
    except Exception as e:
        db.rollback()
        flash(f"更新に失敗しました: {e}", "error")
        return redirect(url_for("supplier_edit_form", supplier_id=supplier_id))

    flash("仕入れ先を更新しました。", "success")
    return redirect(url_for("suppliers_list"))


@app.post("/suppliers/<int:supplier_id>/delete")
def supplier_delete(supplier_id: int):
    db = get_db()

    supplier = db.execute(
        "SELECT supplier_id, name FROM suppliers WHERE supplier_id = ?",
        (supplier_id,),
    ).fetchone()
    if supplier is None:
        abort(404)

    try:
        db.execute("DELETE FROM suppliers WHERE supplier_id = ?", (supplier_id,))
        db.commit()
        flash(f"仕入れ先を削除しました: {supplier['name']}", "success")
    except sqlite3.IntegrityError as e:
        db.rollback()
        flash(f"削除できませんでした（関連データあり）: {e}", "error")
    except Exception as e:
        db.rollback()
        flash(f"削除に失敗しました: {e}", "error")

    return redirect(url_for("suppliers_list"))


# =============================
# Purchases（入庫）: 一覧 / 新規 / 登録 / 詳細
# =============================
def fetch_active_items() -> list[sqlite3.Row]:
    db = get_db()
    return db.execute(
        """
        SELECT item_id, name, unit_base, ref_unit_price
        FROM items
        WHERE is_active = 1
        ORDER BY name ASC
        """
    ).fetchall()


@app.get("/purchases")
def purchases_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT
          p.purchase_id,
          p.purchased_at,
          p.total_amount,
          p.note,
          s.name AS supplier_name
        FROM purchases p
        LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
        ORDER BY p.purchased_at DESC, p.purchase_id DESC
        """
    ).fetchall()
    return render_template("purchases_list.html", purchases=rows)


@app.get("/purchases/new")
def purchase_new_form():
    suppliers = fetch_suppliers()
    items = fetch_active_items()
    return render_template("purchase_new.html", suppliers=suppliers, items=items)


@app.post("/purchases")
def purchase_create():
    db = get_db()

    supplier_id_raw = (request.form.get("supplier_id") or "").strip()
    supplier_id = int(supplier_id_raw) if supplier_id_raw else None

    purchased_at = (request.form.get("purchased_at") or "").strip()
    # HTMLのdatetime-localが空の時はDB側のDEFAULTに任せたいので None にする
    purchased_at = purchased_at if purchased_at else None

    note = (request.form.get("note") or "").strip() or None

    # 明細（最大10行想定）
    item_ids = request.form.getlist("item_id")
    qty_list = request.form.getlist("qty")
    unit_price_list = request.form.getlist("unit_price")

    lines: list[tuple[int, float, float | None]] = []
    errors: list[str] = []

    for idx, (item_id_raw, qty_raw, unit_price_raw) in enumerate(
        zip(item_ids, qty_list, unit_price_list), start=1
    ):
        item_id_raw = (item_id_raw or "").strip()
        qty_raw = (qty_raw or "").strip()
        unit_price_raw = (unit_price_raw or "").strip()

        if item_id_raw == "" and qty_raw == "" and unit_price_raw == "":
            continue  # 完全空行はスキップ

        if item_id_raw == "":
            errors.append(f"{idx}行目：材料を選択してください。")
            continue

        if qty_raw == "":
            errors.append(f"{idx}行目：数量(qty)を入力してください。")
            continue

        try:
            item_id = int(item_id_raw)
        except ValueError:
            errors.append(f"{idx}行目：材料IDが不正です。")
            continue

        try:
            qty = float(qty_raw)
        except ValueError:
            errors.append(f"{idx}行目：数量(qty)が数値ではありません。")
            continue

        if qty <= 0:
            errors.append(f"{idx}行目：数量(qty)は0より大きくしてください。")
            continue

        unit_price: float | None = None
        if unit_price_raw != "":
            try:
                unit_price = float(unit_price_raw)
                if unit_price < 0:
                    errors.append(f"{idx}行目：単価(unit_price)は0以上にしてください。")
                    continue
            except ValueError:
                errors.append(f"{idx}行目：単価(unit_price)が数値ではありません。")
                continue

        lines.append((item_id, qty, unit_price))

    if not lines:
        errors.append("明細が1行もありません。材料と数量を入力してください。")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("purchase_new_form"))

    try:
        # トランザクション（ヘッダ＋明細＋在庫履歴をまとめて登録）
        db.execute("BEGIN;")

        # purchases（ヘッダ）
        if purchased_at is None:
            cur = db.execute(
                """
                INSERT INTO purchases (supplier_id, note, total_amount)
                VALUES (?, ?, NULL)
                """,
                (supplier_id, note),
            )
        else:
            # datetime-local -> "YYYY-MM-DDTHH:MM" なので、SQLiteが扱いやすいように " " に置換
            purchased_at_db = purchased_at.replace("T", " ")
            cur = db.execute(
                """
                INSERT INTO purchases (supplier_id, purchased_at, note, total_amount)
                VALUES (?, ?, ?, NULL)
                """,
                (supplier_id, purchased_at_db, note),
            )

        purchase_id = cur.lastrowid

        # 明細＆在庫履歴
        total = 0.0
        for (item_id, qty, unit_price) in lines:
            line_amount = None
            if unit_price is not None:
                line_amount = qty * unit_price
                total += line_amount

            # purchase_lines
            db.execute(
                """
                INSERT INTO purchase_lines (purchase_id, item_id, qty, unit_price, line_amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                (purchase_id, item_id, qty, unit_price, line_amount),
            )

            # inventory_tx（在庫増加）
            db.execute(
                """
                INSERT INTO inventory_tx (
                  happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note
                )
                VALUES (
                  COALESCE(?, datetime('now')),
                  ?, ?, 'PURCHASE', 'STORE', 'PURCHASE', ?, ?
                )
                """,
                (
                    purchased_at.replace("T", " ") if purchased_at else None,
                    item_id,
                    qty,
                    purchase_id,
                    note,
                ),
            )

        # 合計金額を保存（単価が全部空なら 0 のままになる）
        db.execute(
            "UPDATE purchases SET total_amount = ? WHERE purchase_id = ?",
            (total, purchase_id),
        )

        db.commit()
    except Exception as e:
        db.rollback()
        flash(f"入庫登録に失敗しました: {e}", "error")
        return redirect(url_for("purchase_new_form"))

    flash("入庫（仕入れ）を登録しました。", "success")
    return redirect(url_for("purchase_detail", purchase_id=purchase_id))


@app.get("/purchases/<int:purchase_id>")
def purchase_detail(purchase_id: int):
    db = get_db()

    header = db.execute(
        """
        SELECT
          p.purchase_id,
          p.purchased_at,
          p.total_amount,
          p.note,
          s.name AS supplier_name
        FROM purchases p
        LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
        WHERE p.purchase_id = ?
        """,
        (purchase_id,),
    ).fetchone()

    if header is None:
        abort(404)

    lines = db.execute(
        """
        SELECT
          pl.purchase_line_id,
          pl.qty,
          pl.unit_price,
          pl.line_amount,
          i.name AS item_name,
          i.unit_base
        FROM purchase_lines pl
        JOIN items i ON i.item_id = pl.item_id
        WHERE pl.purchase_id = ?
        ORDER BY pl.purchase_line_id ASC
        """,
        (purchase_id,),
    ).fetchall()

    return render_template("purchase_detail.html", header=header, lines=lines)


@app.get("/purchases/<int:purchase_id>/edit")
def purchase_edit_form(purchase_id: int):
    db = get_db()

    header = db.execute(
        """
        SELECT
          p.purchase_id,
          p.purchased_at,
          p.note,
          p.supplier_id,
          s.name AS supplier_name
        FROM purchases p
        LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
        WHERE p.purchase_id = ?
        """,
        (purchase_id,),
    ).fetchone()
    if header is None:
        abort(404)

    lines = db.execute(
        """
        SELECT item_id, qty, unit_price
        FROM purchase_lines
        WHERE purchase_id = ?
        ORDER BY purchase_line_id ASC
        """,
        (purchase_id,),
    ).fetchall()

    line_rows: list[dict[str, object]] = []
    for l in lines:
        line_rows.append(
            {
                "item_id": l["item_id"],
                "qty": l["qty"],
                "unit_price": l["unit_price"],
            }
        )
    while len(line_rows) < 10:
        line_rows.append({"item_id": "", "qty": "", "unit_price": ""})
    line_rows = line_rows[:10]

    purchased_at_local = ""
    if header["purchased_at"]:
        purchased_at_local = str(header["purchased_at"]).replace(" ", "T")

    suppliers = fetch_suppliers()
    items = fetch_active_items()
    return render_template(
        "purchase_edit.html",
        header=header,
        line_rows=line_rows,
        suppliers=suppliers,
        items=items,
        purchased_at_local=purchased_at_local,
    )


@app.post("/purchases/<int:purchase_id>/update")
def purchase_update(purchase_id: int):
    db = get_db()

    header = db.execute(
        "SELECT purchase_id, purchased_at FROM purchases WHERE purchase_id = ?",
        (purchase_id,),
    ).fetchone()
    if header is None:
        abort(404)

    supplier_id_raw = (request.form.get("supplier_id") or "").strip()
    supplier_id = int(supplier_id_raw) if supplier_id_raw else None

    purchased_at = (request.form.get("purchased_at") or "").strip()
    purchased_at_db = purchased_at.replace("T", " ") if purchased_at else header["purchased_at"]

    note = (request.form.get("note") or "").strip() or None

    item_ids = request.form.getlist("item_id")
    qty_list = request.form.getlist("qty")
    unit_price_list = request.form.getlist("unit_price")

    lines: list[tuple[int, float, float | None]] = []
    errors: list[str] = []

    for idx, (item_id_raw, qty_raw, unit_price_raw) in enumerate(
        zip(item_ids, qty_list, unit_price_list), start=1
    ):
        item_id_raw = (item_id_raw or "").strip()
        qty_raw = (qty_raw or "").strip()
        unit_price_raw = (unit_price_raw or "").strip()

        if item_id_raw == "" and qty_raw == "" and unit_price_raw == "":
            continue

        if item_id_raw == "":
            errors.append(f"{idx}行目：材料を選択してください。")
            continue

        if qty_raw == "":
            errors.append(f"{idx}行目：数量(qty)を入力してください。")
            continue

        try:
            item_id = int(item_id_raw)
        except ValueError:
            errors.append(f"{idx}行目：材料IDが不正です。")
            continue

        try:
            qty = float(qty_raw)
        except ValueError:
            errors.append(f"{idx}行目：数量(qty)が数値ではありません。")
            continue

        if qty <= 0:
            errors.append(f"{idx}行目：数量(qty)は0より大きくしてください。")
            continue

        unit_price: float | None = None
        if unit_price_raw != "":
            try:
                unit_price = float(unit_price_raw)
                if unit_price < 0:
                    errors.append(f"{idx}行目：単価(unit_price)は0以上にしてください。")
                    continue
            except ValueError:
                errors.append(f"{idx}行目：単価(unit_price)が数値ではありません。")
                continue

        lines.append((item_id, qty, unit_price))

    if not lines:
        errors.append("明細が1行もありません。材料と数量を入力してください。")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("purchase_edit_form", purchase_id=purchase_id))

    try:
        db.execute("BEGIN;")

        db.execute(
            """
            UPDATE purchases
            SET supplier_id = ?, purchased_at = ?, note = ?, total_amount = NULL
            WHERE purchase_id = ?
            """,
            (supplier_id, purchased_at_db, note, purchase_id),
        )

        db.execute(
            "DELETE FROM inventory_tx WHERE ref_type = 'PURCHASE' AND ref_id = ?",
            (purchase_id,),
        )
        db.execute("DELETE FROM purchase_lines WHERE purchase_id = ?", (purchase_id,))

        total = 0.0
        for (item_id, qty, unit_price) in lines:
            line_amount = None
            if unit_price is not None:
                line_amount = qty * unit_price
                total += line_amount

            db.execute(
                """
                INSERT INTO purchase_lines (purchase_id, item_id, qty, unit_price, line_amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                (purchase_id, item_id, qty, unit_price, line_amount),
            )

            db.execute(
                """
                INSERT INTO inventory_tx (
                  happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note
                )
                VALUES (
                  COALESCE(?, datetime('now')),
                  ?, ?, 'PURCHASE', 'STORE', 'PURCHASE', ?, ?
                )
                """,
                (
                    purchased_at_db,
                    item_id,
                    qty,
                    purchase_id,
                    note,
                ),
            )

        db.execute(
            "UPDATE purchases SET total_amount = ? WHERE purchase_id = ?",
            (total, purchase_id),
        )

        db.commit()
    except Exception as e:
        db.rollback()
        flash(f"更新に失敗しました: {e}", "error")
        return redirect(url_for("purchase_edit_form", purchase_id=purchase_id))

    flash("入庫を更新しました。", "success")
    return redirect(url_for("purchase_detail", purchase_id=purchase_id))


@app.post("/purchases/<int:purchase_id>/delete")
def purchase_delete(purchase_id: int):
    db = get_db()

    header = db.execute(
        "SELECT purchase_id FROM purchases WHERE purchase_id = ?",
        (purchase_id,),
    ).fetchone()
    if header is None:
        abort(404)

    try:
        db.execute("BEGIN;")
        db.execute(
            "DELETE FROM inventory_tx WHERE ref_type = 'PURCHASE' AND ref_id = ?",
            (purchase_id,),
        )
        db.execute("DELETE FROM purchases WHERE purchase_id = ?", (purchase_id,))
        db.commit()
    except Exception as e:
        db.rollback()
        flash(f"削除に失敗しました: {e}", "error")
        return redirect(url_for("purchase_detail", purchase_id=purchase_id))

    flash("入庫を削除しました。", "success")
    return redirect(url_for("purchases_list"))


# -----------------------------
# Inventory (在庫一覧)
# -----------------------------
@app.get("/inventory")
def inventory_list():
    db = get_db()

    # 在庫残量 = inventory_tx の qty_delta を location 別に合計
    rows = db.execute(
        """
        WITH inv AS (
          SELECT
            item_id,
            SUM(CASE WHEN location = 'STORE' THEN qty_delta ELSE 0 END) AS qty_store,
            SUM(CASE WHEN location = 'WAREHOUSE' THEN qty_delta ELSE 0 END) AS qty_warehouse,
            SUM(qty_delta) AS qty_total
          FROM inventory_tx
          GROUP BY item_id
        )
        SELECT
          i.item_id,
          i.name,
          i.unit_base,
          i.reorder_point,
          i.ref_unit_price,
          i.is_fixed,
          i.is_active,
          s.name AS supplier_name,
          COALESCE(inv.qty_store, 0) AS qty_store,
          COALESCE(inv.qty_warehouse, 0) AS qty_warehouse,
          COALESCE(inv.qty_total, 0) AS qty_total
        FROM items i
        LEFT JOIN inv ON inv.item_id = i.item_id
        LEFT JOIN suppliers s ON s.supplier_id = i.supplier_id
        WHERE i.is_active = 1
        ORDER BY
          (COALESCE(inv.qty_total, 0) <= i.reorder_point) DESC,
          i.name ASC
        """
    ).fetchall()

    return render_template("inventory_list.html", rows=rows)


# -----------------------------
# Edit (更新)
# -----------------------------
@app.get("/items/<int:item_id>/edit")
def item_edit_form(item_id: int):
    item = fetch_item(item_id)
    if item is None:
        abort(404)
    suppliers = fetch_suppliers()
    return render_template("item_edit.html", item=item, suppliers=suppliers)


@app.post("/items/<int:item_id>/update")
def item_update(item_id: int):
    item = fetch_item(item_id)
    if item is None:
        abort(404)

    supplier_id_raw = request.form.get("supplier_id", "").strip()
    supplier_id = int(supplier_id_raw) if supplier_id_raw else None

    name = (request.form.get("name") or "").strip()
    unit_base = (request.form.get("unit_base") or "").strip()
    reorder_point = _to_float(request.form.get("reorder_point", ""), 0.0)
    ref_unit_price = _to_float(request.form.get("ref_unit_price", ""), 0.0)
    is_fixed = 1 if request.form.get("is_fixed") == "1" else 0
    cost_group = (request.form.get("cost_group") or "SUPPLIES").strip()
    if cost_group not in ("FOOD", "SUPPLIES"):
        cost_group = "SUPPLIES"
    is_active = 1 if request.form.get("is_active") == "1" else 0

    errors: list[str] = []
    if not name:
        errors.append("材料名（name）は必須です。")
    if not unit_base:
        errors.append("単位（unit_base）は必須です。（例: g / ml / pcs）")
    if reorder_point < 0:
        errors.append("発注目安（reorder_point）は0以上にしてください。")
    if ref_unit_price < 0:
        errors.append("参考価格（ref_unit_price）は0以上にしてください。")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("item_edit_form", item_id=item_id))

    db = get_db()
    try:
        # category は使わないので NULL で上書きしてOK
        db.execute(
            """
            UPDATE items
            SET
              supplier_id = ?,
              name = ?,
              category = NULL,
              unit_base = ?,
              reorder_point = ?,
              ref_unit_price = ?,
              is_fixed = ?,
              cost_group = ?,
              is_active = ?
            WHERE item_id = ?
            """,
            (supplier_id, name, unit_base, reorder_point, ref_unit_price, is_fixed, cost_group, is_active, item_id),
        )
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        flash(f"更新に失敗しました（整合性エラー）: {e}", "error")
        return redirect(url_for("item_edit_form", item_id=item_id))
    except Exception as e:
        db.rollback()
        flash(f"更新に失敗しました: {e}", "error")
        return redirect(url_for("item_edit_form", item_id=item_id))

    flash("材料を更新しました。", "success")
    return redirect(url_for("items_list"))


@app.post("/items/<int:item_id>/delete")
def item_delete(item_id: int):
    db = get_db()

    # 存在確認
    item = db.execute(
        "SELECT item_id, name FROM items WHERE item_id = ?", (item_id,)
    ).fetchone()
    if item is None:
        abort(404)

    try:
        # まず物理削除を試す
        db.execute("DELETE FROM items WHERE item_id = ?", (item_id,))
        db.commit()
        flash(f"材料を削除しました: {item['name']}", "success")
    except sqlite3.IntegrityError:
        # 関連データがあると削除できないので、無効化へ
        db.rollback()
        db.execute("UPDATE items SET is_active = 0 WHERE item_id = ?", (item_id,))
        db.commit()
        flash(
            f"関連データがあるため物理削除できませんでした。無効化（is_active=0）しました: {item['name']}",
            "error",
        )
    except Exception as e:
        db.rollback()
        flash(f"削除に失敗しました: {e}", "error")

    return redirect(url_for("items_list"))


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
