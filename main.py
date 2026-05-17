import streamlit as st
import pandas as pd
import json
import os
import requests
import base64
from datetime import datetime
import plotly.express as px
from collections import defaultdict

# ── SumUp helpers ─────────────────────────────────────────────────────────────
_SUMUP_BASE = "https://api.sumup.com/v0.1"


def _sumup_headers():
    key = st.secrets.get("SUMUP_API_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _sumup_raise(r):
    """Raise with a human-readable message extracted from SumUp's error body."""
    if not r.ok:
        try:
            body = r.json()
            # SumUp returns either {message, error_code, param} or RFC-9457 {detail, title}
            msg = (
                body.get("message")
                or body.get("detail")
                or body.get("error_message")
                or r.text
            )
            param = body.get("param", "")
            code  = body.get("error_code", "")
            detail = f"{msg}"
            if param: detail += f" (field: {param})"
            if code:  detail += f" [{code}]"
        except Exception:
            detail = r.text or f"HTTP {r.status_code}"
        raise requests.HTTPError(f"SumUp {r.status_code}: {detail}", response=r)


def sumup_list_readers() -> list:
    mc = st.secrets.get("SUMUP_MERCHANT_CODE", "")
    if not mc:
        raise ValueError("SUMUP_MERCHANT_CODE missing from secrets")
    r = requests.get(f"{_SUMUP_BASE}/merchants/{mc}/readers", headers=_sumup_headers(), timeout=10)
    _sumup_raise(r)
    data = r.json()
    return data.get("items", data) if isinstance(data, dict) else data


def sumup_reader_checkout(reader_id: str, amount: float, currency: str, description: str, reference: str) -> dict:
    mc = st.secrets.get("SUMUP_MERCHANT_CODE", "")
    if not mc:
        raise ValueError("SUMUP_MERCHANT_CODE missing from secrets")
    payload = {
        "checkout_reference": reference,
        "amount": round(amount, 2),
        "currency": currency,
        "description": description,
    }
    r = requests.post(
        f"{_SUMUP_BASE}/merchants/{mc}/readers/{reader_id}/checkouts",
        json=payload, headers=_sumup_headers(), timeout=10,
    )
    _sumup_raise(r)
    return r.json()


def sumup_get_checkout(checkout_id: str) -> dict:
    r = requests.get(f"{_SUMUP_BASE}/checkouts/{checkout_id}", headers=_sumup_headers(), timeout=10)
    _sumup_raise(r)
    return r.json()


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VeeBuiltThat Stock",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Persistent storage ────────────────────────────────────────────────────────
INVENTORY_FILE = "inventory.json"
SALES_FILE = "sales.json"


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ── Session state ─────────────────────────────────────────────────────────────
if "inventory" not in st.session_state:
    st.session_state.inventory = load_json(INVENTORY_FILE, [])
if "sales" not in st.session_state:
    st.session_state.sales = load_json(SALES_FILE, [])
if "sumup_pending" not in st.session_state:
    st.session_state.sumup_pending = None
if "sumup_reader_id" not in st.session_state:
    st.session_state.sumup_reader_id = st.secrets.get("SUMUP_READER_ID", "")
if "cart" not in st.session_state:
    st.session_state.cart = []


def save_all():
    save_json(INVENTORY_FILE, st.session_state.inventory)
    save_json(SALES_FILE, st.session_state.sales)


# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'Nunito', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #1a080e 0%, #2d0d18 50%, #1f0a10 100%);
    color: #f0e6d3;
}
section[data-testid="stSidebar"] {
    background: rgba(30,5,12,0.55) !important;
    border-right: 1px solid rgba(192,164,100,0.15);
}
.card {
    background: rgba(80,20,30,0.25);
    border: 1px solid rgba(192,164,100,0.15);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
    backdrop-filter: blur(10px);
}
.card-accent  { border-left: 4px solid #c0a464; }
.card-warning { border-left: 4px solid #f59e0b; }

.metric-tile {
    background: rgba(192,164,100,0.12);
    border: 1px solid rgba(192,164,100,0.3);
    border-radius: 12px;
    padding: 18px;
    text-align: center;
}
.metric-tile .val { font-size: 2.2rem; font-weight: 800; color: #c0a464; font-family: 'Space Mono', monospace; }
.metric-tile .lbl { font-size: 0.8rem; color: rgba(240,230,211,0.6); text-transform: uppercase; letter-spacing: 1px; }

.badge-ok  { background: #1db954; color: #000; border-radius: 20px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700; }
.badge-low { background: #f59e0b; color: #000; border-radius: 20px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700; }
.badge-out { background: #8b2d3f; color: #fff; border-radius: 20px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700; }

h1, h2, h3 { color: #f0e6d3; }
.stButton > button { border-radius: 10px; font-weight: 700; font-family: 'Nunito', sans-serif; }

.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    color: #f0e6d3 !important;
    border-color: rgba(192,164,100,0.25) !important;
    border-radius: 10px !important;
}
.stDataFrame { border-radius: 12px; overflow: hidden; }
.page-title    { font-size: 2rem; font-weight: 800; color: #f0e6d3; margin-bottom: 0.2rem; }
.page-subtitle { color: rgba(240,230,211,0.55); font-size: 0.9rem; margin-bottom: 1.5rem; }
.badge-cat { background: rgba(192,164,100,0.15); border: 1px solid rgba(192,164,100,0.4); color: #c0a464; border-radius: 20px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700; }

/* ── Button styles ── */
.stButton > button {
    transition: all 0.18s ease;
    border: 1px solid rgba(192,164,100,0.3);
    background: rgba(192,164,100,0.1);
    color: #f0e6d3;
}
.stButton > button:hover {
    background: rgba(192,164,100,0.22) !important;
    border-color: rgba(192,164,100,0.6) !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(192,164,100,0.15);
    color: #f0e6d3 !important;
}
.stButton > button:active { transform: translateY(0); }

/* Primary CTA buttons (checkout, add to cart, add product) */
button[kind="primary"], .stButton > button[data-testid*="checkout"],
.stButton > button[data-testid*="cart"], .stButton > button[data-testid*="add"] {
    background: linear-gradient(135deg, #c0a464 0%, #a8894a 100%) !important;
    color: #1a080e !important;
    border: none !important;
    font-weight: 800 !important;
}

/* ── Card transitions ── */
.card {
    transition: box-shadow 0.18s ease, transform 0.18s ease;
    box-shadow: 0 2px 12px rgba(0,0,0,0.3);
}
.card:hover { box-shadow: 0 6px 24px rgba(0,0,0,0.45); }

/* ── Sidebar stat tiles ── */
.stat-tile {
    background: rgba(192,164,100,0.08);
    border: 1px solid rgba(192,164,100,0.2);
    border-radius: 10px;
    padding: 8px 12px;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.9rem;
}
.stat-tile .stat-val { font-weight: 800; color: #c0a464; font-family: 'Space Mono', monospace; font-size: 0.95rem; }
.stat-tile .stat-lbl { color: rgba(240,230,211,0.65); }

/* ── Status badge in sidebar ── */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.8rem;
    font-weight: 700;
    margin-top: 4px;
}

/* ── Cart item rows ── */
.cart-row {
    background: rgba(80,20,30,0.2);
    border: 1px solid rgba(192,164,100,0.12);
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 6px;
    transition: background 0.15s ease;
}
.cart-row:hover { background: rgba(80,20,30,0.35); }

/* ── Filter toolbar ── */
.filter-bar {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(192,164,100,0.15);
    border-radius: 14px;
    padding: 14px 18px;
    margin-bottom: 16px;
}

/* ── Alert/info styling ── */
.stAlert > div {
    border-radius: 12px !important;
    border-left-width: 4px !important;
}

/* ── Dataframe styling ── */
.stDataFrame > div {
    border-radius: 12px;
    border: 1px solid rgba(192,164,100,0.15);
    overflow: hidden;
}

/* ── Selectbox / input focus ── */
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: rgba(192,164,100,0.6) !important;
    box-shadow: 0 0 0 2px rgba(192,164,100,0.15) !important;
}

/* ── Expander polish ── */
.streamlit-expanderHeader {
    background: rgba(192,164,100,0.08) !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
}
.streamlit-expanderHeader:hover {
    background: rgba(192,164,100,0.15) !important;
}

/* ── Section divider ── */
.section-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(192,164,100,0.3), transparent);
    margin: 20px 0;
    border: none;
}

/* ── Nav radio pills ── */
section[data-testid="stSidebar"] .stRadio > label > div:first-child { display: none; }
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
    display: flex;
    flex-direction: column;
    gap: 4px;
}
section[data-testid="stSidebar"] .stRadio label {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(192,164,100,0.12);
    border-radius: 10px;
    padding: 10px 16px;
    cursor: pointer;
    transition: all 0.15s ease;
    font-weight: 600;
    width: 100%;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(192,164,100,0.12);
    border-color: rgba(192,164,100,0.35);
}
section[data-testid="stSidebar"] .stRadio label[data-checked="true"],
section[data-testid="stSidebar"] .stRadio label:has(input:checked) {
    background: rgba(192,164,100,0.18);
    border-color: rgba(192,164,100,0.5);
    color: #c0a464;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
# NOTE: radio labels are plain strings — the if/elif checks below must match exactly.
with st.sidebar:
    st.image("assets/pfp_vee.png", use_container_width=True)
    st.markdown(
        "<div style='text-align:center;font-weight:800;font-size:1.05rem;"
        "margin-top:6px;margin-bottom:0;'>🎨 VeeBuiltThat Stock</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    page = st.radio(
        "Navigate",
        ["Inventory", "Sales / POS", "Analytics"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    inv           = st.session_state.inventory
    total_items   = len(inv)
    in_stock_cnt  = sum(1 for p in inv if p["stock"] > 0)
    out_of_stock  = sum(1 for p in inv if p["stock"] == 0)
    total_revenue = sum(s["total"] for s in st.session_state.sales)
    st.markdown(
        f'<div class="stat-tile"><span class="stat-lbl">📦 Products</span><span class="stat-val">{total_items}</span></div>'
        f'<div class="stat-tile"><span class="stat-lbl">✅ In stock</span><span class="stat-val">{in_stock_cnt}</span></div>'
        f'<div class="stat-tile"><span class="stat-lbl">❌ Out of stock</span><span class="stat-val">{out_of_stock}</span></div>'
        f'<div class="stat-tile"><span class="stat-lbl">💰 Revenue</span><span class="stat-val">€{total_revenue:.2f}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    has_key  = bool(st.secrets.get("SUMUP_API_KEY", ""))
    has_code = bool(st.secrets.get("SUMUP_MERCHANT_CODE", ""))
    has_reader = bool(st.session_state.sumup_reader_id)
    if has_key and has_code and has_reader:
        st.markdown('<div class="status-badge">🟢 SumUp ready</div>', unsafe_allow_html=True)
    elif has_key and has_code and not has_reader:
        st.markdown('<div class="status-badge">🟡 No reader selected</div>', unsafe_allow_html=True)
        if st.button("🔍 Find my reader", use_container_width=True):
            try:
                readers = sumup_list_readers()
                if not readers:
                    st.warning("No readers found on this account.")
                elif len(readers) == 1:
                    st.session_state.sumup_reader_id = readers[0]["id"]
                    st.success(f"Reader found: {readers[0].get('name', readers[0]['id'])}")
                    st.rerun()
                else:
                    st.session_state["_reader_options"] = readers
            except Exception as _e:
                st.error(f"Could not list readers: {_e}")
        # Let user pick if multiple readers were found
        if st.session_state.get("_reader_options"):
            _opts = st.session_state["_reader_options"]
            _labels = [f"{r.get('name', 'Reader')} ({r['id']})" for r in _opts]
            _pick = st.selectbox("Select reader", _labels, key="reader_pick_box")
            if st.button("Use this reader", use_container_width=True):
                _idx = _labels.index(_pick)
                st.session_state.sumup_reader_id = _opts[_idx]["id"]
                del st.session_state["_reader_options"]
                st.rerun()
    elif has_key and not has_code:
        st.markdown('<div class="status-badge">🟡 Missing merchant code</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-badge">🔴 SumUp not configured</div>', unsafe_allow_html=True)


# ── Banner ───────────────────────────────────────────────────────────────────
st.image("assets/banner_vee.png", use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — INVENTORY
# ══════════════════════════════════════════════════════════════════════════════
if page == "Inventory":
    st.markdown('<div class="page-title">📦 Inventory</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Manage products, stock levels, and prices</div>', unsafe_allow_html=True)

    with st.expander("➕ Add New Product", expanded=False):
        with st.form("add_product_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([3, 1, 1, 2])
            new_name  = c1.text_input("Product name", placeholder="e.g. Sticker Pack — Cats")
            new_price = c2.number_input("Price (€)", min_value=0.0, step=0.5, format="%.2f")
            new_stock = c3.number_input("Stock qty", min_value=0, step=1)
            new_cat   = c4.selectbox("Category", ["Stickers", "Print A4", "Print A5", "Print A6", "Charms", "Keychains", "Badges", "Cards", "Bookmarks", "Magnets", "Other"])
            new_img_file = st.file_uploader("Product image (optional)", type=["png", "jpg", "jpeg", "webp"], key="new_product_img")
            if st.form_submit_button("Add Product", use_container_width=True):
                if not new_name.strip():
                    st.error("Product name is required.")
                else:
                    new_product = {
                        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                        "name": new_name.strip(),
                        "price": new_price,
                        "stock": new_stock,
                        "category": new_cat,
                    }
                    if new_img_file:
                        new_product["image"] = base64.b64encode(new_img_file.read()).decode()
                    st.session_state.inventory.append(new_product)
                    save_all()
                    st.success(f"✅ '{new_name}' added!")
                    st.rerun()

    st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
    f1, f2, f3 = st.columns([3, 1, 1])
    search_q      = f1.text_input("🔍 Search products", placeholder="Type a name...")
    filter_status = f2.selectbox("Status", ["All", "In Stock", "Low Stock (≤3)", "Out of Stock"])
    all_cats      = sorted(set(p.get("category", "Other") for p in st.session_state.inventory))
    filter_cat    = f3.selectbox("Category", ["All"] + all_cats)
    st.markdown('</div>', unsafe_allow_html=True)

    inv       = st.session_state.inventory
    displayed = [p for p in inv if search_q.lower() in p["name"].lower()]
    if filter_status == "In Stock":
        displayed = [p for p in displayed if p["stock"] > 3]
    elif filter_status == "Low Stock (≤3)":
        displayed = [p for p in displayed if 0 < p["stock"] <= 3]
    elif filter_status == "Out of Stock":
        displayed = [p for p in displayed if p["stock"] == 0]
    if filter_cat != "All":
        displayed = [p for p in displayed if p.get("category", "Other") == filter_cat]

    cat_totals = defaultdict(int)
    for p in inv:
        cat_totals[p.get("category", "Other")] += p["stock"]
    if cat_totals:
        summary_cols = st.columns(len(cat_totals))
        for i, (cat, total) in enumerate(sorted(cat_totals.items())):
            summary_cols[i].markdown(
                f'<div style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);'
                f'border-radius:10px;padding:10px;text-align:center;margin-bottom:8px;">'
                f'<div style="font-size:1.3rem;font-weight:800;color:#c0a464;">{total}</div>'
                f'<div style="font-size:0.75rem;color:rgba(255,255,255,0.55);text-transform:uppercase;'
                f'letter-spacing:1px;">{cat}</div></div>',
                unsafe_allow_html=True,
            )

    # ── Export buttons ────────────────────────────────────────────────────────
    ex1, ex2, ex3 = st.columns([2, 2, 4])

    # Export ALL products (ignores current filter)
    if inv:
        all_csv = pd.DataFrame([{
            "Name": p["name"], "Category": p.get("category", "Other"),
            "Price (€)": p["price"], "Stock": p["stock"],
            "Status": "Out of Stock" if p["stock"] == 0 else ("Low Stock" if p["stock"] <= 3 else "In Stock"),
        } for p in inv]).to_csv(index=False).encode("utf-8")
        ex1.download_button(
            "⬇️ Export All Products",
            data=all_csv,
            file_name=f"inventory_all_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Export currently filtered view
    if displayed:
        filtered_csv = pd.DataFrame([{
            "Name": p["name"], "Category": p.get("category", "Other"),
            "Price (€)": p["price"], "Stock": p["stock"],
            "Status": "Out of Stock" if p["stock"] == 0 else ("Low Stock" if p["stock"] <= 3 else "In Stock"),
        } for p in displayed]).to_csv(index=False).encode("utf-8")
        ex2.download_button(
            "⬇️ Export Filtered View",
            data=filtered_csv,
            file_name=f"inventory_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown(f"**{len(displayed)} product(s)**")

    if not displayed:
        st.info("No products found. Add one above!")
    else:
        for product in displayed:
            st.markdown('<div class="card card-accent">', unsafe_allow_html=True)
            col_img, col_name, col_cat, col_price, col_stock, col_actions = st.columns([1, 2.5, 1.5, 1, 1.5, 3])
            if product.get("image"):
                col_img.image(base64.b64decode(product["image"]), use_container_width=True)
            else:
                col_img.markdown(
                    '<div style="background:rgba(255,255,255,0.05);border-radius:8px;'
                    'text-align:center;padding:10px;font-size:1.4rem;">🖼️</div>',
                    unsafe_allow_html=True,
                )

            if product["stock"] == 0:
                badge = '<span class="badge-out">Out of Stock</span>'
            elif product["stock"] <= 3:
                badge = '<span class="badge-low">Low Stock</span>'
            else:
                badge = '<span class="badge-ok">In Stock</span>'

            col_name.markdown(f"**{product['name']}**<br>{badge}", unsafe_allow_html=True)
            col_cat.markdown(f"<small style='color:rgba(255,255,255,0.5)'>Category</small><br>{product['category']}", unsafe_allow_html=True)
            col_price.markdown(f"<small style='color:rgba(255,255,255,0.5)'>Price</small><br>**€{product['price']:.2f}**", unsafe_allow_html=True)
            col_stock.markdown(f"<small style='color:rgba(255,255,255,0.5)'>Stock</small><br>**{product['stock']}**", unsafe_allow_html=True)

            pid = product["id"]
            with col_actions:
                a1, a2, a3, a4 = st.columns(4)
                if a1.button("➕", key=f"inc_{pid}", help="Add 1"):
                    product["stock"] += 1; save_all(); st.rerun()
                if a2.button("➖", key=f"dec_{pid}", help="Remove 1", disabled=product["stock"] == 0):
                    product["stock"] = max(0, product["stock"] - 1); save_all(); st.rerun()
                if a3.button("🚫", key=f"out_{pid}", help="Mark Out of Stock"):
                    product["stock"] = 0; save_all(); st.rerun()
                if a4.button("🗑️", key=f"del_{pid}", help="Delete product"):
                    st.session_state.inventory = [p for p in st.session_state.inventory if p["id"] != pid]
                    save_all(); st.rerun()

            with st.expander(f"✏️ Edit / Restock — {product['name']}"):
                ec1, ec2, ec3 = st.columns(3)
                new_q = ec1.number_input("Set stock to", min_value=0, value=product["stock"], key=f"restock_{pid}")
                new_p = ec2.number_input("Set price (€)", min_value=0.0, value=product["price"], step=0.5, format="%.2f", key=f"price_{pid}")
                new_img = st.file_uploader("Update product image", type=["png", "jpg", "jpeg", "webp"], key=f"img_{pid}")
                if ec3.button("Apply", key=f"apply_{pid}"):
                    product["stock"] = new_q
                    product["price"] = new_p
                    if new_img:
                        product["image"] = base64.b64encode(new_img.read()).decode()
                    save_all()
                    st.success("Updated!"); st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — SALES / POS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Sales / POS":   # matches the radio label exactly
    st.markdown('<div class="page-title">🛒 Sales & POS</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Record sales, track payment method, and see per-product totals</div>', unsafe_allow_html=True)

    inv = st.session_state.inventory
    in_stock_products = [p for p in inv if p["stock"] > 0]

    # ── SumUp pending banner — auto-polls every 3 s ───────────────────────────
    if st.session_state.sumup_pending:
        import time
        _pend     = st.session_state.sumup_pending
        total_due = _pend["total"]

        # ── auto-poll: silently check status, resolve if done ─────────────────
        _auto_error = None
        try:
            _data   = sumup_get_checkout(_pend["checkout_id"])
            _status = _data.get("status", "UNKNOWN").upper()
        except Exception as _e:
            _data   = {}
            _status = "UNKNOWN"
            _auto_error = str(_e)

        if _status == "PAID":
            _now    = datetime.now()
            _bid    = _now.strftime("%Y%m%d%H%M%S%f")
            for _idx, _item in enumerate(_pend["cart"]):
                for _prod in st.session_state.inventory:
                    if _prod["id"] == _item["product_id"]:
                        _prod["stock"] = max(0, _prod["stock"] - _item["qty"])
                        break
                st.session_state.sales.append({
                    "id":                f"{_bid}_{_idx:02d}",
                    "timestamp":         _now.isoformat(),
                    "product_id":        _item["product_id"],
                    "product_name":      _item["product_name"],
                    "category":          _item["category"],
                    "qty":               _item["qty"],
                    "unit_price":        _item["unit_price"],
                    "total":             _item["unit_price"] * _item["qty"],
                    "payment":           _pend["payment"],
                    "sumup_checkout_id": _pend["checkout_id"],
                })
            save_all()
            _n = len(_pend["cart"])
            st.session_state.sumup_pending = None
            st.success(f"✅ Payment confirmed! {_n} item(s) · €{total_due:.2f}")
            st.rerun()

        elif _status in ("FAILED", "EXPIRED"):
            st.session_state.sumup_pending = None
            st.error(f"💳 Payment {_status}. Please try again.")
            st.rerun()

        else:
            # Still pending — show animated banner + progress bar, then rerun
            dot_cycle = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            tick = int(time.time()) % len(dot_cycle)
            spinner = dot_cycle[tick]
            _item_summary = ", ".join(f'{i["qty"]}× {i["product_name"]}' for i in _pend["cart"])

            st.markdown(
                f'<div class="card card-warning">'
                f'<b>{spinner} Waiting for card payment on reader</b> &nbsp;·&nbsp; '
                f'{_item_summary} &nbsp;·&nbsp; <b>€{total_due:.2f}</b><br>'
                f'<small style="color:rgba(255,255,255,0.55);">'
                f'👆 Tap or insert card on the SumUp reader &nbsp;·&nbsp; Status: <b>{_status}</b>'
                f'{"&nbsp;·&nbsp; ⚠️ " + _auto_error if _auto_error else ""}'
                f'</small></div>',
                unsafe_allow_html=True,
            )

            # Progress bar counts down the 3-second wait visually
            progress = st.progress(0, text="Next check in 3 s…")
            for i in range(30):
                time.sleep(0.1)
                progress.progress(i + 1, text=f"Next check in {3 - (i + 1) // 10:.0f} s…")
            progress.empty()

            # Manual cancel still available
            if st.button("❌ Cancel Payment", use_container_width=False):
                st.session_state.sumup_pending = None
                st.rerun()

            st.rerun()  # triggers the next poll cycle

        st.markdown("---")

    # ── Cart Builder ──────────────────────────────────────────────────────────
    st.subheader("🛍️ Add to Cart")
    if st.session_state.sumup_pending:
        st.info("Complete or cancel the pending card payment first.")
    elif not in_stock_products:
        st.warning("No products in stock. Add stock in the Inventory page first.")
    else:
        _sale_map    = {p["name"]: p for p in in_stock_products}
        ac1, ac2, ac3 = st.columns([3, 1, 1.5])
        _chosen_name  = ac1.selectbox(
            "Product",
            list(_sale_map.keys()),
            key="sale_product_preview",
            format_func=lambda n: f"{n}  #{_sale_map[n].get('category', 'Other')}",
        )
        _add_qty = ac2.number_input("Qty", min_value=1, step=1, value=1, key="cart_add_qty")
        _preview = _sale_map[_chosen_name]
        _prev_img_col, _prev_info_col = st.columns([1, 6])
        if _preview.get("image"):
            _prev_img_col.image(base64.b64decode(_preview["image"]), width=80)
        _prev_info_col.markdown(
            f'<span class="badge-cat">#{_preview.get("category", "Other")}</span>'
            f' &nbsp; <b>€{_preview["price"]:.2f}</b> each &nbsp;·&nbsp; {_preview["stock"]} in stock',
            unsafe_allow_html=True,
        )
        if ac3.button("➕ Add to Cart", use_container_width=True, key="btn_add_cart"):
            _in_cart = sum(i["qty"] for i in st.session_state.cart if i["product_id"] == _preview["id"])
            if _add_qty + _in_cart > _preview["stock"]:
                st.error(f"Only {_preview['stock']} in stock ({_in_cart} already in cart).")
            else:
                for _ci in st.session_state.cart:
                    if _ci["product_id"] == _preview["id"]:
                        _ci["qty"] += _add_qty
                        break
                else:
                    st.session_state.cart.append({
                        "product_id":   _preview["id"],
                        "product_name": _preview["name"],
                        "category":     _preview.get("category", "Other"),
                        "qty":          _add_qty,
                        "unit_price":   _preview["price"],
                    })
                st.rerun()

    st.markdown("---")
    # ── Cart display + Checkout ───────────────────────────────────────────────
    if st.session_state.cart:
        st.subheader("🛒 Cart")
        _cart_total = 0.0
        for _ci_idx, _ci in enumerate(st.session_state.cart):
            _line        = _ci["unit_price"] * _ci["qty"]
            _cart_total += _line
            st.markdown('<div class="cart-row">', unsafe_allow_html=True)
            cc1, cc2, cc3, cc4 = st.columns([3.5, 1, 1.5, 0.7])
            cc1.markdown(
                f'**{_ci["product_name"]}** &nbsp; <span class="badge-cat">#{_ci["category"]}</span>',
                unsafe_allow_html=True,
            )
            cc2.markdown(f'<span style="color:rgba(240,230,211,0.65);">×{_ci["qty"]}</span>', unsafe_allow_html=True)
            cc3.markdown(f'<span style="font-weight:800;color:#c0a464;">€{_line:.2f}</span>', unsafe_allow_html=True)
            if cc4.button("🗑️", key=f"rm_cart_{_ci_idx}", help="Remove"):
                st.session_state.cart.pop(_ci_idx)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="card card-accent" style="text-align:right;padding:18px 24px;margin-top:8px;">'
            f'<div style="font-size:0.8rem;color:rgba(240,230,211,0.55);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">{len(st.session_state.cart)} item(s)</div>'
            f'<span style="font-size:1.7rem;font-weight:800;color:#c0a464;">Total: €{_cart_total:.2f}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        pay_col, clear_col, checkout_col = st.columns([2, 1.5, 2])
        _payment = pay_col.selectbox("Payment method", ["💳 Card", "💵 Cash"], key="checkout_payment")
        if clear_col.button("🗑️ Clear Cart", use_container_width=True, key="btn_clear_cart"):
            st.session_state.cart = []
            st.rerun()
        if not st.session_state.sumup_pending:
            if checkout_col.button("✅ Checkout", use_container_width=True, key="btn_checkout"):
                if "Card" in _payment:
                    if not st.secrets.get("SUMUP_API_KEY", "") or not st.secrets.get("SUMUP_MERCHANT_CODE", ""):
                        st.error("SumUp not fully configured.")
                    elif not st.session_state.sumup_reader_id:
                        st.error("No card reader selected. Use '🔍 Find my reader' in the sidebar first.")
                    else:
                        _ref    = f"AA-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                        _nitems = sum(i["qty"] for i in st.session_state.cart)
                        _desc   = (f"{_nitems} items" if len(st.session_state.cart) > 1
                                   else f"{st.session_state.cart[0]['qty']}× {st.session_state.cart[0]['product_name']}")
                        try:
                            _co = sumup_reader_checkout(
                                st.session_state.sumup_reader_id,
                                _cart_total, "EUR", _desc, _ref,
                            )
                            st.session_state.sumup_pending = {
                                "checkout_id": _co["id"],
                                "cart":        [dict(i) for i in st.session_state.cart],
                                "payment":     _payment,
                                "total":       _cart_total,
                            }
                            st.session_state.cart = []
                            st.rerun()
                        except Exception as _e:
                            st.error(f"SumUp error: {_e}")
                else:
                    _now = datetime.now()
                    _bid = _now.strftime("%Y%m%d%H%M%S%f")
                    for _ci_idx, _ci in enumerate(st.session_state.cart):
                        for _p in st.session_state.inventory:
                            if _p["id"] == _ci["product_id"]:
                                _p["stock"] = max(0, _p["stock"] - _ci["qty"])
                                break
                        st.session_state.sales.append({
                            "id":           f"{_bid}_{_ci_idx:02d}",
                            "timestamp":    _now.isoformat(),
                            "product_id":   _ci["product_id"],
                            "product_name": _ci["product_name"],
                            "category":     _ci["category"],
                            "qty":          _ci["qty"],
                            "unit_price":   _ci["unit_price"],
                            "total":        _ci["unit_price"] * _ci["qty"],
                            "payment":      _payment,
                        })
                    save_all()
                    _total_paid = _cart_total
                    st.session_state.cart = []
                    st.success(f"💵 Sale recorded! Total: €{_total_paid:.2f}")
                    st.rerun()
    else:
        st.info("Cart is empty — add products above.")

    st.markdown("---")
    st.subheader("📋 Sales Log")

    sales = st.session_state.sales
    if not sales:
        st.info("No sales recorded yet.")
    else:
        product_totals = defaultdict(lambda: {"qty": 0, "revenue": 0.0, "card": 0, "cash": 0})
        for s in sales:
            k = s["product_name"]
            product_totals[k]["qty"]     += s["qty"]
            product_totals[k]["revenue"] += s["total"]
            if "Card" in s["payment"]:
                product_totals[k]["card"] += s["qty"]
            else:
                product_totals[k]["cash"] += s["qty"]

        rows = [
            {"Product": name, "Units Sold": d["qty"], "Revenue (€)": round(d["revenue"], 2),
             "Via Card": d["card"], "Via Cash": d["cash"]}
            for name, d in sorted(product_totals.items(), key=lambda x: -x[1]["revenue"])
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("#### Recent transactions")
        recent = sorted(sales, key=lambda x: x["timestamp"], reverse=True)[:50]
        df_log = pd.DataFrame([{
            "Time":    s["timestamp"][:19].replace("T", " "),
            "Product": s["product_name"],
            "Qty":     s["qty"],
            "Unit €":  s["unit_price"],
            "Total €": s["total"],
            "Payment": s["payment"],
        } for s in recent])
        st.dataframe(df_log, use_container_width=True, hide_index=True)

        # Export full sales log
        sales_csv = pd.DataFrame([{
            "Time": s["timestamp"][:19].replace("T", " "),
            "Product": s["product_name"],
            "Category": s.get("category", ""),
            "Qty": s["qty"],
            "Unit (€)": s["unit_price"],
            "Total (€)": s["total"],
            "Payment": s["payment"],
        } for s in sorted(sales, key=lambda x: x["timestamp"], reverse=True)]).to_csv(index=False).encode("utf-8")
        sc1, sc2 = st.columns([2, 4])
        sc1.download_button(
            "⬇️ Export Sales Log",
            data=sales_csv,
            file_name=f"sales_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        if sc2.button("↩️ Undo Last Sale"):
            last = st.session_state.sales.pop()
            for p in st.session_state.inventory:
                if p["id"] == last["product_id"]:
                    p["stock"] += last["qty"]
                    break
            save_all()
            st.success(f"Undone: {last['product_name']}")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Analytics":   # matches the radio label exactly
    st.markdown('<div class="page-title">📊 Analytics</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Sales performance, best sellers, and payment breakdown</div>', unsafe_allow_html=True)

    sales = st.session_state.sales
    if not sales:
        st.info("No sales data yet. Start recording sales in the POS page!")
    else:
        df = pd.DataFrame(sales)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"]      = df["timestamp"].dt.date

        total_rev   = df["total"].sum()
        total_units = df["qty"].sum()
        num_tx      = len(df)
        card_rev    = df[df["payment"].str.contains("Card")]["total"].sum()
        cash_rev    = df[df["payment"].str.contains("Cash")]["total"].sum()
        best_prod   = df.groupby("product_name")["qty"].sum().idxmax()

        k1, k2, k3, k4, k5, k6 = st.columns(6)

        def kpi(col, val, label):
            col.markdown(
                f'<div class="metric-tile"><div class="val">{val}</div>'
                f'<div class="lbl">{label}</div></div>',
                unsafe_allow_html=True,
            )

        kpi(k1, f"€{total_rev:.0f}", "Total Revenue")
        kpi(k2, total_units, "Units Sold")
        kpi(k3, num_tx, "Transactions")
        kpi(k4, f"€{card_rev:.0f}", "Card Revenue")
        kpi(k5, f"€{cash_rev:.0f}", "Cash Revenue")
        # best_prod now shown instead of being discarded
        k6.markdown(
            f'<div class="metric-tile"><div class="val" style="font-size:0.95rem;padding-top:8px;">'
            f'{best_prod}</div><div class="lbl">Best Seller</div></div>',
            unsafe_allow_html=True,
        )

        st.markdown("")
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### 🏆 Best Sellers (by units)")
            by_prod = df.groupby("product_name")["qty"].sum().sort_values(ascending=False).reset_index()
            by_prod.columns = ["Product", "Units"]
            fig = px.bar(by_prod, x="Units", y="Product", orientation="h",
                         color="Units", color_continuous_scale=["#3f111f", "#c0a464"],
                         template="plotly_dark")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              coloraxis_showscale=False, margin=dict(l=0, r=0, t=10, b=0),
                              yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("#### 💰 Revenue by Product")
            by_rev = df.groupby("product_name")["total"].sum().sort_values(ascending=False).reset_index()
            by_rev.columns = ["Product", "Revenue"]
            fig2 = px.pie(by_rev, values="Revenue", names="Product",
                          color_discrete_sequence=["#c0a464","#8b2d3f","#a8894a","#6b1e2e","#d4bc7a","#4a1520","#e8d4a0"],
                          template="plotly_dark", hole=0.4)
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                               legend=dict(font=dict(color="#fff")),
                               margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### 📅 Revenue Over Time")
        by_date = df.groupby("date")["total"].sum().reset_index()
        by_date.columns = ["Date", "Revenue"]
        fig3 = px.area(by_date, x="Date", y="Revenue",
                       template="plotly_dark", color_discrete_sequence=["#c0a464"])
        fig3.update_traces(fillcolor="rgba(192,164,100,0.2)")
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig3, use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("#### 💳 Payment Method Breakdown")
            pay_df = df.groupby("payment").agg(Units=("qty", "sum"), Revenue=("total", "sum")).reset_index()
            fig4 = px.bar(pay_df, x="payment", y=["Units", "Revenue"], barmode="group",
                          template="plotly_dark", color_discrete_sequence=["#c0a464", "#8b2d3f"])
            fig4.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               margin=dict(l=0, r=0, t=10, b=0),
                               legend=dict(font=dict(color="#fff")))
            st.plotly_chart(fig4, use_container_width=True)

        with c4:
            st.markdown("#### 📂 Revenue by Category")
            cat_df = df.groupby("category")["total"].sum().sort_values(ascending=False).reset_index()
            cat_df.columns = ["Category", "Revenue"]
            fig5 = px.bar(cat_df, x="Category", y="Revenue",
                          template="plotly_dark", color="Revenue",
                          color_continuous_scale=["#3f111f", "#c0a464"])
            fig5.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               coloraxis_showscale=False, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig5, use_container_width=True)