"""SQLite ledger: runs, fills, lots, base positions, hourly equity. One file can hold many runs."""
import sqlite3, json, time
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, mode TEXT, strategy TEXT, config TEXT, symbols TEXT, started_at INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts INTEGER, symbol TEXT, side TEXT, qty REAL, price REAL,
    notional REAL, fee REAL, book TEXT, reason TEXT, ref TEXT);
CREATE TABLE IF NOT EXISTS lots (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, symbol TEXT, side INTEGER, qty REAL, entry_ts INTEGER,
    entry_price REAL, notional REAL, exit_ts INTEGER, exit_price REAL, pnl REAL, status TEXT);
CREATE TABLE IF NOT EXISTS base (run_id TEXT, symbol TEXT, qty REAL, PRIMARY KEY (run_id, symbol));
CREATE TABLE IF NOT EXISTS equity (run_id TEXT, ts INTEGER, equity REAL, cash REAL, exposure REAL, PRIMARY KEY (run_id, ts));
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts INTEGER, level TEXT, message TEXT);
"""

class Ledger:
    def __init__(self, path):
        self.path = str(path); self.con = sqlite3.connect(self.path, timeout=60)
        self.con.executescript(SCHEMA); self.con.commit()

    def new_run(self, run_id, mode, strategy, config, symbols, note=""):
        self.con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?)",
                         (run_id, mode, strategy, json.dumps(config), json.dumps(symbols), int(time.time()), note)); self.con.commit()

    def runs(self):
        return pd.read_sql_query("SELECT * FROM runs ORDER BY started_at", self.con)

    def run_symbols(self, run_id):
        r = self.con.execute("SELECT symbols FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(r[0]) if r else []

    def record_fill(self, run_id, ts, symbol, side, qty, price, notional, fee, book, reason, ref):
        self.con.execute("INSERT INTO fills (run_id, ts, symbol, side, qty, price, notional, fee, book, reason, ref) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (run_id, int(ts), symbol, side, qty, price, notional, fee, book, reason, ref))

    def open_lot(self, run_id, symbol, side, qty, entry_ts, entry_price, notional):
        self.con.execute("INSERT INTO lots (run_id, symbol, side, qty, entry_ts, entry_price, notional, status) VALUES (?,?,?,?,?,?,?,'open')",
                         (run_id, symbol, side, qty, int(entry_ts), entry_price, notional))

    def close_lot(self, run_id, symbol, exit_ts, exit_price, pnl):
        self.con.execute("UPDATE lots SET exit_ts=?, exit_price=?, pnl=?, status='closed' WHERE run_id=? AND symbol=? AND status='open'",
                         (int(exit_ts), exit_price, pnl, run_id, symbol))

    def set_base(self, run_id, symbol, qty):
        self.con.execute("INSERT OR REPLACE INTO base VALUES (?,?,?)", (run_id, symbol, qty))

    def record_equity(self, run_id, ts, equity, cash, exposure):
        self.con.execute("INSERT OR REPLACE INTO equity VALUES (?,?,?,?,?)", (run_id, int(ts), equity, cash, exposure))

    def event(self, run_id, ts, level, message):
        self.con.execute("INSERT INTO events (run_id, ts, level, message) VALUES (?,?,?,?)", (run_id, int(ts), level, message)); self.con.commit()

    def commit(self): self.con.commit()

    def state(self, run_id):
        lots = pd.read_sql_query("SELECT * FROM lots WHERE run_id=? AND status='open'", self.con, params=(run_id,))
        base = pd.read_sql_query("SELECT symbol, qty FROM base WHERE run_id=?", self.con, params=(run_id,))
        return lots, base

    def equity_series(self, run_id):
        df = pd.read_sql_query("SELECT ts, equity, cash, exposure FROM equity WHERE run_id=? ORDER BY ts", self.con, params=(run_id,))
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True); return df.set_index("ts")

    def fills(self, run_id):
        df = pd.read_sql_query("SELECT * FROM fills WHERE run_id=? ORDER BY ts", self.con, params=(run_id,))
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True); return df

    def lots(self, run_id):
        df = pd.read_sql_query("SELECT * FROM lots WHERE run_id=? ORDER BY entry_ts", self.con, params=(run_id,))
        for c in ("entry_ts", "exit_ts"): df[c] = pd.to_datetime(df[c], unit="s", utc=True)
        return df

    def events(self, run_id, limit=200):
        df = pd.read_sql_query("SELECT ts, level, message FROM events WHERE run_id=? ORDER BY id DESC LIMIT ?", self.con, params=(run_id, limit))
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True); return df
