from __future__ import annotations

import sqlite3
from itertools import groupby
import math
from datetime import date, datetime
from flask import Flask, redirect, render_template, request, url_for, flash, abort

from db import close_db, commit_and_sync, get_db

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"  # flash用（あとで環境変数にするのが理想）


app.teardown_appcontext(close_db)


_items_note_column_ready = False


def ensure_items_note_column() -> None:
    db = get_db()
    try:
        cols = db.execute("PRAGMA table_info(items)").fetchall()
        col_names = {row["name"] for row in cols}
        if "note" not in col_names:
            db.execute("ALTER TABLE items ADD COLUMN note TEXT")
            commit_and_sync()
    except Exception:
        db.rollback()


def ensure_stocktake_lines_cost_columns() -> None:
    db = get_db()
    try:
        cols = db.execute("PRAGMA table_info(stocktake_lines)").fetchall()
        col_names = {row["name"] for row in cols}
        if "unit_cost" not in col_names:
            db.execute("ALTER TABLE stocktake_lines ADD COLUMN unit_cost REAL")
        if "line_amount" not in col_names:
            db.execute("ALTER TABLE stocktake_lines ADD COLUMN line_amount REAL")
        commit_and_sync()
    except Exception:
        db.rollback()


@app.before_request
def _ensure_schema():
    global _items_note_column_ready
    if _items_note_column_ready:
        return
    ensure_items_note_column()
    ensure_stocktake_lines_cost_columns()
    _items_note_column_ready = True


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
          i.note,
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
def home():
    return render_template("home.html")


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
          i.note,
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
    note = (request.form.get("note") or "").strip() or None
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
              reorder_point, ref_unit_price, note, is_fixed, cost_group, is_active
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (supplier_id, name, unit_base, reorder_point, ref_unit_price, note, is_fixed, cost_group, is_active),
        )
        commit_and_sync()
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
    location = "WAREHOUSE"

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
        commit_and_sync()
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
        commit_and_sync()
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
        commit_and_sync()
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
          COALESCE(s.name,'（未設定）') AS supplier_name,
          p.note,
          p.total_amount,
          COALESCE(itx.location, 'STORE') AS location
        FROM purchases p
        LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
        LEFT JOIN (
          SELECT ref_id, MIN(location) AS location
          FROM inventory_tx
          WHERE ref_type = 'PURCHASE'
          GROUP BY ref_id
        ) itx ON itx.ref_id = p.purchase_id
        ORDER BY p.purchased_at DESC, p.purchase_id DESC
        """
    ).fetchall()
    created = request.args.get("created")
    try:
        created_purchase_id = int(created) if created else None
    except ValueError:
        created_purchase_id = None
    return render_template(
        "purchases_list.html",
        purchases=rows,
        created_purchase_id=created_purchase_id,
    )


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

    purchased_date = (request.form.get("purchased_date") or "").strip()
    if purchased_date:
        purchased_at = f"{purchased_date} 09:00:00"
    else:
        # 空ならDB側のDEFAULTに任せる
        purchased_at = None

    location = "WAREHOUSE"

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
        if not qty.is_integer():
            errors.append(f"{idx}行目：数量(qty)は整数で入力してください。")
            continue

        item_row = db.execute(
            "SELECT name, unit_base FROM items WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if item_row is None:
            errors.append(f"{idx}行目：材料IDが存在しません。")
            continue
        if item_row["unit_base"] == "pcs" and not qty.is_integer():
            errors.append(f"{idx}行目：{item_row['name']} はpcsなので整数で入力してください。")
            continue

        if unit_price_raw == "":
            errors.append(f"{idx}行目：単価(unit_price)を入力してください。")
            continue

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
            purchased_at_db = purchased_at
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
                  ?, ?, 'PURCHASE', ?, 'PURCHASE', ?, ?
                )
                """,
                (
                    purchased_at,
                    item_id,
                    qty,
                    location,
                    purchase_id,
                    note,
                ),
            )

        # 合計金額を保存（単価が全部空なら 0 のままになる）
        db.execute(
            "UPDATE purchases SET total_amount = ? WHERE purchase_id = ?",
            (total, purchase_id),
        )

        commit_and_sync()
    except Exception as e:
        db.rollback()
        flash(f"入庫登録に失敗しました: {e}", "error")
        return redirect(url_for("purchase_new_form"))

    flash("入庫（仕入れ）を登録しました。", "success")
    return redirect(url_for("purchases_list", created=purchase_id))


