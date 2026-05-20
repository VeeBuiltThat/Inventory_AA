"""One-time script: import inventory_all CSV into the MySQL database."""
import csv
import hashlib
import pymysql

# ── DB credentials (from .streamlit/secrets.toml) ─────────────────────────────
DB_HOST     = "gameswaw7.bisecthosting.com"
DB_PORT     = 3306
DB_NAME     = "s416861_veebuiltthat"
DB_USER     = "u416861_fF8WVXwQmR"
DB_PASSWORD = "S06V5S52ZXI0XQqrsmT1pkIx"

CSV_PATH = r"C:\Users\pepij\Downloads\inventory_all_20260516_1357.csv"

# ── Connect ────────────────────────────────────────────────────────────────────
conn = pymysql.connect(
    host=DB_HOST, port=DB_PORT, database=DB_NAME,
    user=DB_USER, password=DB_PASSWORD, connect_timeout=10,
    cursorclass=pymysql.cursors.DictCursor,
)
cur = conn.cursor()

# ── Ensure table exists ────────────────────────────────────────────────────────
cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id VARCHAR(32) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
        stock INT NOT NULL DEFAULT 0,
        category VARCHAR(100) DEFAULT 'Other',
        image LONGTEXT DEFAULT NULL
    )
""")

# ── Insert rows ────────────────────────────────────────────────────────────────
inserted = 0
skipped  = 0

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        name     = row["Name"].strip()
        category = row["Category"].strip()
        price    = float(row["Price (€)"])
        stock    = int(row["Stock"])
        # Stable 32-char ID derived from the product name
        product_id = hashlib.md5(name.encode()).hexdigest()

        cur.execute(
            """
            INSERT INTO inventory (id, name, price, stock, category, image)
            VALUES (%s, %s, %s, %s, %s, NULL)
            ON DUPLICATE KEY UPDATE
                name=VALUES(name), price=VALUES(price),
                stock=VALUES(stock), category=VALUES(category)
            """,
            (product_id, name, price, stock, category),
        )
        if cur.rowcount == 1:
            inserted += 1
            print(f"  + inserted: {name}")
        else:
            skipped += 1
            print(f"  ~ updated:  {name}")

conn.commit()
cur.close()
conn.close()

print(f"\nDone — {inserted} inserted, {skipped} updated.")
