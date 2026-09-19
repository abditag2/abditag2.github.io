import json, math, statistics as st, datetime as dt
def tstat(xs):
    n=len(xs); return st.mean(xs)/(st.pstdev(xs)/math.sqrt(n)+1e-12) if n>2 else float('nan')
for product in ("BTC-USD","ETH-USD"):
    data = json.load(open(f"{product}_1m_90d.json"))
    ts=[r[0] for r in data]; lo=[r[1] for r in data]; hi=[r[2] for r in data]; cl=[r[4] for r in data]; vol=[r[5] for r in data]
    n=len(cl); lr=[0.0]+[math.log(cl[i]/cl[i-1]) for i in range(1,n)]
    print(f"\n##### {product}: large absolute moves (15-min window), 90 days")
    for thr in (0.01, 0.015, 0.02):
        ev=[]; last=-10**9
        for i in range(1500, n-300):
            r15=sum(lr[i-14:i+1])
            if abs(r15)>=thr and i-last>=120:
                ev.append((i, 1 if r15>0 else -1, r15)); last=i
        if not ev: print(f"|15m move| >= {thr*100:.1f}%: 0 events"); continue
        print(f"|15m move| >= {thr*100:.1f}%: {len(ev)} events ({sum(1 for e in ev if e[1]<0)} down, {sum(1 for e in ev if e[1]>0)} up), mean |move| {st.mean(abs(e[2]) for e in ev)*100:.2f}%")
        print(f"   fade from trigger close ->  " + "  ".join(
            f"{h}m: mean {st.mean([-s*math.log(cl[i+h]/cl[i]) for i,s,_ in ev])*100:+.2f}% hit {sum(1 for i,s,_ in ev if -s*math.log(cl[i+h]/cl[i])>0)/len(ev)*100:.0f}% t={tstat([-s*math.log(cl[i+h]/cl[i]) for i,s,_ in ev]):.1f}"
            for h in (15,30,60,120,240)))
        if thr==0.015:
            print("   individual events (UTC), move, then fade return at 30m / 60m / 240m:")
            for i,s,r in ev:
                print(f"     {dt.datetime.fromtimestamp(ts[i],dt.timezone.utc):%m-%d %H:%M}  {r*100:+.2f}%   {-s*math.log(cl[i+30]/cl[i])*100:+.2f}% / {-s*math.log(cl[i+60]/cl[i])*100:+.2f}% / {-s*math.log(cl[i+240]/cl[i])*100:+.2f}%")
    # direction split for 4-sigma 5-min events with volume, naive entry
    W=1440; sd=[0.0]*n; s=0.0; ss=0.0
    for i in range(n):
        s+=lr[i]; ss+=lr[i]**2
        if i>=W: s-=lr[i-W]; ss-=lr[i-W]**2
        if i>=W-1: m=s/W; sd[i]=math.sqrt(max(ss/W-m*m,1e-18))
    medv=[0.0]*n; cur=0.0
    for i in range(n):
        if i>=W and i%60==0: cur=sorted(vol[i-W:i])[W//2]
        medv[i]=cur
    ev=[]; last=-10**9
    for i in range(W+5,n-120):
        r5=sum(lr[i-4:i+1]); v5=sum(vol[i-4:i+1]); thr=4*sd[i-5]*math.sqrt(5)
        if medv[i]>0 and abs(r5)>=thr and v5>=3*5*medv[i] and i-last>=60: ev.append((i,1 if r5>0 else -1)); last=i
    for label, sgn in (("DOWN moves (fade = buy)",-1),("UP moves (fade = sell)",1)):
        sub=[i for i,s in ev if s==sgn]
        print(f"   4-sigma 5m events, {label}: N={len(sub)}  " + "  ".join(
            f"{h}m: {st.mean([-sgn*math.log(cl[i+h]/cl[i]) for i in sub])*100:+.3f}% (hit {sum(1 for i in sub if -sgn*math.log(cl[i+h]/cl[i])>0)/len(sub)*100:.0f}%, t={tstat([-sgn*math.log(cl[i+h]/cl[i]) for i in sub]):.1f})" for h in (5,15,60)))
    # time-of-day: US hours (13:00-21:00 UTC) vs rest
    for label, f in (("US hours 13-21 UTC", lambda h: 13<=h<21), ("other hours", lambda h: not (13<=h<21))):
        sub=[(i,s) for i,s in ev if f(dt.datetime.fromtimestamp(ts[i],dt.timezone.utc).hour)]
        print(f"   4-sigma 5m events, {label}: N={len(sub)}  " + "  ".join(
            f"{h}m: {st.mean([-s*math.log(cl[i+h]/cl[i]) for i,s in sub])*100:+.3f}% (t={tstat([-s*math.log(cl[i+h]/cl[i]) for i,s in sub]):.1f})" for h in (5,15,60)))
    # realized vol regime by week (annualized), to show what regime this sample is
    print("   weekly annualized vol: " + " ".join(f"{st.pstdev(lr[i:i+10080])*math.sqrt(525600)*100:.0f}%" for i in range(0, n-10080, 10080)))