@app.post("/purchases/new-from-list")
def purchase_new_from_list():
    db = get_db()

    supplier_id_raw = (request.form.get("supplier_id") or "").strip()
    supplier_id = int(supplier_id_raw) if supplier_id_raw else None

    # チェックされた材料
    selected_item_ids_raw = request.form.getlist("selected_item_ids")
    selected_item_ids = []
    for x in selected_item_ids_raw:
        try:
            selected_item_ids.append(int(x))
        except ValueError:
            pass

    if not selected_item_ids:
        flash("チェックされた材料がありません。", "error")
        return redirect(url_for("shopping_list"))

    prefill_lines = []
    for item_id in selected_item_ids[:10]:  # purchase_new.html が10行固定なので最大10件
        qty_raw = (request.form.get(f"qty_{item_id}") or "").strip()
        unit_price_raw = (request.form.get(f"unit_price_{item_id}") or "").strip()

        try:
            qty = float(qty_raw) if qty_raw else 0.0
        except ValueError:
            qty = 0.0

        # 単価は任意
        unit_price = None
        if unit_price_raw != "":
            try:
                unit_price = float(unit_price_raw)
            except ValueError:
                unit_price = None

        prefill_lines.append(
            {
                "item_id": item_id,
                "qty": qty,
                "unit_price": unit_price,
            }
        )

    suppliers = fetch_suppliers()
    items = fetch_active_items()

    # ちょい親切：メモに「買い物リストから」入れとく
    default_note = "買い物リストから作成"

    return render_template(
        "purchase_new.html",
        suppliers=suppliers,
        items=items,
        prefill_lines=prefill_lines,
        default_supplier_id=supplier_id,
        default_note=default_note,
    )


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

    default_purchased_date = ""
    if header["purchased_at"]:
        default_purchased_date = str(header["purchased_at"])[:10]

    suppliers = fetch_suppliers()
    items = fetch_active_items()
    return render_template(
        "purchase_edit.html",
        header=header,
        line_rows=line_rows,
        suppliers=suppliers,
        items=items,
        default_purchased_date=default_purchased_date,
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

    purchased_date = (request.form.get("purchased_date") or "").strip()
    if purchased_date:
        purchased_at_db = f"{purchased_date} 09:00:00"
    else:
        purchased_at_db = header["purchased_at"]

    location = "WAREHOUSE"

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
        if not qty.is_integer():
            errors.append(f"{idx}行目：数量(qty)は整数で入力してください。")
            continue

        item_row = db.execute(
            "SELECT name, unit_base FROM items WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if item_row is None:
            errors.append(f"{idx}行目：材料IDが存在しません。")
            continue
        if item_row["unit_base"] == "pcs" and not qty.is_integer():
            errors.append(f"{idx}行目：{item_row['name']} はpcsなので整数で入力してください。")
            continue

        if unit_price_raw == "":
            errors.append(f"{idx}行目：単価(unit_price)を入力してください。")
            continue

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
                  ?, ?, 'PURCHASE', ?, 'PURCHASE', ?, ?
                )
                """,
                (
                    purchased_at_db,
                    item_id,
                    qty,
                    location,
                    purchase_id,
                    note,
                ),
            )

        db.execute(
            "UPDATE purchases SET total_amount = ? WHERE purchase_id = ?",
            (total, purchase_id),
        )

        commit_and_sync()
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
        commit_and_sync()
    except Exception as e:
        db.rollback()
        flash(f"削除に失敗しました: {e}", "error")
        return redirect(url_for("purchase_detail", purchase_id=purchase_id))

    flash("入庫を削除しました。", "success")
    return redirect(url_for("purchases_list"))


# -----------------------------
# Stocktakes (棚卸)
# -----------------------------
def _to_datetime_seconds(dt_local: str | None) -> str | None:
    """
    HTML datetime-local: 'YYYY-MM-DDTHH:MM' -> 'YYYY-MM-DD HH:MM:00'
    """
    if not dt_local:
        return None
    s = dt_local.strip()
    if not s:
        return None
    s = s.replace("T", " ")
    # 秒がない場合は補完
    if len(s) == 16:  # 'YYYY-MM-DD HH:MM'
        s = s + ":00"
    return s


def fetch_items_for_stocktake(only_food: bool) -> list[sqlite3.Row]:
    db = get_db()
    if only_food:
        return db.execute(
            """
            SELECT item_id, name, unit_base, cost_group
            FROM items
            WHERE is_active = 1 AND cost_group = 'FOOD'
            ORDER BY name ASC
            """
        ).fetchall()
    else:
        return db.execute(
            """
            SELECT item_id, name, unit_base, cost_group
            FROM items
            WHERE is_active = 1
            ORDER BY name ASC
            """
    ).fetchall()


def ceil_to_step(x: float, step: float) -> float:
    if step <= 0:
        return x
    # 浮動小数の誤差対策で少しだけ下げてからceil
    return math.ceil((x - 1e-12) / step) * step


def month_range(ym: str):
    """
    ym: 'YYYY-MM'
    return: (start_date_str, next_month_start_str)
    """
    y, m = ym.split("-")
    y = int(y)
    m = int(m)
    start = date(y, m, 1)
    if m == 12:
        nxt = date(y + 1, 1, 1)
    else:
        nxt = date(y, m + 1, 1)
    return start.isoformat(), nxt.isoformat()


def month_range_for_datetime(dt_str: str):
    """
    dt_str: 'YYYY-MM-DD HH:MM:SS'
    return: (month_start_str, next_month_start_str)
    """
    dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
    start = dt.replace(day=1, hour=0, minute=0, second=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def get_opening_monthly_stocktake_id(db, month_start: str, location: str | None = None):
    if location:
        row = db.execute(
            """
            SELECT stocktake_id, taken_at
            FROM stocktakes
            WHERE scope = 'MONTHLY'
              AND location = ?
              AND taken_at < ?
            ORDER BY taken_at DESC
            LIMIT 1
            """,
            (location, month_start),
        ).fetchone()
        return row
    row = db.execute(
        """
        SELECT stocktake_id, taken_at
        FROM stocktakes
        WHERE scope = 'MONTHLY'
          AND taken_at < ?
        ORDER BY taken_at DESC
        LIMIT 1
        """,
        (month_start,),
    ).fetchone()
    return row


def calc_monthly_weighted_unit_cost(
    db, item_id: int, month_start: str, month_end: str, location: str | None = None
):
    """
    月次総平均（加重平均）単価を計算。
    unit_price未入力なら ref_unit_price 代用、代用が発生したら warning を返す。
    """
    # 参考単価
    item = db.execute(
        "SELECT ref_unit_price FROM items WHERE item_id=?", (item_id,)
    ).fetchone()
    ref = float(item["ref_unit_price"] or 0)

    # 期首（月初の前の月次棚卸）
    opening = get_opening_monthly_stocktake_id(db, month_start, location=location)

    opening_qty = 0.0
    opening_amount = 0.0
    used_ref_opening = False

    if opening:
        sl = db.execute(
            """
            SELECT counted_qty, unit_cost, line_amount
            FROM stocktake_lines
            WHERE stocktake_id=? AND item_id=?
            LIMIT 1
            """,
            (opening["stocktake_id"], item_id),
        ).fetchone()
        if sl:
            opening_qty = float(sl["counted_qty"] or 0)
            uc = sl["unit_cost"]
            la = sl["line_amount"]
            if la is not None:
                opening_amount = float(la or 0)
            else:
                # unit_costが無い過去データは参考単価で代用
                used_ref_opening = True
                unit_cost = float(uc) if uc is not None else ref
                opening_amount = opening_qty * unit_cost

    # 当月仕入（実績優先、無ければ参考単価代用）
    rows = db.execute(
        """
        SELECT pl.qty,
               pl.unit_price,
               pl.line_amount,
               i.ref_unit_price AS ref_unit_price
        FROM purchase_lines pl
        JOIN purchases p ON p.purchase_id = pl.purchase_id
        JOIN items i ON i.item_id = pl.item_id
        WHERE pl.item_id=?
          AND p.purchased_at >= ?
          AND p.purchased_at < ?
        """,
        (item_id, month_start, month_end),
    ).fetchall()

    purchased_qty = 0.0
    purchased_amount = 0.0
    used_ref_purchase = False

    for r in rows:
        qty = float(r["qty"] or 0)
        if qty <= 0:
            continue
        purchased_qty += qty

        if r["line_amount"] is not None:
            purchased_amount += float(r["line_amount"] or 0)
        else:
            unit_price = r["unit_price"]
            if unit_price is None:
                # unit_price未入力 → 参考単価で代用
                used_ref_purchase = True
                purchased_amount += qty * float(r["ref_unit_price"] or 0)
            else:
                purchased_amount += qty * float(unit_price)

    denom = opening_qty + purchased_qty
    if denom <= 0:
        # 数量が0なら単価を作れない → 参考単価
        return ref, True, (used_ref_opening or used_ref_purchase)

    avg_unit_cost = (opening_amount + purchased_amount) / denom
    return avg_unit_cost, False, (used_ref_opening or used_ref_purchase)


def calc_initial_stocktake_unit_cost(db, item_id: int, taken_at: str) -> float:
    """
    初回棚卸用: 棚卸日までの仕入実績平均単価を計算。
    unit_price未入力はref_unit_priceで代用、数量0ならref_unit_price。
    """
    item = db.execute(
        "SELECT ref_unit_price FROM items WHERE item_id=?", (item_id,)
    ).fetchone()
    ref = float(item["ref_unit_price"] or 0)

    row = db.execute(
        """
        SELECT
          COALESCE(SUM(
            CASE
              WHEN pl.line_amount IS NOT NULL THEN pl.line_amount
              WHEN pl.unit_price IS NOT NULL THEN pl.qty * pl.unit_price
              ELSE pl.qty * COALESCE(i.ref_unit_price, 0)
            END
          ), 0) AS amount_sum,
          COALESCE(SUM(pl.qty), 0) AS qty_sum
        FROM purchase_lines pl
        JOIN purchases p ON p.purchase_id = pl.purchase_id
        JOIN items i ON i.item_id = pl.item_id
        WHERE pl.item_id = ?
          AND datetime(p.purchased_at) <= datetime(?)
        """,
        (item_id, taken_at),
    ).fetchone()

    qty_sum = float(row["qty_sum"] or 0)
    if qty_sum <= 0:
        return ref
    amount_sum = float(row["amount_sum"] or 0)
    return amount_sum / qty_sum


def format_daily_report_for_line(rep) -> str:
    """
    LINEへコピペする用の本文を作る
    形式:
    【日報】
    ロス
    売れたバッチ
    生産時間(入力値・時間)

    売上(カンマ区切り)

    所感
    """
    waste = int(rep["waste_pieces"] or 0)
    sold = rep["sold_batches"]
    sold_str = str(sold if sold is not None else 0)

    prod = rep["production_minutes"]
    prod_str = f"{float(prod or 0):.1f}"

    sales = rep["sales_amount"]
    sales_int = int(round(float(sales or 0)))
    sales_str = f"{sales_int:,}"

    impression = (rep["impression"] or "").strip()

    return (
        "【日報】\n"
        f"{waste}\n"
        f"{sold_str}\n"
        f"{prod_str}\n\n"
        f"{sales_str}\n\n"
        f"{impression}"
    )


def get_active_pieces_per_batch(db) -> int:
    row = db.execute(
        """
        SELECT pieces_per_batch
        FROM batch_config
        WHERE is_active = 1
        ORDER BY batch_config_id DESC
        LIMIT 1
        """
    ).fetchone()
    return int(row["pieces_per_batch"]) if row else 80  # 念のため80 fallback


def get_active_batch_config(db):
    row = db.execute(
        """
        SELECT batch_config_id, name, pieces_per_batch
        FROM batch_config
        WHERE is_active = 1
        ORDER BY batch_config_id DESC
        LIMIT 1
        """
    ).fetchone()
    return row


def regenerate_inventory_tx_for_daily_report(db, daily_report_id: int) -> int:
    """
    日報IDに紐づく inventory_tx（CONSUME/WASTE）を作り直す。
    return: 作成したtx件数
    """
    rep = db.execute(
        """
        SELECT daily_report_id, report_date, sold_batches, waste_pieces
        FROM daily_reports
        WHERE daily_report_id = ?
        """,
        (daily_report_id,),
    ).fetchone()

    if rep is None:
        return 0

    report_date = rep["report_date"]  # 'YYYY-MM-DD'
    sold_batches = float(rep["sold_batches"] or 0)
    waste_pieces = int(rep["waste_pieces"] or 0)

    pieces_per_batch = get_active_pieces_per_batch(db)
    waste_batches = (waste_pieces / pieces_per_batch) if pieces_per_batch > 0 else 0.0

    happened_at = f"{report_date} 09:00:00"
    location = "STORE"

    # まず既存の自動生成分を削除（編集時に二重計上させない）
    db.execute(
        """
        DELETE FROM inventory_tx
        WHERE ref_type = 'DAILY_REPORT'
          AND ref_id = ?
          AND tx_type IN ('CONSUME', 'WASTE')
        """,
        (daily_report_id,),
    )

    # auto_consume=1 だけ対象（週次で数えるものは0にしておけばOK）
    recipe_rows = db.execute(
        """
        SELECT rb.item_id, rb.qty_per_batch, i.unit_base
        FROM recipe_batch rb
        JOIN batch_config bc ON bc.batch_config_id = rb.batch_config_id
        JOIN items i ON i.item_id = rb.item_id
        WHERE rb.auto_consume = 1
          AND bc.is_active = 1
        """
    ).fetchall()

    created = 0

    for r in recipe_rows:
        item_id = r["item_id"]
        qty_per_batch = float(r["qty_per_batch"] or 0)

        # 通常消費（売れたバッチ数分）
        consume_qty = qty_per_batch * sold_batches

        # ロス消費（ロス個数→バッチ換算→消費量）
        waste_qty = qty_per_batch * waste_batches

        # マイナスで在庫を減らす
        if abs(consume_qty) > 1e-9:
            db.execute(
                """
                INSERT INTO inventory_tx
                  (happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note)
                VALUES
                  (?, ?, ?, 'CONSUME', ?, 'DAILY_REPORT', ?, ?)
                """,
                (
                    happened_at,
                    item_id,
                    -consume_qty,
                    location,
                    daily_report_id,
                    f"日報自動消費：sold_batches={sold_batches}",
                ),
            )
            created += 1

        if abs(waste_qty) > 1e-9:
            db.execute(
                """
                INSERT INTO inventory_tx
                  (happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note)
                VALUES
                  (?, ?, ?, 'WASTE', ?, 'DAILY_REPORT', ?, ?)
                """,
                (
                    happened_at,
                    item_id,
                    -waste_qty,
                    location,
                    daily_report_id,
                    f"日報自動ロス：waste_pieces={waste_pieces}（{waste_batches:.3f} batches）",
                ),
            )
            created += 1

    return created


@app.get("/daily-reports")
def daily_reports_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT daily_report_id, report_date, sold_batches, waste_pieces, production_minutes, sales_amount
        FROM daily_reports
        ORDER BY report_date DESC, daily_report_id DESC
        """
    ).fetchall()
    return render_template("daily_reports_list.html", reports=rows)


