#!/usr/bin/env python3
"""
One-time migration: watchlist_items one-to-many → many-to-many theme associations.

Steps:
  1. Create watchlist_item_themes association table
  2. Populate it from existing watchlist_items.theme_id values
  3. Deduplicate watchlist_items rows that share the same symbol
     (keeping the highest-scored row, merging all theme links into it)

Safe to re-run: uses INSERT OR IGNORE so it won't duplicate associations.
"""
import os
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "newman_trading.db")

if not os.path.exists(DB_PATH):
    print(f"ERROR: database not found at {DB_PATH}")
    sys.exit(1)

print(f"Database: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ── 1. Create association table ──────────────────────────────────────────────
cur.execute("""
    CREATE TABLE IF NOT EXISTS watchlist_item_themes (
        watchlist_item_id INTEGER NOT NULL REFERENCES watchlist_items(id),
        theme_id          INTEGER NOT NULL REFERENCES themes(id),
        PRIMARY KEY (watchlist_item_id, theme_id)
    )
""")
print("✓ watchlist_item_themes table created (or already exists)")

# ── 2. Migrate existing theme_id FK data ────────────────────────────────────
cur.execute("""
    INSERT OR IGNORE INTO watchlist_item_themes (watchlist_item_id, theme_id)
    SELECT id, theme_id FROM watchlist_items WHERE theme_id IS NOT NULL
""")
migrated = cur.rowcount
print(f"✓ Migrated {migrated} existing theme associations")

# ── 3. Deduplicate watchlist_items by symbol ─────────────────────────────────
cur.execute("""
    SELECT symbol, COUNT(*) AS cnt
    FROM watchlist_items
    GROUP BY symbol
    HAVING cnt > 1
""")
dupes = cur.fetchall()
print(f"Found {len(dupes)} symbols with duplicate rows: {[d[0] for d in dupes]}")

merged_rows = 0
for symbol, _cnt in dupes:
    # Keep the row with the highest rank_score; ties broken by lowest id
    cur.execute("""
        SELECT id FROM watchlist_items
        WHERE symbol = ?
        ORDER BY rank_score DESC, id ASC
    """, (symbol,))
    rows = cur.fetchall()
    keeper_id = rows[0][0]
    duplicate_ids = [r[0] for r in rows[1:]]

    for dup_id in duplicate_ids:
        # Move theme links from the duplicate to the keeper
        cur.execute("""
            INSERT OR IGNORE INTO watchlist_item_themes (watchlist_item_id, theme_id)
            SELECT ?, theme_id FROM watchlist_item_themes WHERE watchlist_item_id = ?
        """, (keeper_id, dup_id))
        # Remove duplicate's associations
        cur.execute("DELETE FROM watchlist_item_themes WHERE watchlist_item_id = ?", (dup_id,))
        # Remove the duplicate row itself
        cur.execute("DELETE FROM watchlist_items WHERE id = ?", (dup_id,))
        merged_rows += 1

print(f"✓ Removed {merged_rows} duplicate rows (symbols merged into single rows)")

conn.commit()
conn.close()

# ── Verify ───────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM watchlist_items")
total_items = cur.fetchone()[0]
cur.execute("SELECT COUNT(DISTINCT symbol) FROM watchlist_items")
unique_symbols = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM watchlist_item_themes")
assocs = cur.fetchone()[0]
cur.execute("SELECT wi.symbol, GROUP_CONCAT(t.name, ', ') FROM watchlist_item_themes wit "
            "JOIN watchlist_items wi ON wi.id = wit.watchlist_item_id "
            "JOIN themes t ON t.id = wit.theme_id "
            "GROUP BY wi.symbol ORDER BY wi.symbol LIMIT 10")
sample = cur.fetchall()
conn.close()

print(f"\nPost-migration state:")
print(f"  watchlist_items:        {total_items} rows ({unique_symbols} unique symbols)")
print(f"  watchlist_item_themes:  {assocs} associations")
print(f"\nSample associations (first 10 symbols):")
for sym, themes in sample:
    print(f"  {sym}: {themes}")

print("\nMigration complete.")
