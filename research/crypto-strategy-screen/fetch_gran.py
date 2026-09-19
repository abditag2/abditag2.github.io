import json, time, urllib.request, datetime as dt, sys, os
BASE = "https://api.exchange.coinbase.com"
def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "research/0.1"})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())
        except Exception as e:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("failed " + path)
product, s, e, gran = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
out_path = f"data/{product}_{gran}s_{s}_{e}.json"
if os.path.exists(out_path): print("cached", out_path); sys.exit(0)
start_dt = dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc); end = dt.datetime.fromisoformat(e).replace(tzinfo=dt.timezone.utc)
out = {}; n = 0
while end > start_dt:
    start = end - dt.timedelta(seconds=gran * 300)
    for t, lo, hi, op, cl, vol in get(f"/products/{product}/candles?granularity={gran}&start={start.isoformat()}&end={end.isoformat()}"):
        out[t] = [lo, hi, op, cl, vol]
    end = start; n += 1; time.sleep(0.25)
ks = sorted(out)
os.makedirs("data", exist_ok=True)
json.dump([[k] + out[k] for k in ks], open(out_path, "w"))
print(f"{product} gran={gran}: {len(ks)} bars, {n} requests, first {dt.datetime.fromtimestamp(ks[0], dt.timezone.utc):%Y-%m-%d} last {dt.datetime.fromtimestamp(ks[-1], dt.timezone.utc):%Y-%m-%d}")