@app.get("/daily-reports/new")
def daily_report_new():
    today = date.today().isoformat()
    return render_template("daily_report_new.html", default_date=today)


@app.post("/daily-reports")
def daily_report_create():
    db = get_db()

    report_date = (request.form.get("report_date") or "").strip()
    if not report_date:
        flash("日付（report_date）は必須です", "error")
        return redirect(url_for("daily_report_new"))

    sold_batches = float((request.form.get("sold_batches") or "0").strip() or 0)
    waste_pieces = int((request.form.get("waste_pieces") or "0").strip() or 0)
    production_minutes = float(
        (request.form.get("production_minutes") or "0").strip() or 0
    )
    sales_amount = float((request.form.get("sales_amount") or "0").strip() or 0)
    impression = (request.form.get("impression") or "").strip()

    # 1日1回運用：同じ日付があるなら編集へ誘導（好みで）
    exists = db.execute(
        """
        SELECT daily_report_id FROM daily_reports WHERE report_date = ?
        LIMIT 1
        """,
        (report_date,),
    ).fetchone()
    if exists:
        flash("この日付の日報は既にあります。編集してください。", "error")
        return redirect(
            url_for("daily_report_edit", daily_report_id=exists["daily_report_id"])
        )

    try:
        db.execute("BEGIN")

        db.execute(
            """
            INSERT INTO daily_reports
              (report_date, sold_batches, waste_pieces, production_minutes, sales_amount, impression, created_at)
            VALUES
              (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                report_date,
                sold_batches,
                waste_pieces,
                production_minutes,
                sales_amount,
                impression,
            ),
        )

        daily_report_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()[
            "id"
        ]

        created_tx = regenerate_inventory_tx_for_daily_report(db, daily_report_id)

        db.execute("COMMIT")
        flash(f"日報を登録しました（inventory_tx自動生成: {created_tx}件）", "success")
        return redirect(url_for("daily_report_detail", daily_report_id=daily_report_id))

    except Exception as e:
        db.execute("ROLLBACK")
        flash(f"日報登録に失敗しました: {e}", "error")
        return redirect(url_for("daily_report_new"))


@app.get("/daily-reports/<int:daily_report_id>/edit")
def daily_report_edit(daily_report_id: int):
    db = get_db()
    rep = db.execute(
        """
        SELECT * FROM daily_reports WHERE daily_report_id = ?
        """,
        (daily_report_id,),
    ).fetchone()
    if rep is None:
        abort(404)
    return render_template("daily_report_edit.html", rep=rep)


@app.post("/daily-reports/<int:daily_report_id>/edit")
def daily_report_update(daily_report_id: int):
    db = get_db()

    report_date = (request.form.get("report_date") or "").strip()
    sold_batches = float((request.form.get("sold_batches") or "0").strip() or 0)
    waste_pieces = int((request.form.get("waste_pieces") or "0").strip() or 0)
    production_minutes = float(
        (request.form.get("production_minutes") or "0").strip() or 0
    )
    sales_amount = float((request.form.get("sales_amount") or "0").strip() or 0)
    impression = (request.form.get("impression") or "").strip()

    try:
        db.execute("BEGIN")

        db.execute(
            """
            UPDATE daily_reports
            SET report_date = ?,
                sold_batches = ?,
                waste_pieces = ?,
                production_minutes = ?,
                sales_amount = ?,
                impression = ?
            WHERE daily_report_id = ?
            """,
            (
                report_date,
                sold_batches,
                waste_pieces,
                production_minutes,
                sales_amount,
                impression,
                daily_report_id,
            ),
        )

        created_tx = regenerate_inventory_tx_for_daily_report(db, daily_report_id)

        db.execute("COMMIT")
        flash(f"日報を更新しました（inventory_tx再生成: {created_tx}件）", "success")
        return redirect(url_for("daily_report_detail", daily_report_id=daily_report_id))

    except Exception as e:
        db.execute("ROLLBACK")
        flash(f"日報更新に失敗しました: {e}", "error")
        return redirect(url_for("daily_report_edit", daily_report_id=daily_report_id))


@app.get("/daily-reports/<int:daily_report_id>")
def daily_report_detail(daily_report_id: int):
    db = get_db()
    rep = db.execute(
        """
        SELECT *
        FROM daily_reports
        WHERE daily_report_id = ?
        """,
        (daily_report_id,),
    ).fetchone()

    if rep is None:
        abort(404)

    line_text = format_daily_report_for_line(rep)
    return render_template("daily_report_detail.html", rep=rep, line_text=line_text)


@app.get("/recipe-batch")
def recipe_batch_edit():
    db = get_db()

    bc = get_active_batch_config(db)
    if bc is None:
        flash("アクティブなBATCH_CONFIGがありません。先に batch_config を作成してください。", "error")
        return redirect(url_for("items_list"))

    batch_config_id = bc["batch_config_id"]

    # items と recipe_batch を紐付けて表示
    rows = db.execute(
        """
        SELECT
          i.item_id,
          i.name,
          i.unit_base,
          COALESCE(i.cost_group, 'SUPPLIES') AS cost_group,
          COALESCE(rb.qty_per_batch, 0) AS qty_per_batch,
          COALESCE(rb.auto_consume, 0) AS auto_consume
        FROM items i
        LEFT JOIN recipe_batch rb
          ON rb.item_id = i.item_id
         AND rb.batch_config_id = ?
        WHERE i.is_active = 1
        ORDER BY
          CASE COALESCE(i.cost_group,'SUPPLIES') WHEN 'FOOD' THEN 0 ELSE 1 END,
          i.name ASC
        """,
        (batch_config_id,),
    ).fetchall()

    return render_template(
        "recipe_batch_edit.html",
        bc=bc,
        rows=rows,
    )


@app.post("/recipe-batch")
def recipe_batch_update():
    db = get_db()

    batch_config_id = request.form.get("batch_config_id")
    if not batch_config_id:
        abort(400)
    batch_config_id = int(batch_config_id)

    # 対象items（アクティブ）
    items = db.execute(
        """
        SELECT item_id, unit_base
        FROM items
        WHERE is_active = 1
        ORDER BY item_id
        """
    ).fetchall()

    # 既存レシピ（qtyを保持するため qty_per_batch も取る）
    existing = db.execute(
        """
        SELECT recipe_id, item_id, qty_per_batch, auto_consume
        FROM recipe_batch
        WHERE batch_config_id = ?
        """,
        (batch_config_id,),
    ).fetchall()

    existing_by_item = {
        r["item_id"]: {
            "recipe_id": r["recipe_id"],
            "qty_per_batch": float(r["qty_per_batch"] or 0),
            "auto_consume": int(r["auto_consume"] or 0),
        }
        for r in existing
    }

    updated = 0
    inserted = 0

    try:
        db.execute("BEGIN")

        for it in items:
            item_id = it["item_id"]
            unit_base = it["unit_base"]

            # ✅ auto_consume はチェックのON/OFFだけで設定できる
            auto_consume = 1 if request.form.get(f"auto_{item_id}") == "1" else 0

            # qty_per_batch：空欄なら「既存値を保持」する
            raw_qty = (request.form.get(f"qty_{item_id}") or "").strip()

            if item_id in existing_by_item:
                # 既存がある場合：空欄なら保持、入力があれば更新
                qty = existing_by_item[item_id]["qty_per_batch"]
                if raw_qty != "":
                    try:
                        qty = float(raw_qty)
                    except ValueError:
                        pass  # 変な入力は無視して保持
            else:
                # 既存がない場合：空欄なら0（ただしauto_consume=1なら「設定行」を作る）
                if raw_qty == "":
                    qty = 0.0
                else:
                    try:
                        qty = float(raw_qty)
                    except ValueError:
                        qty = 0.0

            # pcsも小数を許可（小数第3位まで想定）

            if item_id in existing_by_item:
                # 既存行：auto_consume だけの変更もOK、qtyは空欄なら保持
                recipe_id = existing_by_item[item_id]["recipe_id"]
                db.execute(
                    """
                    UPDATE recipe_batch
                    SET qty_per_batch = ?, auto_consume = ?
                    WHERE recipe_id = ?
                    """,
                    (qty, auto_consume, recipe_id),
                )
                updated += 1
            else:
                # 新規：qty>0 もしくは auto_consume=1 のときだけ行を作る
                # （auto_consume=1 で qty=0 の「設定だけ」もOK）
                if qty > 0 or auto_consume == 1:
                    db.execute(
                        """
                        INSERT INTO recipe_batch (batch_config_id, item_id, qty_per_batch, auto_consume)
                        VALUES (?, ?, ?, ?)
                        """,
                        (batch_config_id, item_id, qty, auto_consume),
                    )
                    inserted += 1

        db.execute("COMMIT")
        flash(f"保存しました（追加:{inserted} 更新:{updated}）", "success")
        return redirect(url_for("recipe_batch_edit"))

    except Exception as e:
        db.execute("ROLLBACK")
        flash(f"保存に失敗しました: {e}", "error")
        return redirect(url_for("recipe_batch_edit"))
@app.get("/stocktakes")
def stocktakes_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT
          st.stocktake_id,
          st.taken_at,
          st.scope,
          st.location,
          st.note,
          COUNT(sl.stocktake_line_id) AS line_count
        FROM stocktakes st
        LEFT JOIN stocktake_lines sl ON sl.stocktake_id = st.stocktake_id
        GROUP BY st.stocktake_id
        ORDER BY st.taken_at DESC, st.stocktake_id DESC
        """
    ).fetchall()
    return render_template("stocktakes_list.html", stocktakes=rows)


