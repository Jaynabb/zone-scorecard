# Pause candle anywhere in the base's run (Jay, BTC 5M 2026-11-26 16:40-16:45 supply that was not drawn): today a base
# needs a pause candle (body under half its range) from the turn on; the run of side by side candles before the turn is
# cut off first. 'check' lets a pause anywhere in the run count, 'extend' also stretches the base back to that pause.
# Zones from zone_struct.py on the lab candles; the zones a variant adds over the current rule are traded on their first
# touch (limit at the near edge, stop a tenth past the far edge, 2R / 3R; a candle hitting both is a loss) next to the
# zones the current rule already draws. Usage: python pause_run_backtest.py <lab dir>
import sys, os, glob, numpy as np, pandas as pd
D = sys.argv[1]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "zone_struct.py")).read()
g = {"__name__": "zs", "__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "zone_struct.py")}; exec(src, g)
zones = g["zones"]

def first_touch(df, z, rr):
    o, h, l, c = (df[k].values for k in "ohlc"); sup = z["sup"]; d = -1 if sup else 1
    near, far = (z["btm"], z["top"]) if sup else (z["top"], z["btm"]); hgt = z["top"] - z["btm"]
    if hgt <= 0: return None
    stop = far - d * 0.1 * hgt
    i = int(df.index[df.dt == z["imp"]][0])
    for j in range(i + 1, min(i + 500, len(c))):
        if (l[j] <= near) if d == 1 else (h[j] >= near):
            e = near if (o[j] - near) * d > 0 else o[j]
            risk = (e - stop) * d
            if risk <= 0: return None
            tgt = e + d * rr * risk
            for q in range(j, min(j + 500, len(c))):
                if ((l[q] <= stop) if d == 1 else (h[q] >= stop)): return -1.0
                if ((h[q] >= tgt) if d == 1 else (l[q] <= tgt)): return float(rr)
            return None
        if (c[j] - far) * d < 0: return None
    return None

def f(v):
    v = np.array(v)
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R" if len(v) else "    0 trades"
for sub, style in (("scalp", "Scalping"), ("day", "Day")):
    res = {}
    for fpath in sorted(glob.glob(os.path.join(D, sub, f"*_{style}.csv"))):
        df = pd.read_csv(fpath)[["t", "o", "h", "l", "c"]].reset_index(drop=True)
        df["dt"] = pd.to_datetime(df.t, unit="s", utc=True)
        base = {(z["sup"], z["t0"], z["imp"]) for z in zones(df)}
        for v in (None, "check", "extend"):
            for z in zones(df, pause_run=v):
                grp = "current" if v is None else (v + " adds") if (z["sup"], z["t0"], z["imp"]) not in base else None
                if grp is None and v == "extend":
                    continue
                if grp is None: continue
                for rr in (2, 3):
                    r = first_touch(df, z, rr)
                    if r is not None: res.setdefault((grp, rr), []).append(r)
    print(f"\n=== {style} ({sub}) ===")
    for grp in ("current", "check adds", "extend adds"):
        print(f"  {grp:12s} 2R {f(res.get((grp, 2), []))} | 3R {f(res.get((grp, 3), []))}")
