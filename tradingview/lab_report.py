# Reads lab_candidates.pkl (lab_backtest.py) and prints: the indicator as it is (proper entry, valid setups, one and done
# on Scalping, one trade at a time per symbol), then the rules bent one at a time, then a search for 75% win rate setups
# that also make money in both halves of the history.
# Usage: python lab_report.py <dir> [style]
import sys, os, itertools, numpy as np, pandas as pd
D = sys.argv[1]; ONLY = sys.argv[2] if len(sys.argv) > 2 else None
df = pd.read_pickle(os.path.join(D, "lab_candidates.pkl"))
EX = ["Z0", "Z0.1", "Z0.5", "Z1", "Z2", "Z3", "T1", "T2", "T3", "P33", "P50", "P75", "R1", "R2", "EMA9"]

def one_at_a_time(x, col):
    # a new setup on a symbol waits until the open trade on that symbol has closed
    out = []
    for sym, g in x.sort_values("t").groupby("sym"):
        busy = -1
        for i, r in g.iterrows():
            if r.t >= busy and not np.isnan(r[col]):
                out.append(i); busy = r["x_" + col]
    return x.loc[out]

def stat(x, col):
    r = x[col].dropna()
    if len(r) == 0: return "   no trades"
    a = x[x.half == 0][col].dropna(); b = x[x.half == 1][col].dropna()
    return (f"{len(r):5d} trades | win {(r > 0).mean() * 100:4.0f}% ({(a > 0).mean() * 100:3.0f}/{(b > 0).mean() * 100:3.0f})"
            f" | avg {r.mean():+.2f}R ({a.mean():+.2f}/{b.mean():+.2f}) | total {r.sum():+7.1f}R")

for style in df["style"].unique():
    if ONLY and style != ONLY: continue
    s = df[df["style"] == style]
    print(f"\n######## {style}  ({', '.join(sorted(s.sym.unique()))})")
    base = s[s.proper & s.valid]
    if style == "Scalping": base = base[base.vis == 1]
    print("  THE INDICATOR AS IT IS (proper entry type, valid score, target = opposing zone)")
    for col in EX: print(f"    {col:5s} {stat(one_at_a_time(base, col), col)}")
    print("  BENDING ONE RULE (stop at the far edge + 0.1, and the 9 EMA exit)")
    bends = {
        "any entry type (all 3 on every valid visit)": s[s.valid],
        "Touch only": s[s.valid & (s.et == "TOUCH")],
        "Zone only": s[s.valid & (s.et == "ZONE")],
        "Exit only": s[s.valid & (s.et == "EXIT")],
        "no EMA rule": s[s.proper & ~s.rr & ~s.retired & ~s.sup_ & (s.score >= (16 if style == "Scalping" else 14))],
        "score >= 12": s[s.proper & ~s.rr & ~s.retired & ~s.sup_ & (s.score >= 12) & ((s.ema == 1) | (style != "Scalping"))],
        "score >= 16": s[s.proper & s.valid & (s.score >= 16)],
        "score >= 18": s[s.proper & s.valid & (s.score >= 18)],
        "with trend only": s[s.proper & s.valid & (s.trend == 4)],
        "target within 3 zone heights": s[s.proper & s.valid & (s.dist_h <= 3)],
        "target 3+ zone heights away": s[s.proper & s.valid & (s.dist_h >= 3)],
        "reaction / retired zones allowed": s[s.proper & (s.score >= (16 if style == "Scalping" else 14)) & ((s.ema == 1) | (style != "Scalping"))],
    }
    for k, x in bends.items():
        if style == "Scalping" and k not in ("reaction / retired zones allowed",): x = x[x.vis == 1]
        print(f"    {k:40s} Z0.1 {stat(one_at_a_time(x, 'Z0.1'), 'Z0.1')}")
        print(f"    {'':40s} EMA9 {stat(one_at_a_time(x, 'EMA9'), 'EMA9')}")
    # 75% search
    out = []
    F = dict(et=["proper", "TOUCH", "ZONE", "EXIT"], sc=[0, 12, 14, 16, 18], ema=[0, 1], tr=[0, 4], dmax=[99, 5, 3, 2], first=[0, 1])
    for et, sc, em, tr, dm, fi in itertools.product(*F.values()):
        m = (s.proper if et == "proper" else s.et == et) & ~s.rr & ~s.sup_ & (s.score >= sc) & ((s.ema == 1) | (em == 0)) & (s.trend >= tr) & (s.dist_h <= dm) & ((s.vis == 1) | (fi == 0))
        x = s[m]
        for col in EX:
            a = x[x.half == 0][col].dropna(); b = x[x.half == 1][col].dropna()
            if len(a) < 25 or len(b) < 25: continue
            out.append(dict(et=et, score=sc, ema=em, trend=tr, dmax=dm, first=fi, exit=col, n=len(a) + len(b),
                            win=(pd.concat([a, b]) > 0).mean(), wa=(a > 0).mean(), wb=(b > 0).mean(), avg=pd.concat([a, b]).mean(), aa=a.mean(), ab=b.mean()))
    R = pd.DataFrame(out)
    if len(R):
        ok = R[(R.wa >= 0.75) & (R.wb >= 0.75) & (R.aa > 0) & (R.ab > 0)].sort_values("avg", ascending=False)
        print(f"  75% WIN SEARCH: {len(ok)} of {len(R)} combos have >= 75% wins and make money in both halves")
        print(ok.head(10).round(2).to_string(index=False))
        best = R[(R.aa > 0) & (R.ab > 0) & (R.n >= 60)].sort_values("avg", ascending=False)
        print("  BEST BY PROFIT (both halves positive, 60+ trades)")
        print(best.head(8).round(2).to_string(index=False))
