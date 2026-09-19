# Pre-registered rule: fade 4-sigma 5-min moves (vol >= 3x trailing median), entered at trigger close,
# only when the trigger is outside 13:00-21:00 UTC and not in the 12:25-12:59 UTC macro window.
import json, math, statistics as st, datetime as dt, sys
def tstat(xs):
    n=len(xs); return st.mean(xs)/(st.pstdev(xs)/math.sqrt(n)+1e-12) if n>2 else float('nan')
def events(data):
    ts=[r[0] for r in data]; cl=[r[4] for r in data]; vol=[r[5] for r in data]; n=len(cl)
    lr=[0.0]+[math.log(cl[i]/cl[i-1]) for i in range(1,n)]
    W=1440; sd=[0.0]*n; s=0.0; ss=0.0
    for i in range(n):
        s+=lr[i]; ss+=lr[i]**2
        if i>=W: s-=lr[i-W]; ss-=lr[i-W]**2
        if i>=W-1: m=s/W; sd[i]=math.sqrt(max(ss/W-m*m,1e-18))
    medv=[0.0]*n; cur=0.0
    for i in range(n):
        if i>=W and i%60==0: cur=sorted(vol[i-W:i])[W//2]
        medv[i]=cur
    rows=[]; last=-10**9
    for i in range(W+5,n-300):
        r5=sum(lr[i-4:i+1]); v5=sum(vol[i-4:i+1]); thr=4*sd[i-5]*math.sqrt(5)
        if medv[i]>0 and abs(r5)>=thr and v5>=3*5*medv[i] and i-last>=60:
            sgn=1 if r5>0 else -1; last=i
            t=dt.datetime.fromtimestamp(ts[i],dt.timezone.utc)
            off = not (13<=t.hour<21) and not (t.hour==12 and t.minute>=25)
            rows.append(dict(t=t, sgn=sgn, off=off, fwd={h:-sgn*math.log(cl[i+h]/cl[i]) for h in (15,30,60,120,240)}))
    return rows
def report(label, rows, horizons=(15,30,60,120,240)):
    if len(rows)<5: print(f"   {label:<28} N={len(rows)} (too few)"); return
    print(f"   {label:<28} N={len(rows):<4}" + "  ".join(f"{h}m {st.mean([r['fwd'][h] for r in rows])*100:+.3f}% (hit {sum(1 for r in rows if r['fwd'][h]>0)/len(rows)*100:.0f}%, t={tstat([r['fwd'][h] for r in rows]):+.1f})" for h in horizons))
for product in ("BTC-USD","ETH-USD"):
    for path, label in ((f"{product}_1m_2025-09-19_2026-06-21.json","OUT-OF-SAMPLE 2025-09-19..2026-06-21"), (f"{product}_1m_90d.json","IN-SAMPLE 2026-06-21..2026-09-19")):
        try: data=json.load(open(path))
        except FileNotFoundError: print(f"{product} {label}: file missing"); continue
        rows=events(data); off=[r for r in rows if r["off"]]; us=[r for r in rows if not r["off"]]
        print(f"\n##### {product}  {label}  ({len(data)/1440:.0f} days, {len(rows)} events)")
        report("off-hours, non-macro (RULE)", off); report("US hours / macro (excluded)", us); report("all events", rows)
        if len(off)>=5:
            x=[r['fwd'][120] for r in off]; xs=sorted(x)
            print(f"   RULE 120m: net/trade @0.04% fees {st.mean(x)*100-0.04:+.3f}%, @0.10% {st.mean(x)*100-0.10:+.3f}%; sd {st.pstdev(x)*100:.2f}%; p10 {xs[len(xs)//10]*100:+.2f}% p90 {xs[9*len(xs)//10]*100:+.2f}% worst {xs[0]*100:+.2f}%")
            months={}
            for r in off: months.setdefault(r['t'].strftime('%Y-%m'),[]).append(r['fwd'][120])
            print("   RULE 120m by month: " + "  ".join(f"{m}: {st.mean(v)*100:+.2f}% (N={len(v)})" for m,v in sorted(months.items())))
            print(f"   RULE by direction 120m: buy-the-drop N={sum(1 for r in off if r['sgn']<0)} {st.mean([r['fwd'][120] for r in off if r['sgn']<0])*100:+.3f}%   sell-the-spike N={sum(1 for r in off if r['sgn']>0)} {st.mean([r['fwd'][120] for r in off if r['sgn']>0])*100:+.3f}%")
