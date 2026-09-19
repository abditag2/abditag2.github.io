import json, math, statistics as st, sys

def load(product, days):
    return json.load(open(f"{product}_1m_{days}d.json"))

def tstat(xs):
    n = len(xs)
    if n < 3: return float('nan')
    return st.mean(xs) / (st.pstdev(xs) / math.sqrt(n) + 1e-12)

def study(product, data, k, volmult, W=1440, horizons=(5, 15, 30, 60), cooldown=60, fees=(0.0004, 0.0010, 0.0020)):
    lo = [r[1] for r in data]; hi = [r[2] for r in data]; cl = [r[4] for r in data]; vol = [r[5] for r in data]
    n = len(cl)
    lr = [0.0] + [math.log(cl[i] / cl[i-1]) for i in range(1, n)]
    # rolling 1m sd via running sums (trailing W bars ending at i)
    sd = [0.0] * n; s = 0.0; ss = 0.0
    for i in range(n):
        s += lr[i]; ss += lr[i] * lr[i]
        if i >= W:
            s -= lr[i-W]; ss -= lr[i-W] * lr[i-W]
        if i >= W - 1:
            m = s / W; sd[i] = math.sqrt(max(ss / W - m * m, 1e-18))
    # rolling median volume, recomputed hourly
    medv = [0.0] * n; cur = 0.0
    for i in range(n):
        if i >= W and i % 60 == 0:
            cur = sorted(vol[i-W:i])[W // 2]
        medv[i] = cur
    events = []  # (i, sign) sign=-1 for down move, +1 for up move
    last = -10**9
    for i in range(W + 5, n - 120):
        r5 = sum(lr[i-4:i+1]); v5 = sum(vol[i-4:i+1])
        thr = k * sd[i-5] * math.sqrt(5)
        if medv[i] <= 0 or thr <= 0: continue
        if abs(r5) >= thr and v5 >= volmult * 5 * medv[i] and i - last >= cooldown:
            events.append((i, 1 if r5 > 0 else -1, r5)); last = i
    res = {"naive": {h: [] for h in horizons}, "exh": {h: [] for h in horizons}}
    n_noexh = 0; extension = []; waits = []; mae = []; mfe = []
    trades = {f: [] for f in fees}; gross = []; outcomes = {"target": 0, "stop": 0, "time": 0}
    for i, sgn, r5 in events:
        # naive: enter at trigger close, bet on reversion
        for h in horizons:
            res["naive"][h].append(-sgn * math.log(cl[i+h] / cl[i]))
        # exhaustion: wait until no new extreme for 3 consecutive minutes (max 30 min)
        if sgn < 0:
            ext = min(lo[i-4:i+1])
        else:
            ext = max(hi[i-4:i+1])
        streak = 0; j = None; ext0 = ext
        for m in range(i + 1, min(i + 31, n - 120)):
            newext = (lo[m] < ext) if sgn < 0 else (hi[m] > ext)
            if newext:
                ext = lo[m] if sgn < 0 else hi[m]; streak = 0
            else:
                streak += 1
                if streak == 3: j = m; break
        if j is None:
            n_noexh += 1; continue
        extension.append(-sgn * math.log(ext / ext0))   # how much further it ran after the trigger (positive = ran further against the fade)
        waits.append(j - i)
        for h in horizons:
            res["exh"][h].append(-sgn * math.log(cl[j+h] / cl[j]))
        # excursions over 30 min after entry (in the direction of the fade)
        if sgn < 0:
            mae.append(min(lo[j+1:j+31]) / cl[j] - 1); mfe.append(max(hi[j+1:j+31]) / cl[j] - 1)
        else:
            mae.append(1 - max(hi[j+1:j+31]) / cl[j]); mfe.append(1 - min(lo[j+1:j+31]) / cl[j])
        # simple rule: leg = pre-cascade close to extreme; stop beyond extreme by 20% of leg; target 50% retrace of leg; 30 min time stop
        ref = cl[i-5]; leg = abs(math.log(ref / ext)); entry = cl[j]
        if sgn < 0:
            stop = ext * math.exp(-0.2 * leg); target = ext * math.exp(0.5 * leg)
        else:
            stop = ext * math.exp(0.2 * leg); target = ext * math.exp(-0.5 * leg)
        pnl = None
        for m in range(j + 1, j + 31):
            if sgn < 0:
                if lo[m] <= stop: pnl = math.log(stop / entry) - 0.0005; outcomes["stop"] += 1; break
                if hi[m] >= target: pnl = math.log(target / entry); outcomes["target"] += 1; break
            else:
                if hi[m] >= stop: pnl = math.log(entry / stop) - 0.0005; outcomes["stop"] += 1; break
                if lo[m] <= target: pnl = math.log(entry / target); outcomes["target"] += 1; break
        if pnl is None:
            pnl = -sgn * math.log(cl[j+30] / entry); outcomes["time"] += 1
        gross.append(pnl)
        for f in fees: trades[f].append(pnl - f)
    print(f"\n=== {product}  k={k}-sigma 5-min move, volume>={volmult}x median  ({len(data)/1440:.0f} days) ===")
    print(f"events: {len(events)}  (down moves: {sum(1 for e in events if e[1] < 0)}, up moves: {sum(1 for e in events if e[1] > 0)})")
    if events:
        print(f"mean |trigger move|: {st.mean(abs(e[2]) for e in events)*100:.2f}%")
    print(f"no exhaustion within 30 min (cascade kept going): {n_noexh}")
    if extension:
        print(f"after trigger, price ran a further {st.mean(extension)*100:.2f}% on average (median {st.median(extension)*100:.2f}%) before stalling; avg wait {st.mean(waits):.1f} min")
    print(f"{'entry':<8}{'horizon':>8}{'N':>6}{'mean':>9}{'median':>9}{'hit%':>7}{'t':>7}")
    for kind in ("naive", "exh"):
        for h in horizons:
            xs = res[kind][h]
            if len(xs) < 3: continue
            print(f"{kind:<8}{h:>7}m{len(xs):>6}{st.mean(xs)*100:>8.3f}%{st.median(xs)*100:>8.3f}%{sum(1 for x in xs if x > 0)/len(xs)*100:>6.0f}%{tstat(xs):>7.2f}")
    if mae:
        print(f"30-min excursions after exhaustion entry: mean adverse {st.mean(mae)*100:.2f}% (median {st.median(mae)*100:.2f}%), mean favorable {st.mean(mfe)*100:.2f}% (median {st.median(mfe)*100:.2f}%)")
    if gross:
        print(f"rule (stop 20% beyond extreme, target 50% retrace, 30m time stop): N={len(gross)} outcomes={outcomes} hit%={sum(1 for x in gross if x > 0)/len(gross)*100:.0f}%")
        print(f"   gross per trade {st.mean(gross)*100:+.3f}%  total {sum(gross)*100:+.2f}%  t={tstat(gross):.2f}")
        for f in fees:
            print(f"   net of {f*100:.2f}% RT fees: per trade {st.mean(trades[f])*100:+.3f}%  total {sum(trades[f])*100:+.2f}%")
    # unconditional baseline: sd of h-minute returns for scale
    print("baseline sd of forward returns: " + ", ".join(f"{h}m {st.pstdev([sum(lr[i:i+h]) for i in range(W, n-120, 7)])*100:.3f}%" for h in horizons))

if __name__ == "__main__":
    days = int(sys.argv[1])
    for product in ("BTC-USD", "ETH-USD"):
        data = load(product, days)
        for k, vm in ((3, 3), (4, 3), (5, 4)):
            study(product, data, k, vm)
