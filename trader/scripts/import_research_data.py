"""Import the research JSON candle files into the bar store: python scripts/import_research_data.py --dir /path/to/data"""
import argparse, glob, os, re
from common import *
ap = argparse.ArgumentParser(); ap.add_argument("--dir", required=True); a = ap.parse_args()
store = BarStore(state_dir() / "bars.db")
for path in sorted(glob.glob(os.path.join(a.dir, "*_3600s_*.json"))):
    sym = os.path.basename(path).split("_3600s_")[0]; n = store.import_json(sym, path); print(f"{sym}: {n} bars from {os.path.basename(path)}")
print("done; symbols in store:", store.con.execute("SELECT COUNT(DISTINCT symbol) FROM bars").fetchone()[0])