@app.get("/stocktakes/new")
def stocktake_new_form():
    # デフォルトはFOODのみ
    only_food = request.args.get("only_food", "1") != "0"
    # 月次棚卸は倉庫へ寄せる前提
    location = "WAREHOUSE"

    items = fetch_items_for_stocktake(only_food)

    # 現在の理論在庫（location別）を表示用に持ってくる
    db = get_db()
    current_map = {
        row["item_id"]: float(row["qty"] or 0)
        for row in db.execute(
            """
            SELECT item_id, SUM(qty_delta) AS qty
            FROM inventory_tx
            WHERE location = ?
            GROUP BY item_id
            """,
            (location,),
        ).fetchall()
    }

    return render_template(
        "stocktake_new.html",
        items=items,
        only_food=only_food,
        current_map=current_map,
    )


@app.post("/stocktakes")
def stocktake_create():
    db = get_db()

    taken_at_local = (request.form.get("taken_at") or "").strip()
    taken_at = _to_datetime_seconds(taken_at_local)  # 'YYYY-MM-DD HH:MM:00' or None
    scope = "MONTHLY"  # 今回は月次固定（必要ならフォーム化できます）
    # 月次棚卸は倉庫での実測を前提
    location = "WAREHOUSE"
    note = (request.form.get("note") or "").strip() or None

    only_food = (request.form.get("only_food") or "1") != "0"

    # 明細
    item_ids = request.form.getlist("item_id")
    counted_list = request.form.getlist("counted_qty")

    lines: list[tuple[int, float]] = []
    errors: list[str] = []

    for idx, (item_id_raw, counted_raw) in enumerate(
        zip(item_ids, counted_list), start=1
    ):
        item_id_raw = (item_id_raw or "").strip()
        counted_raw = (counted_raw or "").strip()

        if counted_raw == "":
            continue  # 未入力は「今回は数えてない」とみなしてスキップ

        try:
            item_id = int(item_id_raw)
        except ValueError:
            errors.append(f"{idx}行目：材料IDが不正です。")
            continue

        try:
            counted = float(counted_raw)
        except ValueError:
            errors.append(f"{idx}行目：棚卸数量が数値ではありません。")
            continue

        if counted < 0:
            errors.append(f"{idx}行目：棚卸数量は0以上にしてください。")
            continue

        lines.append((item_id, counted))

    if not lines:
        errors.append("棚卸数量が1つも入力されていません。少なくとも1つ入力してください。")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("stocktake_new_form", only_food=("1" if only_food else "0")))

    # ここ重要：棚卸時点の「理論在庫」を計算（taken_atがあればその時点まで）
    if taken_at:
        inv_rows = db.execute(
            """
            SELECT item_id, SUM(qty_delta) AS qty
            FROM inventory_tx
            WHERE location = ? AND happened_at <= ?
            GROUP BY item_id
            """,
            (location, taken_at),
        ).fetchall()
    else:
        inv_rows = db.execute(
            """
            SELECT item_id, SUM(qty_delta) AS qty
            FROM inventory_tx
            WHERE location = ?
            GROUP BY item_id
            """,
            (location,),
        ).fetchall()

    theoretical_map = {row["item_id"]: float(row["qty"] or 0) for row in inv_rows}

    try:
        # 明示BEGINは使わず、まとめてcommit/rollback
        # stocktakes（ヘッダ）
        if taken_at:
            cur = db.execute(
                """
                INSERT INTO stocktakes (taken_at, scope, location, note)
                VALUES (?, ?, ?, ?)
                """,
                (taken_at, scope, location, note),
            )
        else:
            cur = db.execute(
                """
                INSERT INTO stocktakes (taken_at, scope, location, note)
                VALUES (datetime('now'), ?, ?, ?)
                """,
                (scope, location, note),
            )

        stocktake_id = cur.lastrowid

        # lines と adjust tx
        for (item_id, counted) in lines:
            # 保存（棚卸の実測）
            db.execute(
                """
                INSERT INTO stocktake_lines (stocktake_id, item_id, counted_qty)
                VALUES (?, ?, ?)
                """,
                (stocktake_id, item_id, counted),
            )

            theoretical = theoretical_map.get(item_id, 0.0)
            delta = counted - theoretical

            # 差分が0なら tx を作らない（履歴が汚れない）
            if abs(delta) < 1e-9:
                continue

            # inventory_tx（差分調整）
            db.execute(
                """
                INSERT INTO inventory_tx (
                  happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note
                )
                VALUES (
                  COALESCE(?, datetime('now')),
                  ?, ?, 'ADJUST', ?, 'STOCKTAKE', ?, ?
                )
                """,
                (taken_at, item_id, delta, location, stocktake_id, note),
            )

        commit_and_sync()
    except Exception as e:
        db.rollback()
        flash(f"月次棚卸の登録に失敗しました: {e}", "error")
        return redirect(url_for("stocktake_new_form", only_food=("1" if only_food else "0")))

    flash("月次棚卸を登録し、差分を ADJUST で反映しました。", "success")
    return redirect(url_for("stocktake_detail", stocktake_id=stocktake_id))


