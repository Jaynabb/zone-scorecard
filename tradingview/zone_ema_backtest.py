# Zone + EMA backtest: does a zone entry need the retest once the EMA candle has printed?
# Zones follow the Jay S&D defaults in simplified form (impulse >= 1 typical body, base of up to 4 candles
# each <= 0.5 x impulse body, zone height <= 4 typical bodies, price must travel 1 zone height away within 8 candles,
# a zone dies on a close through its far edge). Only fresh zones (first retest) are traded. The 20 point score is
# not modelled. Usage: python zone_ema_backtest.py <datadir> <interval>
import sys, numpy as np, pandas as pd
DATA, IV = sys.argv[1], sys.argv[2]
SYMS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "NQ"]
EMAS = (9, 21, 50)
MAXB = 120 if IV == "1d" else 288      # trade time limit: about 6 months of days / one day of 5m candles

def load(s):
    df = pd.read_csv(f"{DATA}/{s}_{IV}.csv", index_col=0, parse_dates=True)[["Open", "High", "Low", "Close"]].dropna()
    return df[df.High > df.Low]

def zones(o, h, l, c, yard):
    out = []   # (created_bar, is_supply, top, btm)
    body = np.abs(c - o)
    for i in range(25, len(c) - 8):
        imp = body[i]
        if not yard[i] > 0 or imp < yard[i]:
            continue
        up = c[i] > o[i]
        n = 0
        j = i - 1
        while j >= 0 and n < 4 and body[j] <= 0.5 * imp:
            n += 1; j -= 1
        if n == 0:
            continue
        b0, b1 = i - n, i - 1
        if up:
            btm = l[b0:b1 + 1].min(); top = np.maximum(o, c)[b0:b1 + 1].max()
        else:
            top = h[b0:b1 + 1].max(); btm = np.minimum(o, c)[b0:b1 + 1].min()
        hgt = top - btm
        if hgt <= 0 or hgt > 4 * yard[i]:
            continue
        # departure: within 8 candles price travels one zone height beyond the near edge
        k_end = min(i + 8, len(c) - 1)
        if up:
            ok = h[i:k_end + 1].max() >= top + hgt
        else:
            ok = l[i:k_end + 1].min() <= btm - hgt
        if not ok:
            continue
        # the zone becomes known on the departure candle
        k = next(k for k in range(i, k_end + 1) if (h[k] >= top + hgt if up else l[k] <= btm - hgt))
        out.append((k, not up, top, btm))
    return out

def sim(h, l, c, start, entry, stop, target, d, fill_bar_checks=True):
    # returns R multiple; a candle touching both stop and target counts as a loss
    risk = (entry - stop) * d
    if risk <= 0:
        return None
    for j in range(start, min(start + MAXB, len(c))):
        hit_s = l[j] <= stop if d == 1 else h[j] >= stop
        hit_t = h[j] >= target if d == 1 else l[j] <= target
        if hit_s:
            return -1.0
        if hit_t:
            return (target - entry) * d / risk
    return None

def run():
    res = {k: [] for k in ("A_retest_ema", "B_ema_candle", "B2_ema_candle_2R", "C_retest_no_ema", "D_retest_ema_against")}
    for s in SYMS:
        df = load(s)
        o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
        yard = pd.Series(np.abs(c - o)).rolling(20).median().values
        em = np.vstack([df.Close.ewm(span=p, adjust=False).mean().values for p in EMAS])
        up = l > em.max(0); dn = h < em.min(0)
        sig = np.zeros(len(c), int); st = 0
        for i in range(1, len(c)):
            if up[i] and not up[i - 1]: st = 1
            if dn[i] and not dn[i - 1]: st = -1
            sig[i] = st                      # signal standing after candle i closes
        buy_bar = np.zeros(len(c), bool); sell_bar = np.zeros(len(c), bool)
        buy_bar[1:] = up[1:] & ~up[:-1]; sell_bar[1:] = dn[1:] & ~dn[:-1]
        for (k, sup, top, btm) in zones(o, h, l, c, yard):
            if k < 60:
                continue
            d = -1 if sup else 1
            near, far = (btm, top) if sup else (top, btm)
            hgt = top - btm
            stop = far + d * -0.1 * hgt      # a tenth of the zone beyond the far edge
            target = near + d * 2 * abs(near - stop)   # 2R from the zone edge
            # walk forward until the first retest or the zone dies
            fired_b = False
            for j in range(k + 1, min(k + 1 + MAXB * 2, len(c))):
                # zone dies on a close through the far edge
                # B: EMA candle in the trade's direction while the zone is alive and untested, entry at its close
                if not fired_b and ((d == 1 and buy_bar[j]) or (d == -1 and sell_bar[j])) and (c[j] - near) * d > 0:
                    fired_b = True
                    r = sim(h, l, c, j + 1, c[j], stop, target, d)
                    if r is not None: res["B_ema_candle"].append(r)
                    r2 = sim(h, l, c, j + 1, c[j], stop, c[j] + d * 2 * abs(c[j] - stop), d)
                    if r2 is not None: res["B2_ema_candle_2R"].append(r2)
                touched = l[j] <= near if d == 1 else h[j] >= near
                if touched:
                    entry = near if (o[j] - near) * d > 0 else o[j]
                    if (entry - stop) * d <= 0:
                        break
                    # stop and target checked from the entry candle on (conservative)
                    r = sim(h, l, c, j, entry, stop, target, d)
                    if r is not None:
                        res["C_retest_no_ema"].append(r)
                        if sig[j - 1] == d: res["A_retest_ema"].append(r)
                        elif sig[j - 1] == -d: res["D_retest_ema_against"].append(r)
                    break
                if (c[j] - far) * d < 0:
                    break
    return res

r = run()
names = {"A_retest_ema": "A  Retest, EMA agrees (current v84 rule)",
         "B_ema_candle": "B  Enter on the EMA candle, zone stop, same target",
         "B2_ema_candle_2R": "B2 Enter on the EMA candle, zone stop, 2R target",
         "C_retest_no_ema": "C  Retest, ignore EMA",
         "D_retest_ema_against": "D  Retest, EMA against"}
print(f"\n=== {IV} | {', '.join(SYMS)} | EMAs {EMAS} ===")
for k, v in r.items():
    v = np.array(v)
    if len(v) == 0:
        print(f"{names[k]:55s} no trades"); continue
    print(f"{names[k]:55s} trades {len(v):4d} | win {np.mean(v > 0) * 100:5.1f}% | avg R {v.mean():+.2f} | total R {v.sum():+.1f}")
