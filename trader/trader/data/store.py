"""Hourly bar store (SQLite) and Coinbase Exchange candle feed. Panel layout matches the research code:
DataFrames indexed by a complete hourly UTC index, one column per symbol."""
import sqlite3, json, time, datetime as dt, urllib.request, urllib.parse
import numpy as np, pandas as pd

class BarStore:
    def __init__(self, path):
        self.path = str(path)
        self.con = sqlite3.connect(self.path, timeout=60)
        self.con.execute("""CREATE TABLE IF NOT EXISTS bars (symbol TEXT NOT NULL, ts INTEGER NOT NULL, open REAL, high REAL, low REAL,
                            close REAL, volume REAL, PRIMARY KEY (symbol, ts))""")
        self.con.commit()

    def last_ts(self, symbol):
        r = self.con.execute("SELECT MAX(ts) FROM bars WHERE symbol=?", (symbol,)).fetchone()
        return r[0]

    def count(self, symbol):
        return self.con.execute("SELECT COUNT(*) FROM bars WHERE symbol=?", (symbol,)).fetchone()[0]

    def upsert(self, symbol, rows):
        """rows: iterable of (ts, open, high, low, close, volume)"""
        self.con.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?)", [(symbol, int(r[0]), *map(float, r[1:6])) for r in rows])
        self.con.commit()

    def import_json(self, symbol, path):
        """Research file format: [[ts, low, high, open, close, volume], ...]"""
        rows = json.load(open(path))
        self.upsert(symbol, [(t, op, hi, lo, cl, vol) for t, lo, hi, op, cl, vol in rows])
        return len(rows)

    def frame(self, symbol, start_ts, end_ts):
        df = pd.read_sql_query("SELECT ts, open, high, low, close, volume FROM bars WHERE symbol=? AND ts>=? AND ts<=? ORDER BY ts",
                               self.con, params=(symbol, int(start_ts), int(end_ts)))
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
        return df.set_index("ts")

    def panel(self, symbols, start_ts, end_ts):
        frames = {s: self.frame(s, start_ts, end_ts) for s in symbols}
        frames = {s: f for s, f in frames.items() if len(f)}
        if not frames:
            raise RuntimeError("no bars in store for requested symbols/range")
        lo = min(f.index[0] for f in frames.values()); hi = max(f.index[-1] for f in frames.values())
        idx = pd.date_range(lo.floor("h"), hi.floor("h"), freq="1h", tz="UTC")
        def col(name):
            return pd.DataFrame({s: f[name].reindex(idx) for s, f in frames.items()}, index=idx)
        raw_close = col("close"); avail = raw_close.notna()
        close = raw_close.ffill()
        return dict(close=close, high=col("high").fillna(close), low=col("low").fillna(close), open=col("open").fillna(close),
                    volume=col("volume").fillna(0.0), avail=avail)

class CoinbaseFeed:
    BASE = "https://api.exchange.coinbase.com"

    def __init__(self, sleep=0.25, user_agent="trader/0.1"):
        self.sleep = sleep; self.ua = user_agent

    def _get(self, path):
        req = urllib.request.Request(self.BASE + path, headers={"User-Agent": self.ua})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("coinbase request failed: " + path)

    def candles(self, product, start, end, gran=3600):
        """Hourly candles between two aware datetimes; returns rows (ts, open, high, low, close, volume) ascending."""
        out = {}
        while end > start:
            s = max(start, end - dt.timedelta(seconds=gran * 300))
            q = urllib.parse.urlencode({"granularity": gran, "start": s.isoformat(), "end": end.isoformat()})
            for t, lo, hi, op, cl, vol in self._get(f"/products/{product}/candles?{q}"):
                out[t] = (t, op, hi, lo, cl, vol)
            end = s; time.sleep(self.sleep)
        return [out[k] for k in sorted(out)]

    def update(self, store, symbols, lookback_days=120, now=None):
        """Bring the store up to the last completed hour for each symbol. Returns {symbol: rows added}."""
        now = now or dt.datetime.now(dt.timezone.utc)
        end = now.replace(minute=0, second=0, microsecond=0)   # candles for the current, incomplete hour are excluded
        added = {}
        for s in symbols:
            last = store.last_ts(s)
            start = (dt.datetime.fromtimestamp(last, dt.timezone.utc) - dt.timedelta(hours=2)) if last else end - dt.timedelta(days=lookback_days)
            rows = [r for r in self.candles(s, start, end) if r[0] < end.timestamp()]
            store.upsert(s, rows); added[s] = len(rows)
        return added