@app.get("/stocktakes/<int:stocktake_id>")
def stocktake_detail(stocktake_id: int):
    db = get_db()

    header = db.execute(
        """
        SELECT stocktake_id, taken_at, scope, location, note
        FROM stocktakes
        WHERE stocktake_id = ?
        """,
        (stocktake_id,),
    ).fetchone()
    if header is None:
        abort(404)

    lines = db.execute(
        """
        SELECT
          sl.stocktake_line_id,
          i.name AS item_name,
          i.unit_base,
          i.cost_group,
          sl.counted_qty
        FROM stocktake_lines sl
        JOIN items i ON i.item_id = sl.item_id
        WHERE sl.stocktake_id = ?
        ORDER BY i.name ASC
        """,
        (stocktake_id,),
    ).fetchall()

    adjusts = db.execute(
        """
        SELECT
          itx.tx_id,
          i.name AS item_name,
          i.unit_base,
          itx.qty_delta
        FROM inventory_tx itx
        JOIN items i ON i.item_id = itx.item_id
        WHERE itx.ref_type = 'STOCKTAKE'
          AND itx.ref_id = ?
          AND itx.tx_type = 'ADJUST'
        ORDER BY i.name ASC
        """,
        (stocktake_id,),
    ).fetchall()

    return render_template(
        "stocktake_detail.html",
        header=header,
        st=header,
        lines=lines,
        adjusts=adjusts,
    )


