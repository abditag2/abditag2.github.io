import portfolio as P
NEW16 = "ZRX-USD,BAT-USD,ZEC-USD,EOS-USD,DASH-USD,OMG-USD,KNC-USD,COMP-USD,MKR-USD,SNX-USD,YFI-USD,GRT-USD,CRV-USD,MANA-USD,SAND-USD,AXS-USD".split(",")
D16 = P.prepare(NEW16); print("16 coins never used in any selection:", D16["coins"])
P.row("M9 vt30 K=20 long-only", P.simulate(D16, long_only=True, K=20, r3_vt=0.30))
P.row("M10 vt30 K=15 long-only", P.simulate(D16, long_only=True, K=15, r3_vt=0.30))
P.row("vt25 K=25 long-only (lowest-risk cell)", P.simulate(D16, long_only=True, K=25, r3_vt=0.25))
P.row("R3 vt30 only", P.simulate(D16, K=0, r3_vt=0.30))
P.row("B* K=20 long-only only", P.simulate(D16, use_r3=False, long_only=True, K=20))
P.row("buy&hold-ish: R3 vt99 long-only", P.simulate(D16, K=0, r3_vt=9.9))
