import json, math, statistics as st, datetime as dt, time, urllib.request, os, bisect

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "oi-study/0.1"})
    for a in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())
        except Exception as e: time.sleep(1.5*(a+1))
    raise RuntimeError(url)

def fetch_oi(sym, since, to):
    cache = f"kraken_oi_{sym}.json"
    if os.path.exists(cache):
        t, v = json.load(open(cache)); return [t, [float(x) for x in v]]
    ts_all, oi_all = [], []
    s = since
    while True:
        r = get(f"https://futures.kraken.com/api/charts/v1/analytics/{sym}/open-interest?since={s}&to={to}&interval=300")["result"]
        ts, data = r["timestamp"], r["data"]
        if not ts: break
        vals = [ (d if isinstance(d,(int,float)) else (d.get("value") if isinstance(d,dict) else d[0])) for d in data ]
        ts_all += ts; oi_all += vals
        if not r.get("more"): break
        s = ts[-1] + 1
        time.sleep(0.15)
    json.dump([ts_all, oi_all], open(cache, "w"))
    return [ts_all, [float(x) for x in oi_all]]

def tstat(xs):
    n=len(xs); return st.mean(xs)/(st.pstdev(xs)/math.sqrt(n)+1e-12) if n>2 else float('nan')

def oi_at(ts_oi, oi, t):
    k = bisect.bisect_right(ts_oi, t) - 1
    return oi[k] if k >= 0 else None

def report(label, rows, horizons=(15,30,60,120,240)):
    # rows: list of dict(fwd={h:ret})
    if len(rows) < 5: print(f"   {label:<42} N={len(rows)} (too few)"); return
    print(f"   {label:<42} N={len(rows):<4}" + "  ".join(
        f"{h}m {st.mean([r['fwd'][h] for r in rows])*100:+.2f}% (hit {sum(1 for r in rows if r['fwd'][h]>0)/len(rows)*100:.0f}%, t={tstat([r['fwd'][h] for r in rows]):+.1f})" for h in horizons))

for product, sym in (("BTC-USD","PF_XBTUSD"), ("ETH-USD","PF_ETHUSD")):
    data = json.load(open(f"{product}_1m_90d.json"))
    ts=[r[0] for r in data]; cl=[r[4] for r in data]; vol=[r[5] for r in data]
    n=len(cl); lr=[0.0]+[math.log(cl[i]/cl[i-1]) for i in range(1,n)]
    ts_oi, oi = fetch_oi(sym, ts[0]-3600, ts[-1]+3600)
    print(f"\n##### {product} / {sym}: OI points={len(ts_oi)} from {dt.datetime.fromtimestamp(ts_oi[0],dt.timezone.utc):%m-%d} to {dt.datetime.fromtimestamp(ts_oi[-1],dt.timezone.utc):%m-%d}; OI now≈{oi[-1]:.0f}; sample raw={oi[:3]}")
    # daily OI change sd for scale
    d_oi = [math.log(oi[i]/oi[i-1]) for i in range(1,len(oi)) if oi[i]>0 and oi[i-1]>0]
    print(f"   5-min OI log-change sd: {st.pstdev(d_oi)*100:.3f}%   25-min OI change sd: {st.pstdev([math.log(oi[i]/oi[i-5]) for i in range(5,len(oi)) if oi[i]>0 and oi[i-5]>0])*100:.3f}%")

    def build_events(kind):
        ev=[]; last=-10**9
        if kind == "big15":
            for i in range(1500, n-300):
                r15=sum(lr[i-14:i+1])
                if abs(r15)>=0.01 and i-last>=120: ev.append((i, 1 if r15>0 else -1, r15)); last=i
        else:  # 4-sigma 5-min with volume
            W=1440; sd=[0.0]*n; s=0.0; ss=0.0
            for i in range(n):
                s+=lr[i]; ss+=lr[i]**2
                if i>=W: s-=lr[i-W]; ss-=lr[i-W]**2
                if i>=W-1: m=s/W; sd[i]=math.sqrt(max(ss/W-m*m,1e-18))
            medv=[0.0]*n; cur=0.0
            for i in range(n):
                if i>=W and i%60==0: cur=sorted(vol[i-W:i])[W//2]
                medv[i]=cur
            for i in range(W+5,n-300):
                r5=sum(lr[i-4:i+1]); v5=sum(vol[i-4:i+1]); thr=4*sd[i-5]*math.sqrt(5)
                if medv[i]>0 and abs(r5)>=thr and v5>=3*5*medv[i] and i-last>=60: ev.append((i,1 if r5>0 else -1, r5)); last=i
        rows=[]
        for i,sgn,r in ev:
            o_before = oi_at(ts_oi, oi, ts[i]-20*60); o_after = oi_at(ts_oi, oi, ts[i]+5*60)
            if not o_before or not o_after: continue
            doi = math.log(o_after/o_before)
            hour = dt.datetime.fromtimestamp(ts[i],dt.timezone.utc).hour; minute = dt.datetime.fromtimestamp(ts[i],dt.timezone.utc).minute
            macro = (hour==12 and minute>=25) or (hour==13 and minute<=50) or (hour==18 and minute<=40)
            rows.append(dict(i=i, sgn=sgn, move=r, doi=doi, macro=macro, us=(13<=hour<21),
                             fwd={h: -sgn*math.log(cl[i+h]/cl[i]) for h in (15,30,60,120,240)}))
        return rows

    for kind, title in (("big15","|15-min move| >= 1.0%"), ("sig4","4-sigma 5-min move with 3x volume")):
        rows = build_events(kind)
        dois = sorted(r["doi"] for r in rows)
        lo_cut, hi_cut = dois[len(dois)//3], dois[2*len(dois)//3]
        print(f"\n   == {title}: N={len(rows)}; OI change during move: terciles cut at {lo_cut*100:+.2f}% / {hi_cut*100:+.2f}%, min {dois[0]*100:+.2f}% max {dois[-1]*100:+.2f}%")
        report("all events (fade)", rows)
        report("OI FELL most (deleveraging tercile)", [r for r in rows if r["doi"]<=lo_cut])
        report("OI middle tercile", [r for r in rows if lo_cut<r["doi"]<hi_cut])
        report("OI ROSE most (positioning tercile)", [r for r in rows if r["doi"]>=hi_cut])
        report("OI fell > 1% (strong deleveraging)", [r for r in rows if r["doi"]<=-0.01])
        report("OI fell > 1%, DOWN moves only (buy)", [r for r in rows if r["doi"]<=-0.01 and r["sgn"]<0])
        report("OI fell > 1%, UP moves only (sell)", [r for r in rows if r["doi"]<=-0.01 and r["sgn"]>0])
        report("OI fell > 1%, excl. macro windows", [r for r in rows if r["doi"]<=-0.01 and not r["macro"]])
        report("OI rose > 1% (strong positioning)", [r for r in rows if r["doi"]>=0.01])
        report("macro-window events (12:25-13:50, 18:00-18:40 UTC)", [r for r in rows if r["macro"]])
        report("non-macro, outside US hours", [r for r in rows if not r["macro"] and not r["us"]])
        # correlation between doi and 60m fade return
        xs=[r["doi"] for r in rows]; ys=[r["fwd"][60] for r in rows]
        mx,my=st.mean(xs),st.mean(ys); cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys)); corr=cov/math.sqrt(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys)+1e-18)
        print(f"   corr(OI change, 60m fade return) = {corr:+.3f}   (negative = OI drop -> more reversion)")
