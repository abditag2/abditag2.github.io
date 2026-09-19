"""Strategy dashboard: compare backtest, paper and live runs from the SQLite ledgers in the state directory.
Run: streamlit run dashboard/app.py"""
import sys, pathlib, glob, os, json, datetime as dt
import numpy as np, pandas as pd, streamlit as st, plotly.graph_objects as go
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from trader import config, metrics
from trader.ledger import Ledger

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]   # fixed order, never cycled
GRID = "#eeeeea"; TEXT = "#0b0b0b"; MUTED = "#52514e"

st.set_page_config(page_title="Strategy dashboard", layout="wide")
st.title("Strategy runs")

# ---- data ----
state_dir = config.STATE_DIR
files = sorted(f for f in glob.glob(str(state_dir / "*.db")) if not f.endswith("bars.db"))
if not files:
    st.info(f"No ledgers in {state_dir}. Run scripts/backtest.py or scripts/run.py first."); st.stop()

@st.cache_data(ttl=60)
def load_runs(paths):
    rows = []
    for p in paths:
        L = Ledger(p); r = L.runs(); r["ledger"] = os.path.basename(p); rows.append(r)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

@st.cache_data(ttl=60)
def load_run(path, run_id):
    L = Ledger(path)
    return L.equity_series(run_id), L.lots(run_id), L.fills(run_id), L.events(run_id)

runs = load_runs(files)
with st.sidebar:
    st.header("Runs")
    chosen_files = st.multiselect("Ledgers", [os.path.basename(f) for f in files], default=[os.path.basename(f) for f in files])
    avail = runs[runs["ledger"].isin(chosen_files)]
    labels = [f"{r.run_id}  [{r.mode}]" for r in avail.itertuples()]
    picked = st.multiselect("Compare up to 8 runs", labels, default=labels[:4])
    if len(picked) > 8:
        st.warning("Showing the first 8; fold the rest into another view."); picked = picked[:8]
    start = st.date_input("From", value=None); end = st.date_input("To", value=None)
    normalize = st.checkbox("Normalize equity to 1.0 at start", value=True)

sel = avail[[f"{r.run_id}  [{r.mode}]" in picked for r in avail.itertuples()]]
if sel.empty: st.stop()

series, table_rows, yearly_rows, lots_all = {}, [], {}, {}
for r in sel.itertuples():
    path = str(state_dir / r.ledger); eq, lots, fills, events = load_run(path, r.run_id)
    if start: eq = eq[eq.index >= pd.Timestamp(start, tz="UTC")]
    if end: eq = eq[eq.index <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
    if len(eq) < 2: continue
    e = eq["equity"] / eq["equity"].iloc[0] if normalize else eq["equity"]
    series[r.run_id] = (e, eq)
    m = metrics.summarize(eq["equity"], lots, eq["exposure"]); lots_all[r.run_id] = (lots, fills, events, r.mode, path)
    if m:
        table_rows.append({"run": r.run_id, "mode": r.mode, "from": m["start"], "to": m["end"], "total return": m["total_return"], "CAGR": m["cagr"],
                           "max drawdown": m["max_drawdown"], "Sharpe": m["sharpe"], "worst month": m["worst_month"], "years +": f"{m['years_positive']}/{m['years']}",
                           "avg exposure": m.get("avg_exposure", np.nan), "trades": m.get("trades", 0), "hit rate": m.get("hit_rate", np.nan), "expectancy": m.get("expectancy", np.nan)})
        yearly_rows[r.run_id] = m["yearly"]

# ---- metrics table ----
st.subheader("Metrics")
if table_rows:
    df = pd.DataFrame(table_rows).set_index("run")
    st.dataframe(df.style.format({"total return": "{:+.1%}", "CAGR": "{:+.1%}", "max drawdown": "{:.1%}", "Sharpe": "{:.2f}", "worst month": "{:+.1%}",
                                  "avg exposure": "{:.0%}", "hit rate": "{:.0%}", "expectancy": "{:+.2%}"}, na_rep="-"), use_container_width=True)

def base_layout(fig, ytitle):
    fig.update_layout(template="plotly_white", hovermode="x unified", height=420, margin=dict(l=40, r=20, t=30, b=40),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), font=dict(color=TEXT, size=13),
                      xaxis=dict(showgrid=False, linecolor=GRID), yaxis=dict(title=ytitle, gridcolor=GRID, zeroline=False))
    return fig

