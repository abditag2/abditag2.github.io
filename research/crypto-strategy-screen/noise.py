import json, math, statistics as st, time, urllib.request, datetime as dt

BASE = "https://api.exchange.coinbase.com"
def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "noise-check/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def candles(product, gran, n_bars):
    out = {}
    end = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    while len(out) < n_bars:
        start = end - dt.timedelta(seconds=gran * 300)
        rows = get(f"/products/{product}/candles?granularity={gran}&start={start.isoformat()}&end={end.isoformat()}")
        if not rows: break
        for t, lo, hi, op, cl, vol in rows:
            out[t] = (lo, hi, op, cl, vol)
        end = start
        time.sleep(0.15)
    ks = sorted(out)[-n_bars:]
    return [out[k] for k in ks]

def analyze(name, rows, gran):
    closes = [r[3] for r in rows]
    rets = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
    sd = st.pstdev(rets)
    absm = sorted(abs(x) for x in rets)
    med_abs = absm[len(absm)//2]
    rng = st.mean((r[1] - r[0]) / r[2] for r in rows)
    # lag-1 autocorrelation of close-to-close returns
    mu = st.mean(rets)
    num = sum((rets[i]-mu)*(rets[i-1]-mu) for i in range(1, len(rets)))
    den = sum((x-mu)**2 for x in rets)
    ac1 = num/den
    # naive "fade the last bar" strategy: position = -sign(last return), hold one bar
    gross = sum(-math.copysign(1, rets[i-1]) * rets[i] for i in range(1, len(rets)))
    trades = len(rets) - 1
    # naive "follow the last bar" (momentum)
    gross_mom = -gross
    # z-score reversal: enter when 5-bar return < -2 sd*sqrt(5), exit after 5 bars
    w = 5; thr = 2 * sd * math.sqrt(w)
    z_pnl = 0.0; z_n = 0; i = w
    while i + w < len(rets):
        r5 = sum(rets[i-w:i])
        if r5 < -thr:
            z_pnl += sum(rets[i:i+w]); z_n += 1; i += w
        elif r5 > thr:
            z_pnl -= sum(rets[i:i+w]); z_n += 1; i += w
        else:
            i += 1
    hours = len(rows) * gran / 3600
    print(f"\n[{name}] bars={len(rows)} span={hours/24:.1f}d  price≈{closes[-1]:.0f}")
    print(f"  per-bar close-to-close sd      : {sd*100:.4f}%")
    print(f"  median |move| per bar          : {med_abs*100:.4f}%")
    print(f"  mean high-low range per bar    : {rng*100:.4f}%")
    print(f"  lag-1 autocorr of returns      : {ac1:+.4f}")
    for fee_rt, label in [(0.0004,"perp maker 0.04% RT"),(0.0010,"perp taker 0.10% RT"),(0.0020,"spot 0.20% RT"),(0.0120,"CB retail-tier ~1.2% RT")]:
        frac = sum(1 for x in absm if x > fee_rt) / len(absm)
        print(f"  share of bars with |move| > {label:<24}: {frac*100:5.1f}%")
    print(f"  fade-last-bar: gross {gross*100:+.2f}% over {trades} trades ({gross/trades*1e4:+.2f} bp/trade)")
    print(f"  follow-last-bar: gross {gross_mom*100:+.2f}%  ({gross_mom/trades*1e4:+.2f} bp/trade)")
    print(f"  2-sigma 5-bar reversal: gross {z_pnl*100:+.2f}% over {z_n} trades ({(z_pnl/z_n*1e4 if z_n else 0):+.2f} bp/trade)")
    for fee_rt, label in [(0.0004,"0.04%"),(0.0010,"0.10%"),(0.0020,"0.20%")]:
        print(f"    -> 2-sigma reversal net of {label} RT fees: {(z_pnl - z_n*fee_rt)*100:+.2f}%")

book = get("/products/BTC-USD/book?level=1")
bid = float(book["bids"][0][0]); ask = float(book["asks"][0][0])
print(f"BTC-USD Coinbase top of book: bid {bid} ask {ask} spread {(ask-bid)/bid*100:.4f}%  (bid size {book['bids'][0][1]}, ask size {book['asks'][0][1]})")
stats = get("/products/BTC-USD/stats")
print("24h stats:", {k: stats[k] for k in ("open","high","low","last","volume")})

for name, gran, n in [("1m", 60, 4320), ("5m", 300, 4032), ("15m", 900, 2880), ("1h", 3600, 2160)]:
    analyze(name, candles("BTC-USD", gran, n), gran)

# a smaller alt for comparison
try:
    analyze("SOL-USD 1m", candles("SOL-USD", 60, 1440), 60)
    b = get("/products/SOL-USD/book?level=1"); bid=float(b["bids"][0][0]); ask=float(b["asks"][0][0])
    print(f"  SOL-USD spread {(ask-bid)/bid*100:.4f}%")
except Exception as e:
    print("SOL fetch failed:", e)
