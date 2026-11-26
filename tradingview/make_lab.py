# Builds jay_sd_lab.pine: the indicator unchanged, plus an export of every entry timeframe zone visit as it happens
# (visit start, first close inside, close back out) with the zone, its score at that moment, purity, trend, EMA signal
# and the opposing zone target the indicator would use. Plots are hidden (data window only); lab_export.js reads them
# with the chart's own candles so lab_backtest.py can replay the trades with the indicator's exact zones.
# Usage: python make_lab.py   (writes jay_sd_lab.pine next to jay_sd.pine)
import re, os
here = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(here, "jay_sd.pine")).read()
s = s.replace('indicator("Jay S&D",', 'indicator("Jay S&D Lab",', 1)
old = "    float chk = na        //"
assert s.count(old) == 1
s = s.replace(old, "    int lab_tc = 0        // lab: touches already reported\n" + old, 1)
s += r'''

//-----------------------------------------------------------------------------
// LAB EXPORT (jay_sd_lab.pine only, built by make_lab.py)
//-----------------------------------------------------------------------------
// nearest opposing zone ahead of the edge, the indicator's order: entry timeframe (not a reaction, retired or
// superseded), else Mid, else High
lab_opp(bool is_supply, float edge) =>
    float best = na
    for s2 = 0 to 2
        array<Zone> oa = s2 == 0 ? (is_supply ? dem_d : sup_d) : s2 == 1 ? (is_supply ? dem_w : sup_w) : (is_supply ? dem_m : sup_m)
        if oa.size() > 0
            for q = 0 to oa.size() - 1
                Zone oz = oa.get(q)
                if not (s2 == 0 and (oz.rr or oz.retired or superseded(oa, q)))
                    float ne = is_supply ? oz.b.get_top() : oz.b.get_bottom()
                    if (is_supply ? ne < edge : ne > edge) and (na(best) or (is_supply ? ne > best : ne < best))
                        best := ne
        if not na(best)
            break
    best

// event bits: 1 a visit started this bar, 2 first close inside on this visit, 4 close back out
lab_scan(array<Zone> zs) =>
    int ev = 0
    int idx = -1
    if zs.size() > 0
        for i = 0 to zs.size() - 1
            Zone z = zs.get(i)
            int e = 0
            if z.ct == time
                z.lab_tc := z.touches
            else
                if z.touches > z.lab_tc
                    e += 1
                if z.zc_t == time
                    e += 2
                if z.x_t == time
                    e += 4
                z.lab_tc := z.touches
            if e > 0 and idx < 0
                ev := e
                idx := i
    [ev, idx]

lab_pack(array<Zone> zs, bool is_supply, int ev, int idx) =>
    float o_top = na
    float o_btm = na
    float o_vis = na
    float o_pur = na
    float o_sc = na
    float o_tr = na
    float o_ema = na
    float o_zc = na
    float o_x = na
    float o_tgt = na
    float o_fl = na
    float o_ext = na
    if ev > 0
        flag_reactions(zs, is_supply, 0)
        Zone z = zs.get(idx)
        [r_top, r_btm, r_top_nm, r_btm_nm, r_top_t, r_btm_t] = range_levels()
        [tot, a1, a2, a3, a4, a5, a6, a7, rr, mr, rp, onm, spl] = score_zone(z, is_supply, r_top, r_btm, na, "")
        [en, et] = ema_conf(z, is_supply)
        o_top := z.b.get_top()
        o_btm := z.b.get_bottom()
        o_vis := z.touches
        o_pur := purity_of(z, true)
        o_sc := tot - a6
        o_tr := a3
        o_ema := en
        o_zc := ev % 4 >= 2 ? z.zc_px : na
        o_x := ev >= 4 ? z.x_px : na
        o_tgt := lab_opp(is_supply, is_supply ? o_btm : o_top)
        o_fl := (z.rr ? 1 : 0) + (z.retired ? 2 : 0) + (superseded(zs, idx) ? 4 : 0) + (z.gap_out ? 8 : 0) + (z.os ? 16 : 0)
        o_ext := mr
    [o_top, o_btm, o_vis, o_pur, o_sc, o_tr, o_ema, o_zc, o_x, o_tgt, o_fl, o_ext]

[lab_sev, lab_si] = lab_scan(sup_d)
[lab_dev, lab_di] = lab_scan(dem_d)
[s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12] = lab_pack(sup_d, true, lab_sev, lab_si)
[d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, d11, d12] = lab_pack(dem_d, false, lab_dev, lab_di)
plot(lab_sev > 0 ? lab_sev : na, "LAB s ev", display=display.data_window)
plot(s1, "LAB s top", display=display.data_window)
plot(s2, "LAB s btm", display=display.data_window)
plot(s3, "LAB s vis", display=display.data_window)
plot(s4, "LAB s pur", display=display.data_window)
plot(s5, "LAB s score", display=display.data_window)
plot(s6, "LAB s trend", display=display.data_window)
plot(s7, "LAB s ema", display=display.data_window)
plot(s8, "LAB s zc", display=display.data_window)
plot(s9, "LAB s x", display=display.data_window)
plot(s10, "LAB s tgt", display=display.data_window)
plot(s11, "LAB s flags", display=display.data_window)
plot(s12, "LAB s move", display=display.data_window)
plot(lab_dev > 0 ? lab_dev : na, "LAB d ev", display=display.data_window)
plot(d1, "LAB d top", display=display.data_window)
plot(d2, "LAB d btm", display=display.data_window)
plot(d3, "LAB d vis", display=display.data_window)
plot(d4, "LAB d pur", display=display.data_window)
plot(d5, "LAB d score", display=display.data_window)
plot(d6, "LAB d trend", display=display.data_window)
plot(d7, "LAB d ema", display=display.data_window)
plot(d8, "LAB d zc", display=display.data_window)
plot(d9, "LAB d x", display=display.data_window)
plot(d10, "LAB d tgt", display=display.data_window)
plot(d11, "LAB d flags", display=display.data_window)
plot(d12, "LAB d move", display=display.data_window)
'''
open(os.path.join(here, "jay_sd_lab.pine"), "w").write(s)
print("ok", len(s.splitlines()), "lines")