# ---- equity ----
st.subheader("Equity")
fig = go.Figure()
for i, (run, (e, eq)) in enumerate(series.items()):
    fig.add_trace(go.Scatter(x=e.index, y=e.values, mode="lines", name=run, line=dict(width=2, color=PALETTE[i]),
                             hovertemplate="%{y:.3f}<extra>" + run + "</extra>"))
st.plotly_chart(base_layout(fig, "equity (start = 1.0)" if normalize else "equity"), use_container_width=True)

# ---- drawdown ----
st.subheader("Drawdown from peak")
fig = go.Figure()
for i, (run, (e, eq)) in enumerate(series.items()):
    dd = metrics.drawdown(eq["equity"]) * 100
    fig.add_trace(go.Scatter(x=dd.index, y=dd.values, mode="lines", name=run, line=dict(width=2, color=PALETTE[i]), hovertemplate="%{y:.1f}%<extra>" + run + "</extra>"))
st.plotly_chart(base_layout(fig, "% below peak"), use_container_width=True)

# ---- yearly returns ----
st.subheader("Returns by calendar year")
if yearly_rows:
    ydf = pd.DataFrame(yearly_rows).sort_index()
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = go.Figure()
        for i, run in enumerate(ydf.columns):
            fig.add_trace(go.Bar(x=ydf.index, y=ydf[run] * 100, name=run, marker_color=PALETTE[i], hovertemplate="%{y:+.1f}%<extra>" + run + "</extra>"))
        fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
        st.plotly_chart(base_layout(fig, "% return"), use_container_width=True)
    with c2:
        st.dataframe(ydf.style.format("{:+.1%}", na_rep="-"), use_container_width=True)

# ---- per-run detail ----
st.subheader("Run detail")
detail = st.selectbox("Run", list(lots_all))
if detail:
    lots, fills, events, mode, path = lots_all[detail]; e, eq = series[detail]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last mark", eq.index[-1].strftime("%Y-%m-%d %H:%M UTC"))
    c2.metric("Equity", f"{eq['equity'].iloc[-1]:,.2f}")
    c3.metric("Exposure", f"{eq['exposure'].iloc[-1]:.0%}")
    c4.metric("Open lots", int((lots["status"] == "open").sum()) if len(lots) else 0)
    if mode != "backtest":
        age = (dt.datetime.now(dt.timezone.utc) - eq.index[-1].to_pydatetime()).total_seconds() / 3600
        (st.success if age < 2.5 else st.error)(f"Last step {age:.1f} hours ago" + ("" if age < 2.5 else ": the loop is not running or data is stale"))
        L = Ledger(path)
        if L.con.execute("SELECT name FROM sqlite_master WHERE name='kv'").fetchone():
            row = L.con.execute("SELECT value FROM kv WHERE run_id=? AND key='paper_balances'", (detail,)).fetchone()
            if row: st.caption("Paper balances: " + ", ".join(f"{k} {v:,.4f}" for k, v in json.loads(row[0]).items() if abs(v) > 1e-9))
    t1, t2, t3 = st.tabs(["Open positions", "Closed trades", "Events"])
    with t1:
        if len(lots): st.dataframe(lots[lots["status"] == "open"][["symbol", "side", "qty", "entry_ts", "entry_price", "notional"]], use_container_width=True)
    with t2:
        if len(lots):
            cl = lots[lots["status"] == "closed"].copy(); cl["return"] = cl["pnl"] / cl["notional"]
            st.dataframe(cl[["symbol", "side", "entry_ts", "exit_ts", "entry_price", "exit_price", "notional", "pnl", "return"]].sort_values("exit_ts", ascending=False)
                         .style.format({"return": "{:+.2%}", "pnl": "{:+.2f}", "entry_price": "{:.4f}", "exit_price": "{:.4f}", "notional": "{:.2f}"}), use_container_width=True)
    with t3:
        if len(events): st.dataframe(events, use_container_width=True)
        else: st.caption("no events")
