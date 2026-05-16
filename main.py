import streamlit as st
import pandas as pd
import json
import os
import requests
from datetime import datetime
import plotly.express as px
from collections import defaultdict

# ── SumUp helpers ─────────────────────────────────────────────────────────────
_SUMUP_BASE = "https://api.sumup.com/v0.1"


def _sumup_headers():
    key = st.secrets.get("SUMUP_API_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def sumup_create_checkout(amount: float, currency: str, description: str, reference: str) -> dict:
    payload = {
        "checkout_reference": reference,
        "amount": round(amount, 2),
        "currency": currency,
        "description": description,
    }
    r = requests.post(f"{_SUMUP_BASE}/checkouts", json=payload, headers=_sumup_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def sumup_get_checkout(checkout_id: str) -> dict:
    r = requests.get(f"{_SUMUP_BASE}/checkouts/{checkout_id}", headers=_sumup_headers(), timeout=10)
    r.raise_for_status()
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


def save_all():
    save_json(INVENTORY_FILE, st.session_state.inventory)
    save_json(SALES_FILE, st.session_state.sales)


# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'Nunito', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #e0e0f0;
}
section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.05) !important;
    border-right: 1px solid rgba(255,255,255,0.1);
}
.card {
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
    backdrop-filter: blur(10px);
}
.card-accent  { border-left: 4px solid #e94560; }
.card-warning { border-left: 4px solid #f59e0b; }

.metric-tile {
    background: rgba(233,69,96,0.15);
    border: 1px solid rgba(233,69,96,0.3);
    border-radius: 12px;
    padding: 18px;
    text-align: center;
}
.metric-tile .val { font-size: 2.2rem; font-weight: 800; color: #e94560; font-family: 'Space Mono', monospace; }
.metric-tile .lbl { font-size: 0.8rem; color: rgba(255,255,255,0.6); text-transform: uppercase; letter-spacing: 1px; }

.badge-ok  { background: #1db954; color: #000; border-radius: 20px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700; }
.badge-low { background: #f59e0b; color: #000; border-radius: 20px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700; }
.badge-out { background: #e94560; color: #fff; border-radius: 20px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700; }

h1, h2, h3 { color: #ffffff; }
.stButton > button { border-radius: 10px; font-weight: 700; font-family: 'Nunito', sans-serif; }

.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    color: #fff !important;
    border-color: rgba(255,255,255,0.2) !important;
    border-radius: 10px !important;
}
.stDataFrame { border-radius: 12px; overflow: hidden; }
.page-title    { font-size: 2rem; font-weight: 800; color: #fff; margin-bottom: 0.2rem; }
.page-subtitle { color: rgba(255,255,255,0.5); font-size: 0.9rem; margin-bottom: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
# NOTE: radio labels are plain strings — the if/elif checks below must match exactly.
with st.sidebar:
    st.markdown("## 🎨 VeeBuiltThat Stock")
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
    st.markdown(f"**Products:** {total_items}")
    st.markdown(f"✅ In stock: {in_stock_cnt}")
    st.markdown(f"❌ Out of stock: {out_of_stock}")
    st.markdown(f"💰 Revenue: **€{total_revenue:.2f}**")
    st.markdown("---")
    has_key = bool(st.secrets.get("SUMUP_API_KEY", ""))
    st.markdown(f"**SumUp:** {'🟢 configured' if has_key else '🔴 no API key'}")


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
            new_cat   = c4.selectbox("Category", ["Stickers", "Prints", "Charms", "Keychains", "Badges", "Cards", "Other"])
            if st.form_submit_button("Add Product", use_container_width=True):
                if not new_name.strip():
                    st.error("Product name is required.")
                else:
                    st.session_state.inventory.append({
                        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                        "name": new_name.strip(),
                        "price": new_price,
                        "stock": new_stock,
                        "category": new_cat,
                    })
                    save_all()
                    st.success(f"✅ '{new_name}' added!")
                    st.rerun()

    f1, f2, f3 = st.columns([3, 1, 1])
    search_q      = f1.text_input("🔍 Search products", placeholder="Type a name...")
    filter_status = f2.selectbox("Status", ["All", "In Stock", "Low Stock (≤3)", "Out of Stock"])
    all_cats      = sorted(set(p.get("category", "Other") for p in st.session_state.inventory))
    filter_cat    = f3.selectbox("Category", ["All"] + all_cats)

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
                f'<div style="font-size:1.3rem;font-weight:800;color:#e94560;">{total}</div>'
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
            col_name, col_cat, col_price, col_stock, col_actions = st.columns([3, 1.5, 1, 1.5, 3])

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
                if ec3.button("Apply", key=f"apply_{pid}"):
                    product["stock"] = new_q; product["price"] = new_p; save_all()
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
        p         = st.session_state.sumup_pending
        total_due = p["unit_price"] * p["qty"]

        # ── auto-poll: silently check status, resolve if done ─────────────────
        _auto_error = None
        try:
            _data   = sumup_get_checkout(p["checkout_id"])
            _status = _data.get("status", "UNKNOWN").upper()
        except Exception as _e:
            _data   = {}
            _status = "UNKNOWN"
            _auto_error = str(_e)

        if _status == "PAID":
            for prod in st.session_state.inventory:
                if prod["id"] == p["product_id"]:
                    prod["stock"] = max(0, prod["stock"] - p["qty"])
                    break
            st.session_state.sales.append({
                "id":                datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "timestamp":         datetime.now().isoformat(),
                "product_id":        p["product_id"],
                "product_name":      p["product_name"],
                "category":          p["category"],
                "qty":               p["qty"],
                "unit_price":        p["unit_price"],
                "total":             total_due,
                "payment":           p["payment"],
                "sumup_checkout_id": p["checkout_id"],
            })
            save_all()
            st.session_state.sumup_pending = None
            st.success(f"✅ Payment confirmed! Sold {p['qty']}× {p['product_name']} for €{total_due:.2f}")
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

            st.markdown(
                f'<div class="card card-warning">'
                f'<b>{spinner} Waiting for card payment</b> &nbsp;·&nbsp; '
                f'{p["qty"]}× {p["product_name"]} &nbsp;·&nbsp; <b>€{total_due:.2f}</b><br>'
                f'<small style="color:rgba(255,255,255,0.55);">'
                f'Auto-checking every 3 s &nbsp;·&nbsp; Status: <b>{_status}</b>'
                f'{"&nbsp;·&nbsp; ⚠️ " + _auto_error if _auto_error else ""}'
                f'</small></div>',
                unsafe_allow_html=True,
            )

            if p.get("checkout_url"):
                st.markdown(f"[🔗 Open SumUp payment page]({p['checkout_url']})")

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

    # ── Record a sale ─────────────────────────────────────────────────────────
    st.subheader("🛍️ Record a Sale")
    if st.session_state.sumup_pending:
        st.info("Complete or cancel the pending card payment before recording a new sale.")
    elif not in_stock_products:
        st.warning("No products in stock. Add stock in the Inventory page first.")
    else:
        with st.form("sale_form", clear_on_submit=True):
            product_names  = {p["name"]: p for p in in_stock_products}
            c1, c2, c3     = st.columns([3, 1, 1])
            chosen_name    = c1.selectbox("Product", list(product_names.keys()))
            qty            = c2.number_input("Qty", min_value=1, step=1, value=1)
            payment        = c3.selectbox("Payment", ["💳 Card", "💵 Cash"])
            chosen_product = product_names[chosen_name]
            unit_price     = chosen_product["price"]
            st.markdown(f"**Unit price:** €{unit_price:.2f} &nbsp;|&nbsp; **Total:** €{unit_price * qty:.2f}")

            if st.form_submit_button("✅ Record Sale", use_container_width=True):
                if qty > chosen_product["stock"]:
                    st.error(f"Only {chosen_product['stock']} in stock!")
                elif "Card" in payment:
                    if not st.secrets.get("SUMUP_API_KEY", ""):
                        st.error("No SUMUP_API_KEY in secrets. Add it to .streamlit/secrets.toml to use card payments.")
                    else:
                        ref = f"AA-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                        try:
                            checkout     = sumup_create_checkout(unit_price * qty, "EUR", f"{qty}× {chosen_name}", ref)
                            checkout_url = checkout.get("hosted_checkout_url") or checkout.get("checkout_url", "")
                            st.session_state.sumup_pending = {
                                "checkout_id":  checkout["id"],
                                "checkout_url": checkout_url,
                                "product_id":   chosen_product["id"],
                                "product_name": chosen_name,
                                "category":     chosen_product.get("category", "Other"),
                                "qty":          qty,
                                "unit_price":   unit_price,
                                "payment":      payment,
                            }
                            st.rerun()
                        except Exception as e:
                            st.error(f"SumUp error: {e}")
                else:
                    chosen_product["stock"] -= qty
                    st.session_state.sales.append({
                        "id":           datetime.now().strftime("%Y%m%d%H%M%S%f"),
                        "timestamp":    datetime.now().isoformat(),
                        "product_id":   chosen_product["id"],
                        "product_name": chosen_product["name"],
                        "category":     chosen_product["category"],
                        "qty":          qty,
                        "unit_price":   unit_price,
                        "total":        unit_price * qty,
                        "payment":      payment,
                    })
                    save_all()
                    st.success(f"💵 Sold {qty}× {chosen_name} for €{unit_price * qty:.2f}")
                    st.rerun()

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
                         color="Units", color_continuous_scale=["#0f3460", "#e94560"],
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
                          color_discrete_sequence=px.colors.sequential.Plasma_r,
                          template="plotly_dark", hole=0.4)
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                               legend=dict(font=dict(color="#fff")),
                               margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### 📅 Revenue Over Time")
        by_date = df.groupby("date")["total"].sum().reset_index()
        by_date.columns = ["Date", "Revenue"]
        fig3 = px.area(by_date, x="Date", y="Revenue",
                       template="plotly_dark", color_discrete_sequence=["#e94560"])
        fig3.update_traces(fillcolor="rgba(233,69,96,0.2)")
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig3, use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("#### 💳 Payment Method Breakdown")
            pay_df = df.groupby("payment").agg(Units=("qty", "sum"), Revenue=("total", "sum")).reset_index()
            fig4 = px.bar(pay_df, x="payment", y=["Units", "Revenue"], barmode="group",
                          template="plotly_dark", color_discrete_sequence=["#e94560", "#0f3460"])
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
                          color_continuous_scale=["#0f3460", "#e94560"])
            fig5.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               coloraxis_showscale=False, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig5, use_container_width=True)