def _get_active_batch_config_id(db):
    row = db.execute(
        """
        SELECT batch_config_id
        FROM batch_config
        WHERE is_active = 1
        ORDER BY batch_config_id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    return row["batch_config_id"]


def _get_manual_items_for_weekly(db, batch_config_id: int):
    # 手動管理＝auto_consume=0（NULLも0扱いにして手動に寄せる）
    # 理論在庫＝inventory_tx合計
    # 前回週次棚卸値（あれば）も取る
    return db.execute(
        """
        SELECT
            i.item_id,
            i.name,
            i.unit_base,
            i.reorder_point,
            COALESCE(rb.auto_consume, 0) AS auto_consume,
            COALESCE((
                SELECT SUM(tx.qty_delta)
                FROM inventory_tx tx
                WHERE tx.item_id = i.item_id
            ), 0) AS theoretical_qty,
            (
                SELECT sl.counted_qty
                FROM stocktake_lines sl
                JOIN stocktakes st ON st.stocktake_id = sl.stocktake_id
                WHERE st.scope = 'WEEKLY' AND sl.item_id = i.item_id
                ORDER BY st.taken_at DESC
                LIMIT 1
            ) AS last_weekly_qty
        FROM items i
        LEFT JOIN recipe_batch rb
          ON rb.item_id = i.item_id
         AND rb.batch_config_id = ?
        WHERE i.is_active = 1
          AND COALESCE(rb.auto_consume, 0) = 0
        ORDER BY i.name COLLATE NOCASE
        """,
        (batch_config_id,),
    ).fetchall()


@app.route("/stocktakes/weekly/new", methods=["GET", "POST"])
def stocktake_weekly_new():
    db = get_db()

    qty_rows = db.execute(
        """
        SELECT item_id, COALESCE(SUM(qty_delta), 0) AS qty
        FROM inventory_tx
        GROUP BY item_id
        """
    ).fetchall()
    current_qty = {row["item_id"]: float(row["qty"] or 0) for row in qty_rows}

    items = db.execute(
        """
        SELECT item_id, name, unit_base, reorder_point, ref_unit_price, cost_group, is_active
        FROM items
        WHERE is_active = 1
        ORDER BY name
        """
    ).fetchall()

    if request.method == "POST":
        taken_at = request.form.get("taken_at")
        if not taken_at:
            taken_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note = request.form.get("note", "").strip()

        try:
            db.execute("BEGIN")

            cur = db.execute(
                """
                INSERT INTO stocktakes (taken_at, scope, location, note)
                VALUES (?, 'WEEKLY', 'STORE', ?)
                """,
                (taken_at, note),
            )
            stocktake_id = cur.lastrowid

            eps = 1e-9
            adjusted_count = 0

            for it in items:
                item_id = it["item_id"]
                field = f"counted_{item_id}"
                if field not in request.form:
                    continue

                raw = (request.form.get(field) or "").strip()
                counted = float(raw) if raw != "" else 0.0

                before = float(current_qty.get(item_id, 0.0))
                delta = counted - before

                unit_cost = float(it["ref_unit_price"] or 0.0)
                line_amount = counted * unit_cost
                db.execute(
                    """
                    INSERT INTO stocktake_lines (
                        stocktake_id, item_id, counted_qty, unit_cost, line_amount
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (stocktake_id, item_id, counted, unit_cost, line_amount),
                )

                if abs(delta) > eps:
                    db.execute(
                        """
                        INSERT INTO inventory_tx (
                            happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note
                        )
                        VALUES (?, ?, ?, 'ADJUST', 'STORE', 'STOCKTAKE', ?, ?)
                        """,
                        (taken_at, item_id, delta, stocktake_id, "週次棚卸の差分調整"),
                    )
                    adjusted_count += 1

            db.execute("COMMIT")
            flash(
                f"週次棚卸を登録しました。差分 {adjusted_count}件 をADJUST反映しました。",
                "success",
            )
            return redirect(url_for("stocktakes_list"))

        except Exception as e:
            db.execute("ROLLBACK")
            flash(f"週次棚卸の保存に失敗しました: {e}", "error")
            return redirect(url_for("stocktake_weekly_new"))

    view_items = []
    for it in items:
        item_id = it["item_id"]
        view_items.append(
            {
                "item_id": item_id,
                "name": it["name"],
                "unit_base": it["unit_base"],
                "reorder_point": it["reorder_point"],
                "cost_group": it["cost_group"],
                "ref_unit_price": it["ref_unit_price"],
                "current_qty": float(current_qty.get(item_id, 0.0)),
            }
        )

    default_taken_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return render_template(
        "stocktake_weekly_new.html",
        items=view_items,
        default_taken_at=default_taken_at,
    )


# -----------------------------
# Stocktakes (月次: 新フォーム)
# -----------------------------
@app.get("/stocktakes/monthly/new")
def stocktake_monthly_new():
    db = get_db()

    # FOOD(38品目)だけ数える運用が基本。必要なら ?group=ALL で全表示
    group = (request.args.get("group") or "FOOD").upper()
    if group not in ("FOOD", "ALL"):
        group = "FOOD"

    # 月次棚卸は倉庫へ寄せる前提
    location = "WAREHOUSE"

    # 入力は日付だけ（デフォルト今日）
    taken_date = (request.args.get("taken_date") or date.today().isoformat()).strip()

    # 対象アイテム
    if group == "FOOD":
        items = db.execute(
            """
            SELECT item_id, name, unit_base, ref_unit_price
            FROM items
            WHERE is_active = 1 AND cost_group = 'FOOD'
            ORDER BY name ASC
            """
        ).fetchall()
    else:
        items = db.execute(
            """
            SELECT item_id, name, unit_base, ref_unit_price
            FROM items
            WHERE is_active = 1
            ORDER BY name ASC
            """
        ).fetchall()

    # 現在庫（inventory_tx の合計）
    if location == "ALL":
        cur_rows = db.execute(
            """
            SELECT item_id, COALESCE(SUM(qty_delta), 0) AS qty
            FROM inventory_tx
            GROUP BY item_id
            """
        ).fetchall()
    else:
        cur_rows = db.execute(
            """
            SELECT item_id, COALESCE(SUM(qty_delta), 0) AS qty
            FROM inventory_tx
            WHERE location = ?
            GROUP BY item_id
            """,
            (location,),
        ).fetchall()
    current_map = {r["item_id"]: float(r["qty"] or 0) for r in cur_rows}

    # 画面表示用：現在庫を埋めた行リスト
    rows = []
    for it in items:
        cur = current_map.get(it["item_id"], 0.0)
        rows.append(
            {
                "item_id": it["item_id"],
                "name": it["name"],
                "unit_base": it["unit_base"],
                "ref_unit_price": float(it["ref_unit_price"] or 0),
                "current_qty": cur,
                # 入力の初期値を「現在庫」にして、ユーザーは差分があれば直すだけ
                "counted_default": cur,
            }
        )

    return render_template(
        "stocktake_monthly_new.html",
        rows=rows,
        taken_date=taken_date,
        group=group,
    )


@app.post("/stocktakes/monthly")
def stocktake_monthly_create():
    db = get_db()

    group = (request.form.get("group") or "FOOD").upper()
    if group not in ("FOOD", "ALL"):
        group = "FOOD"

    # 月次棚卸は倉庫へ寄せる前提
    location = "WAREHOUSE"

    taken_date = (request.form.get("taken_date") or "").strip()
    if not taken_date:
        taken_date = date.today().isoformat()

    # DBには日時文字列で保存（固定時刻でOK）
    taken_at = f"{taken_date} 09:00:00"
    note = (request.form.get("note") or "").strip()

    # 対象アイテムをDBから取り直す（GET時点から在庫が変わってもOKにするため）
    if group == "FOOD":
        items = db.execute(
            """
            SELECT item_id, name, unit_base
            FROM items
            WHERE is_active = 1 AND cost_group = 'FOOD'
            ORDER BY name ASC
            """
        ).fetchall()
    else:
        items = db.execute(
            """
            SELECT item_id, name, unit_base
            FROM items
            WHERE is_active = 1
            ORDER BY name ASC
            """
        ).fetchall()

    # 現在庫（POST時点）
    if location == "ALL":
        cur_rows = db.execute(
            """
            SELECT item_id, COALESCE(SUM(qty_delta), 0) AS qty
            FROM inventory_tx
            GROUP BY item_id
            """
        ).fetchall()
    else:
        cur_rows = db.execute(
            """
            SELECT item_id, COALESCE(SUM(qty_delta), 0) AS qty
            FROM inventory_tx
            WHERE location = ?
            GROUP BY item_id
            """,
            (location,),
        ).fetchall()
    current_map = {r["item_id"]: float(r["qty"] or 0) for r in cur_rows}
    month_start, month_end = month_range_for_datetime(taken_at)

    # 初回棚卸かどうか（それ以前のMONTHLYが存在しない）
    prev_monthly = db.execute(
        """
        SELECT stocktake_id
        FROM stocktakes
        WHERE scope = 'MONTHLY'
          AND location = ?
          AND datetime(taken_at) < datetime(?)
        ORDER BY datetime(taken_at) DESC, stocktake_id DESC
        LIMIT 1
        """,
        (location, taken_at),
    ).fetchone()
    is_initial_stocktake = prev_monthly is None

    try:
        db.execute("BEGIN")

        # stocktakes を作成
        db.execute(
            """
            INSERT INTO stocktakes (taken_at, scope, location, note)
            VALUES (?, 'MONTHLY', ?, ?)
            """,
            (taken_at, location, note),
        )
        stocktake_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()[
            "id"
        ]

        # lines と ADJUST を作成
        adjust_count = 0

        for it in items:
            item_id = it["item_id"]
            unit_base = it["unit_base"]

            raw = (request.form.get(f"counted_{item_id}") or "").strip()
            if raw == "":
                # 空欄なら「現在庫のまま」にする（入力を楽に）
                counted = current_map.get(item_id, 0.0)
            else:
                try:
                    counted = float(raw)
                except ValueError:
                    counted = current_map.get(item_id, 0.0)

            # pcsは整数扱い（ゆるく丸め）
            if unit_base == "pcs":
                counted = float(int(round(counted)))

            # stocktake_lines に保存（後で在庫金額計算に使う）
            if is_initial_stocktake:
                unit_cost = calc_initial_stocktake_unit_cost(db, item_id, taken_at)
            else:
                unit_cost, _no_qty, _used_ref = calc_monthly_weighted_unit_cost(
                    db, item_id, month_start, month_end, location=location
                )
            line_amount = counted * unit_cost
            db.execute(
                """
                INSERT INTO stocktake_lines (
                  stocktake_id, item_id, counted_qty, unit_cost, line_amount
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (stocktake_id, item_id, counted, unit_cost, line_amount),
            )

            current = current_map.get(item_id, 0.0)
            delta = counted - current

            # ほぼ0は無視（履歴を綺麗に）
            if abs(delta) < 1e-9:
                continue

            db.execute(
                """
                INSERT INTO inventory_tx
                  (happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note)
                VALUES
                  (?, ?, ?, 'ADJUST', ?, 'STOCKTAKE', ?, ?)
                """,
                (
                    taken_at,
                    item_id,
                    delta,
                    location,
                    stocktake_id,
                    "MONTHLY棚卸差分（ADJUST）",
                ),
            )
            adjust_count += 1

        db.execute("COMMIT")
        flash(f"月次棚卸を登録しました（ADJUST反映: {adjust_count}件）", "success")
        return redirect(url_for("stocktake_detail", stocktake_id=stocktake_id))

    except Exception as e:
        db.execute("ROLLBACK")
        flash(f"棚卸登録に失敗しました: {e}", "error")
        return redirect(url_for("stocktake_monthly_new"))


# -----------------------------
# Transfers (移動)
# -----------------------------
@app.get("/transfers")
def transfers_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT
          t.transfer_id,
          t.moved_at,
          t.from_location,
          t.to_location,
          t.note,
          COUNT(tl.transfer_line_id) AS line_count
        FROM transfers t
        LEFT JOIN transfer_lines tl ON tl.transfer_id = t.transfer_id
        GROUP BY t.transfer_id
        ORDER BY t.moved_at DESC, t.transfer_id DESC
        """
    ).fetchall()
    return render_template("transfers_list.html", transfers=rows)


@app.get("/transfers/new")
def transfer_new_form():
    items = fetch_active_items()
    return render_template("transfer_new.html", items=items)


@app.post("/transfers")
def transfer_create():
    db = get_db()

    moved_date = (request.form.get("moved_date") or "").strip()
    if moved_date:
        moved_at = f"{moved_date} 09:00:00"
    else:
        moved_at = None

    from_location = (request.form.get("from_location") or "WAREHOUSE").strip()
    to_location = (request.form.get("to_location") or "STORE").strip()
    note = (request.form.get("note") or "").strip() or None

    if from_location not in ("STORE", "WAREHOUSE"):
        from_location = "WAREHOUSE"
    if to_location not in ("STORE", "WAREHOUSE"):
        to_location = "STORE"

    errors = []
    if from_location == to_location:
        errors.append("移動元と移動先が同じです。")

    item_ids = request.form.getlist("item_id")
    qty_list = request.form.getlist("qty")

    lines = []
    for idx, (item_id_raw, qty_raw) in enumerate(
        zip(item_ids, qty_list), start=1
    ):
        item_id_raw = (item_id_raw or "").strip()
        qty_raw = (qty_raw or "").strip()

        if item_id_raw == "" and qty_raw == "":
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

        lines.append((item_id, qty))

    if not lines:
        errors.append("明細が1行もありません。材料と数量を入力してください。")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("transfer_new_form"))

    try:
        # transfers（ヘッダ）
        if moved_at:
            cur = db.execute(
                """
                INSERT INTO transfers (moved_at, from_location, to_location, note)
                VALUES (?, ?, ?, ?)
                """,
                (moved_at, from_location, to_location, note),
            )
        else:
            cur = db.execute(
                """
                INSERT INTO transfers (from_location, to_location, note)
                VALUES (?, ?, ?)
                """,
                (from_location, to_location, note),
            )

        transfer_id = cur.lastrowid

        for (item_id, qty) in lines:
            # transfer_lines
            db.execute(
                """
                INSERT INTO transfer_lines (transfer_id, item_id, qty)
                VALUES (?, ?, ?)
                """,
                (transfer_id, item_id, qty),
            )

            happened_at = moved_at if moved_at else None

            # inventory_tx：移動元 -qty
            db.execute(
                """
                INSERT INTO inventory_tx
                  (happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note)
                VALUES
                  (COALESCE(?, datetime('now')), ?, ?, 'TRANSFER', ?, 'TRANSFER', ?, ?)
                """,
                (happened_at, item_id, -qty, from_location, transfer_id, note),
            )

            # inventory_tx：移動先 +qty
            db.execute(
                """
                INSERT INTO inventory_tx
                  (happened_at, item_id, qty_delta, tx_type, location, ref_type, ref_id, note)
                VALUES
                  (COALESCE(?, datetime('now')), ?, ?, 'TRANSFER', ?, 'TRANSFER', ?, ?)
                """,
                (happened_at, item_id, qty, to_location, transfer_id, note),
            )

        commit_and_sync()
    except Exception as e:
        db.rollback()
        flash(f"移動の登録に失敗しました: {e}", "error")
        return redirect(url_for("transfer_new_form"))

    flash("移動を登録しました（在庫履歴にも反映済み）。", "success")
    return redirect(url_for("transfer_detail", transfer_id=transfer_id))


