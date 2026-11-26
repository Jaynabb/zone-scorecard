# split_trend_backtest.py on the indicator's exact zones (jay_sd_lab.pine exports, lab_candidates.pkl from
# lab_backtest.py). Touch GO as v233: first visit (purity 4), Mid trend score 4, 9 EMA with the zone, not a reaction,
# retired or superseded zone. The lab chart is the entry timeframe, so the Low trend is trend_pack ported
# (split_trend_backtest.trend_pack) run on the exported candles, read on the candle before the touch.
#   SPLIT: Low trend against the zone (what the change would drop)   AGREE: Low trend with it or range
# Exits: the indicator's stop (a tenth past the far edge) to the opposing zone (Z2Z), fixed 1R / 2R, and the 9 EMA exit.
# Usage: python split_trend_lab.py <lab dir with SYMBOL_Style.csv and lab_candidates.pkl>
import sys, os, numpy as np, pandas as pd
D = sys.argv[1]
src = open(__file__.replace("split_trend_lab.py", "split_trend_backtest.py")).read()
g = {"np": np}; exec("ZL, ZR = 10, 2\ndef trend_pack" + src.split("\ndef trend_pack")[1].split("\ndef on_low")[0], g)
trend_pack = g["trend_pack"]
df = pd.read_pickle(os.path.join(D, "lab_candidates.pkl"))
df = df[(df.et == "TOUCH") & (df.pur == 4) & (df.trend == 4) & (df.ema == 1) & ~df.rr & ~df.retired & ~df.sup_].copy()
low = {}
for (sym, style) in df[["sym", "style"]].drop_duplicates().itertuples(index=False):
    x = pd.read_csv(os.path.join(D, f"{sym}_{style}.csv"))
    st, _, _ = trend_pack(x.h.values, x.l.values, x.c.values)
    low[(sym, style)] = (x.t.values, st)
def low_at(r):
    t, st = low[(r.sym, r.style)]; j = np.searchsorted(t, r.t)
    return st[j - 1] if j >= 1 else 0
df["low"] = df.apply(low_at, axis=1)
df["d"] = np.where(df.side == "s", -1, 1)
df["grp"] = np.where(df.low == -df.d, "SPLIT", "AGREE")
EX = [("Z0.1", "to opposing zone"), ("R1", "1R"), ("R2", "2R"), ("EMA9", "9 EMA exit")]
def row(name, s):
    out = f"    {name:6s} {len(s):5d}"
    for k, _ in EX:
        v = s[k].dropna(); out += f" | {k:4s} win {np.mean(v > 0) * 100:4.1f}% avg {v.mean():+.2f}R"
    return out
for style in ("Scalping", "Day", "Swing", "Longer"):
    s0 = df[df.style == style]
    if not len(s0): continue
    print(f"\n#### {style}  ({', '.join(sorted(s0.sym.unique()))})")
    for grp in ("AGREE", "SPLIT"): print(row(grp, s0[s0.grp == grp]))
    for h in (0, 1):
        sh = s0[s0.half == h]; print(f"  {'first' if h == 0 else 'second'} half of the data")
        for grp in ("AGREE", "SPLIT"): print(row(grp, sh[sh.grp == grp]))
    u = s0[s0.sym == "US30"]
    if len(u):
        print("  US30 only")
        for grp in ("AGREE", "SPLIT"): print(row(grp, u[u.grp == grp]))
