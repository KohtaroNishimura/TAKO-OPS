from __future__ import annotations

import os
import sqlite3
from itertools import groupby
import math
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
          COALESCE(s.name,'（未設定）') AS supplier_name,
          p.note,
          p.total_amount,
          COALESCE(itx.location, 'STORE') AS location
        FROM purchases p
        LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
        LEFT JOIN inventory_tx itx
          ON itx.ref_type = 'PURCHASE' AND itx.ref_id = p.purchase_id
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
    return redirect(url_for("purchases_list", created=purchase_id))


@app.post("/purchases/new-from-list")
def purchase_new_from_list():
    db = get_db()

    supplier_id_raw = (request.form.get("supplier_id") or "").strip()
    supplier_id = int(supplier_id_raw) if supplier_id_raw else None

    location = (request.form.get("location") or "STORE").strip()
    if location not in ("STORE", "WAREHOUSE"):
        location = "STORE"

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
        # 買い物リストに戻す（locationは保持）
        return redirect(url_for("shopping_list", location=location))

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
        default_location=location,
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

    tx_loc = db.execute(
        """
        SELECT location
        FROM inventory_tx
        WHERE ref_type = 'PURCHASE' AND ref_id = ?
        LIMIT 1
        """,
        (purchase_id,),
    ).fetchone()
    default_location = tx_loc["location"] if tx_loc else "STORE"
    if default_location not in ("STORE", "WAREHOUSE"):
        default_location = "STORE"

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
        default_location=default_location,
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

    location = (request.form.get("location") or "STORE").strip()
    if location not in ("STORE", "WAREHOUSE"):
        location = "STORE"

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
    location = request.args.get("location", "WAREHOUSE")
    if location not in ("STORE", "WAREHOUSE"):
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
        location=location,
        current_map=current_map,
    )


@app.post("/stocktakes")
def stocktake_create():
    db = get_db()

    taken_at_local = (request.form.get("taken_at") or "").strip()
    taken_at = _to_datetime_seconds(taken_at_local)  # 'YYYY-MM-DD HH:MM:00' or None
    scope = "MONTHLY"  # 今回は月次固定（必要ならフォーム化できます）
    location = (request.form.get("location") or "WAREHOUSE").strip()
    if location not in ("STORE", "WAREHOUSE"):
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
        return redirect(
            url_for("stocktake_new_form", only_food=("1" if only_food else "0"), location=location)
        )

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

        db.commit()
    except Exception as e:
        db.rollback()
        flash(f"月次棚卸の登録に失敗しました: {e}", "error")
        return redirect(
            url_for("stocktake_new_form", only_food=("1" if only_food else "0"), location=location)
        )

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
        lines=lines,
        adjusts=adjusts,
    )


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

        db.commit()
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
    default_moved_at = p["purchased_at"]  # 仕入れ日時をそのまま移動日時に

    return render_template(
        "transfer_new.html",
        suppliers=suppliers,
        items=items,
        prefill_lines=prefill_lines,
        default_from_location=from_location,
        default_to_location=to_location,
        default_moved_at=default_moved_at,
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
          AND COALESCE(inv.qty, 0) <= COALESCE(i.reorder_point, 0)
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