@app.get("/transfers/<int:transfer_id>")
def transfer_detail(transfer_id: int):
    db = get_db()

    header = db.execute(
        """
        SELECT transfer_id, moved_at, from_location, to_location, note
        FROM transfers
        WHERE transfer_id = ?
        """,
        (transfer_id,),
    ).fetchone()
    if header is None:
        abort(404)

    lines = db.execute(
        """
        SELECT
          tl.transfer_line_id,
          i.name AS item_name,
          i.unit_base,
          tl.qty
        FROM transfer_lines tl
        JOIN items i ON i.item_id = tl.item_id
        WHERE tl.transfer_id = ?
        ORDER BY i.name ASC
        """,
        (transfer_id,),
    ).fetchall()

    return render_template("transfer_detail.html", header=header, lines=lines)


@app.get("/transfers/new-from-purchase/<int:purchase_id>")
def transfer_new_from_purchase(purchase_id: int):
    db = get_db()

    # 仕入れヘッダ
    p = db.execute(
        """
        SELECT purchase_id, supplier_id, purchased_at, note
        FROM purchases
        WHERE purchase_id = ?
        """,
        (purchase_id,),
    ).fetchone()
    if p is None:
        abort(404)

    # 仕入れ明細
    lines = db.execute(
        """
        SELECT pl.item_id, pl.qty, i.name, i.unit_base
        FROM purchase_lines pl
        JOIN items i ON i.item_id = pl.item_id
        WHERE pl.purchase_id = ?
        ORDER BY pl.purchase_line_id ASC
        """,
        (purchase_id,),
    ).fetchall()

    if not lines:
        flash("この仕入れには明細がありません。", "error")
        return redirect(url_for("purchases_list"))

    # この仕入れがどこに入庫されたか（inventory_txから推定）
    tx_loc = db.execute(
        """
        SELECT location
        FROM inventory_tx
        WHERE ref_type = 'PURCHASE' AND ref_id = ?
        LIMIT 1
        """,
        (purchase_id,),
    ).fetchone()

    from_location = (tx_loc["location"] if tx_loc else "WAREHOUSE")
    if from_location not in ("STORE", "WAREHOUSE"):
        from_location = "WAREHOUSE"

    # 移動先（倉庫→店舗が基本）
    to_location = "STORE" if from_location == "WAREHOUSE" else "WAREHOUSE"

    # transfer_new.html が10行固定なら最大10件まで
    prefill_lines = []
    for r in lines[:10]:
        prefill_lines.append(
            {
                "item_id": r["item_id"],
                "qty": float(r["qty"] or 0),
            }
        )

    if len(lines) > 10:
        flash("明細が10件を超えています。移動フォームには先頭10件のみ反映しました。", "error")

    suppliers = fetch_suppliers()
    items = fetch_active_items()

    default_note = f"仕入れID {purchase_id} から店舗へ補充"
    default_moved_date = str(p["purchased_at"])[:10] if p["purchased_at"] else ""

    return render_template(
        "transfer_new.html",
        suppliers=suppliers,
        items=items,
        prefill_lines=prefill_lines,
        default_from_location=from_location,
        default_to_location=to_location,
        default_moved_date=default_moved_date,
        default_note=default_note,
    )


# -----------------------------
# Shopping list (買い物リスト)
# -----------------------------
@app.get("/shopping-list")
def shopping_list():
    db = get_db()

    # 在庫集計CTE（常に合算）
    inv_cte = """
    WITH inv AS (
      SELECT item_id, SUM(qty_delta) AS qty
      FROM inventory_tx
      GROUP BY item_id
    )
    """
    inv_params = ()

    # フィルタ条件
    cond = ["i.is_active = 1"]

    where_sql = " AND ".join(cond)

    rows = db.execute(
        f"""
        {inv_cte}
        SELECT
          i.item_id,
          i.name,
          i.unit_base,
          i.reorder_point,
          i.ref_unit_price,
          i.cost_group,
          i.is_fixed,
          i.supplier_id,
          COALESCE(s.name, '（未設定）') AS supplier_name,
          COALESCE(inv.qty, 0) AS qty
        FROM items i
        LEFT JOIN inv ON inv.item_id = i.item_id
        LEFT JOIN suppliers s ON s.supplier_id = i.supplier_id
        WHERE {where_sql}
          AND COALESCE(inv.qty, 0) < COALESCE(i.reorder_point, 0)
          AND COALESCE(i.reorder_point, 0) > 0
        ORDER BY supplier_name ASC, i.name ASC
        """,
        inv_params,
    ).fetchall()

    # 仕入れ先ごとにまとめる（推奨発注量も計算）
    grouped = []
    for supplier_name, group in groupby(rows, key=lambda r: r["supplier_name"]):
        items = []
        est_sum = 0.0
        for r in group:
            reorder_point = float(r["reorder_point"] or 0)
            qty = float(r["qty"] or 0)
            shortage = max(reorder_point - qty, 0.0)
            step = 1.0 if (r["unit_base"] == "pcs") else 0.01
            order_qty = ceil_to_step(shortage, step)
            ref_price = float(r["ref_unit_price"] or 0)
            est_amount = order_qty * ref_price
            est_sum += est_amount

            items.append(
                {
                    "item_id": r["item_id"],
                    "supplier_id": r["supplier_id"],
                    "name": r["name"],
                    "unit_base": r["unit_base"],
                    "qty": qty,
                    "reorder_point": reorder_point,
                    "order_qty": order_qty,
                    "ref_unit_price": ref_price,
                    "est_amount": est_amount,
                    "cost_group": r["cost_group"],
                    "is_fixed": r["is_fixed"],
                }
            )
        grouped.append({"supplier_name": supplier_name, "items": items, "est_sum": est_sum})

    return render_template(
        "shopping_list.html",
        grouped=grouped,
    )


