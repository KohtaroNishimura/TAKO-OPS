from __future__ import annotations

import sqlite3
from pathlib import Path
from flask import Flask, g, redirect, render_template, request, url_for, flash, abort

app = Flask(__name__)
app.secret_key = "dev-secret"  # 本番は環境変数にしてください

DB_PATH = Path(__file__).with_name("takoyaki_inventory.db")


def get_db() -> sqlite3.Connection:
    """
    リクエストごとにSQLite接続を1つだけ使い回す。
    """
    if "db" not in g:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"DB file not found: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # SQLiteで外部キー制約を有効化（重要）
        conn.execute("PRAGMA foreign_keys = ON;")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exception: Exception | None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def to_int_bool(v) -> int:
    return 1 if str(v).lower() in ("1", "true", "on", "yes") else 0


@app.get("/")
def home():
    return redirect(url_for("products_index"))


# =========================
# PRODUCTS: 一覧
# =========================
@app.get("/products")
def products_index():
    db = get_db()
    show = request.args.get("show", "active")  # active / all / inactive

    where_sql = ""
    params: list = []

    if show == "active":
        where_sql = "WHERE is_active = 1"
    elif show == "inactive":
        where_sql = "WHERE is_active = 0"
    elif show == "all":
        where_sql = ""
    else:
        # 想定外パラメータはactive扱い
        where_sql = "WHERE is_active = 1"
        show = "active"

    rows = db.execute(
        f"""
        SELECT product_id, name, pieces_per_set, is_active, created_at
        FROM products
        {where_sql}
        ORDER BY product_id DESC
        """,
        params,
    ).fetchall()

    return render_template("products.html", products=rows, show=show)


# =========================
# PRODUCTS: 新規作成（フォーム表示）
# =========================
@app.get("/products/new")
def products_new():
    # 1セット=80個が基本だけど、将来変更できるように入力欄は残す
    return render_template("product_new.html", default_pieces_per_set=80)


# =========================
# PRODUCTS: 新規作成（登録）
# =========================
@app.post("/products")
def products_create():
    name = (request.form.get("name") or "").strip()
    pieces_per_set_raw = (request.form.get("pieces_per_set") or "80").strip()
    is_active = to_int_bool(request.form.get("is_active", "on"))

    if not name:
        flash("商品名を入力してください。", "error")
        return redirect(url_for("products_new"))

    try:
        pieces_per_set = int(pieces_per_set_raw)
        if pieces_per_set <= 0:
            raise ValueError
    except ValueError:
        flash("セット個数は 1 以上の整数で入力してください。", "error")
        return redirect(url_for("products_new"))

    db = get_db()

    try:
        db.execute(
            """
            INSERT INTO products (name, pieces_per_set, is_active)
            VALUES (?, ?, ?)
            """,
            (name, pieces_per_set, is_active),
        )
        db.commit()
    except sqlite3.IntegrityError as e:
        # UNIQUE(name)などに引っかかった場合
        flash("同じ商品名がすでに登録されています。別の名前にしてください。", "error")
        return redirect(url_for("products_new"))

    flash("商品を登録しました。", "success")
    return redirect(url_for("products_index"))


# =========================
# PRODUCTS: 有効/無効 切替
# =========================
@app.post("/products/<int:product_id>/toggle")
def products_toggle(product_id: int):
    db = get_db()

    row = db.execute(
        "SELECT product_id, is_active FROM products WHERE product_id = ?",
        (product_id,),
    ).fetchone()

    if row is None:
        abort(404)

    new_active = 0 if row["is_active"] == 1 else 1

    db.execute(
        "UPDATE products SET is_active = ? WHERE product_id = ?",
        (new_active, product_id),
    )
    db.commit()

    flash("ステータスを更新しました。", "success")
    # 絞り込み状態を維持して戻す
    show = request.args.get("show", "active")
    return redirect(url_for("products_index", show=show))


if __name__ == "__main__":
    app.run(debug=True)
