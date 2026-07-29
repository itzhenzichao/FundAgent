import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_FILE = os.path.join(DB_DIR, "fund_data.db")


def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_tables():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stock_industry (
            stock_code TEXT PRIMARY KEY,
            industry TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fund_info (
            fund_code TEXT PRIMARY KEY,
            fund_name TEXT,
            fund_type TEXT,
            latest_nav REAL,
            latest_date TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fund_holdings (
            fund_code TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            holding_ratio REAL,
            quarter TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (fund_code, stock_code, quarter)
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            fund_code TEXT PRIMARY KEY,
            fund_name TEXT NOT NULL,
            added_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fund_bond_holdings (
            fund_code TEXT NOT NULL,
            bond_code TEXT NOT NULL,
            bond_name TEXT NOT NULL,
            holding_ratio REAL,
            holding_value REAL,
            quarter TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (fund_code, bond_code, quarter)
        );
        CREATE INDEX IF NOT EXISTS idx_stock_industry_code ON stock_industry(stock_code);
        CREATE INDEX IF NOT EXISTS idx_fund_holdings_code ON fund_holdings(fund_code, quarter);
        CREATE INDEX IF NOT EXISTS idx_fund_bond_holdings_code ON fund_bond_holdings(fund_code, quarter);
        CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, created_at);
    """)
    conn.commit()
    conn.close()