# -----------------------------
# Reports (月次原価)
# -----------------------------
@app.get("/reports/monthly-food-cost")
def monthly_food_cost():
    # 月選択：?ym=2026-01（なければ今月）
    ym = (request.args.get("ym") or date.today().strftime("%Y-%m")).strip()

    # 月次棚卸は倉庫に寄せる運用
    location = "WAREHOUSE"

    ideal_ratio = 0.38  # 理想38%

    month_start, month_end = month_range(ym)

    db = get_db()

    # 期首：通常は月初より前の最新MONTHLY棚卸
    begin_st = db.execute(
        """
        SELECT stocktake_id, taken_at
        FROM stocktakes
        WHERE scope = 'MONTHLY'
          AND location = ?
          AND datetime(taken_at) < datetime(?)
        ORDER BY datetime(taken_at) DESC, stocktake_id DESC
        LIMIT 1
        """,
        (location, month_start),
    ).fetchone()

    is_cutover_month = False
    if begin_st is None:
        # 運用開始月：月内の最初のMONTHLYを期首扱いにする
        begin_st = db.execute(
            """
            SELECT stocktake_id, taken_at
            FROM stocktakes
            WHERE scope = 'MONTHLY'
              AND location = ?
              AND datetime(taken_at) >= datetime(?)
              AND datetime(taken_at) < datetime(?)
            ORDER BY datetime(taken_at) ASC, stocktake_id ASC
            LIMIT 1
            """,
            (location, month_start, month_end),
        ).fetchone()
        if begin_st:
            is_cutover_month = True

    begin_value = 0.0
    begin_taken_at = None
    begin_missing = False
    if begin_st:
        begin_taken_at = begin_st["taken_at"]
        begin_value = db.execute(
            """
            SELECT COALESCE(SUM(sl.line_amount), 0) AS v
            FROM stocktake_lines sl
            JOIN items i ON i.item_id = sl.item_id
            WHERE sl.stocktake_id = ?
              AND i.cost_group = 'FOOD'
            """,
            (begin_st["stocktake_id"],),
        ).fetchone()["v"]
    else:
        begin_missing = True

    # 期末：当月内の最新MONTHLY棚卸（location指定）
    end_st = db.execute(
        """
        SELECT stocktake_id, taken_at
        FROM stocktakes
        WHERE scope = 'MONTHLY'
          AND location = ?
          AND datetime(taken_at) >= datetime(?)
          AND datetime(taken_at) < datetime(?)
        ORDER BY datetime(taken_at) DESC, stocktake_id DESC
        LIMIT 1
        """,
        (location, month_start, month_end),
    ).fetchone()

    end_value = 0.0
    end_taken_at = None
    end_missing = False
    end_lines = []
    if end_st:
        end_taken_at = end_st["taken_at"]
        end_value = db.execute(
            """
            SELECT COALESCE(SUM(sl.line_amount), 0) AS v
            FROM stocktake_lines sl
            JOIN items i ON i.item_id = sl.item_id
            WHERE sl.stocktake_id = ?
              AND i.cost_group = 'FOOD'
            """,
            (end_st["stocktake_id"],),
        ).fetchone()["v"]

        # 期末棚卸の内訳（表示用）
        end_lines = db.execute(
            """
            SELECT
              i.name,
              i.unit_base,
              sl.counted_qty,
              i.ref_unit_price,
              sl.line_amount AS amount
            FROM stocktake_lines sl
            JOIN items i ON i.item_id = sl.item_id
            WHERE sl.stocktake_id = ?
              AND i.cost_group = 'FOOD'
            ORDER BY amount DESC, i.name ASC
            """,
            (end_st["stocktake_id"],),
        ).fetchall()
    else:
        end_missing = True

    effective_start = month_start
    if is_cutover_month and begin_st:
        effective_start = begin_st["taken_at"]

    effective_end = month_end
    if end_st:
        # 期末棚卸より後は「翌月在庫」になるので、期間末を期末棚卸時点に寄せる
        effective_end = end_st["taken_at"]

    # 当月仕入金額（FOODのみ）
    # unit_price未入力はref_unit_priceで代用し、件数も取る
    purchases_row = db.execute(
        """
        SELECT
          COALESCE(SUM(
            CASE
              WHEN pl.line_amount IS NOT NULL THEN pl.line_amount
              WHEN pl.unit_price IS NOT NULL THEN pl.qty * pl.unit_price
              ELSE pl.qty * i.ref_unit_price
            END
          ), 0) AS purchase_amount,
          SUM(CASE WHEN pl.unit_price IS NULL AND pl.line_amount IS NULL THEN 1 ELSE 0 END) AS used_ref_count
        FROM purchase_lines pl
        JOIN purchases p ON p.purchase_id = pl.purchase_id
        JOIN items i ON i.item_id = pl.item_id
        WHERE i.cost_group = 'FOOD'
          AND (p.note IS NULL OR p.note NOT LIKE '%初回棚卸%')
          AND datetime(p.purchased_at) >= datetime(?)
          AND datetime(p.purchased_at) < datetime(?)
        """,
        (effective_start, effective_end),
    ).fetchone()
    purchases_cost = purchases_row["purchase_amount"]
    used_ref_count = int(purchases_row["used_ref_count"] or 0)

    # 売上（daily_reports.sales_amount の月合計）
    sales = db.execute(
        """
        SELECT COALESCE(SUM(sales_amount), 0) AS v
        FROM daily_reports
        WHERE datetime(report_date) >= datetime(?)
          AND datetime(report_date) < datetime(?)
        """,
        (effective_start, effective_end),
    ).fetchone()["v"]

    # 当月仕入の内訳（表示用）
    purchase_breakdown = db.execute(
        """
        SELECT
          i.name,
          i.unit_base,
          SUM(pl.qty) AS qty_sum,
          SUM(pl.qty * COALESCE(pl.unit_price, i.ref_unit_price)) AS amount
        FROM purchase_lines pl
        JOIN purchases p ON p.purchase_id = pl.purchase_id
        JOIN items i ON i.item_id = pl.item_id
        WHERE i.cost_group = 'FOOD'
          AND (p.note IS NULL OR p.note NOT LIKE '%初回棚卸%')
          AND datetime(p.purchased_at) >= datetime(?)
          AND datetime(p.purchased_at) < datetime(?)
        GROUP BY i.item_id
        ORDER BY amount DESC, i.name ASC
        """,
        (effective_start, effective_end),
    ).fetchall()

    # 原価計算
    cogs = float(begin_value) + float(purchases_cost) - float(end_value)

    ratio = None
    if float(sales) > 0:
        ratio = cogs / float(sales)  # 0.38など

    ideal_cogs = float(sales) * ideal_ratio
    diff_yen = cogs - ideal_cogs
    diff_pp = None if ratio is None else (ratio - ideal_ratio) * 100  # percentage points

    return render_template(
        "monthly_food_cost.html",
        ym=ym,
        start_date=month_start,
        next_date=month_end,
        location=location,
        ideal_ratio=ideal_ratio,
        sales=float(sales),
        purchases_cost=float(purchases_cost),
        used_ref_count=used_ref_count,
        begin_value=float(begin_value),
        end_value=float(end_value),
        cogs=float(cogs),
        ratio=ratio,  # None or 0.xx
        diff_yen=float(diff_yen),
        diff_pp=diff_pp,
        begin_taken_at=begin_taken_at,
        end_taken_at=end_taken_at,
        begin_missing=begin_missing,
        end_missing=end_missing,
        purchase_breakdown=purchase_breakdown,
        end_lines=end_lines,
    )


# -----------------------------
# Inventory (在庫一覧)
# -----------------------------
@app.get("/inventory")
def inventory_list():
    db = get_db()

    # 在庫残量 = inventory_tx の qty_delta を全体合算
    rows = db.execute(
        """
        WITH inv AS (
          SELECT
            item_id,
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
    note = (request.form.get("note") or "").strip() or None
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
              note = ?,
              is_fixed = ?,
              cost_group = ?,
              is_active = ?
            WHERE item_id = ?
            """,
            (supplier_id, name, unit_base, reorder_point, ref_unit_price, note, is_fixed, cost_group, is_active, item_id),
        )
        commit_and_sync()
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
        commit_and_sync()
        flash(f"材料を削除しました: {item['name']}", "success")
    except sqlite3.IntegrityError:
        # 関連データがあると削除できないので、無効化へ
        db.rollback()
        db.execute("UPDATE items SET is_active = 0 WHERE item_id = ?", (item_id,))
        commit_and_sync()
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
