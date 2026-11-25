import statistics
raw="""2023-07,70.385,81.955,69.735,81.715;2023-08,81.685,84.845,77.635,83.535;2023-09,83.535,94.985,83.505,90.705;2023-10,90.785,91.835,80.785,81.305;2023-11,81.425,83.555,72.215,75.565;2023-12,75.535,76.725,67.74,71.293;2024-01,72.14,79.245,69.31,75.778;2024-02,75.885,79.58,71.43,78.228;2024-03,78.255,83.17,76.82,83.058;2024-04,83.295,87.6,80.74,81.433;2024-05,81.385,81.53,76.18,77.118;2024-06,77.115,82.68,72.43,81.437;2024-07,81.44,84.485,74.635,78.545;2024-08,78.515,80.125,71.49,73.588;2024-09,73.8,74.255,65.29,68.233;2024-10,68.34,78.42,66.365,70.453;2024-11,70.44,72.84,66.587,68.11;2024-12,68.05,71.98,67.005,71.812;2025-01,71.785,80.73,71.785,73.753;2025-02,74.75,75.14,68.39,69.918;2025-03,70.035,71.8,65.25,71.323;2025-04,71.355,72.218,55.145,58.165;2025-05,58.256,64.141,55.391,60.675;2025-06,61.546,77.566,61.546,64.92;2025-07,64.906,70.51,64.691,69.35;2025-08,69.35,69.58,61.45,64;2025-09,63.95,66.42,61.45,62.42;2025-10,62.46,62.92,55.96,60.87;2025-11,61.4,61.5,57.1,58.47;2025-12,58.96,60.5,54.98,57.4;2026-01,57.41,66.48,55.76,65.73;2026-02,64.72,67.83,61.12,67.28;2026-03,75,119.48,69.2,101.55;2026-04,101.72,117.63,78.97,105.4;2026-05,105.14,107.46,86.35,87.75;2026-06,88.5,97,68.56,70.02;2026-07,69.98,93.5,67.04,86.79;2026-08,80.1,87.69,74.24,86.3;2026-09,86.31,106.75,86.13,90.33;2026-10,90.4,104.99,86.86,102.94;2026-11,102.39,102.75,79.07,81.69"""
B=[r.split(',') for r in raw.split(';')]
T=[b[0] for b in B]; O=[float(b[1]) for b in B]; H=[float(b[2]) for b in B]; L=[float(b[3]) for b in B]; C=[float(b[4]) for b in B]
def detect(sup, idx, base_max=10, base_mult=0.5):
    # idx = index of impulse candle; offsets go to idx-j
    yard=statistics.median([abs(C[i]-O[i]) for i in range(idx-19, idx+1)])
    body=abs(C[idx]-O[idx]); away = C[idx]<O[idx] if sup else C[idx]>O[idx]
    pt=max(O[idx-1],C[idx-1]); pb=min(O[idx-1],C[idx-1]); mg=yard*0.1
    gap=max(pb-O[idx],0) if sup else max(O[idx]-pt,0); gap=gap if gap>mg else 0
    drive=(body+gap) if away else gap
    if drive<yard: return 'no impulse'
    lim=drive*base_mult; legs=0; cnt=0; alo=ahi=None
    j=0
    while j < base_max+4:
        j+=1
        if cnt>=base_max: break
        o=idx-j
        legc = (C[o]<O[o] and C[o]<L[o-1]) if sup else (C[o]>O[o] and C[o]>H[o-1])
        legp = (C[o-1]<O[o-1] and C[o-1]<L[o-2]) if sup else (C[o-1]>O[o-1] and C[o-1]>H[o-2])
        tiny = abs(C[o]-O[o]) <= 0.25*yard
        if cnt==0 and legs<4 and (legc or (legs>0 and tiny and legp)):
            legs+=1; drive+=abs(C[o]-O[o]); lim=drive*base_mult; continue
        bd=abs(C[o]-O[o]); bh=max(O[o],C[o]); bl=min(O[o],C[o]); rg=H[o]-L[o]
        bal = rg>0 and bd<=rg*0.5 and bd<=drive
        if bd>lim and not (j==1+legs and gap>0) and not bal: break
        if cnt>0 and (O[o+1]>H[o]+mg or O[o+1]<L[o]-mg): break
        if cnt>0 and (bh<alo or bl>ahi): break
        alo=L[o] if alo is None else min(alo,L[o]); ahi=H[o] if ahi is None else max(ahi,H[o]); cnt+=1
    if cnt==0: return 'no base'
    js=list(range(legs+1,legs+cnt+1))
    if cnt>=2:
        ext=None; tj=js[0]
        for jj in js:
            o=idx-jj; bb=max(O[o],C[o]) if sup else min(O[o],C[o])
            if ext is None or (bb>ext if sup else bb<ext): ext=bb; tj=jj
        o3=idx-tj
        arr = (C[o3-1]>O[o3-1] and max(O[o3-1],C[o3-1])<ext) if sup else (C[o3-1]<O[o3-1] and min(O[o3-1],C[o3-1])>ext)
        if arr and tj<legs+cnt: cnt=tj-legs; js=list(range(legs+1,legs+cnt+1))
    blo=min(min(O[idx-j],C[idx-j]) for j in js); bhi=max(max(O[idx-j],C[idx-j]) for j in js)
    wext=max(H[idx-j] for j in js) if sup else min(L[idx-j] for j in js)
    far=wext
    if cnt>=2:
        thr=0.5*max(bhi-blo,yard); cand=[ (H[idx-j] if sup else L[idx-j]) for j in js if ((H[idx-j]-bhi) if sup else (blo-L[idx-j]))<=thr]
        far=(max(cand) if sup else min(cand)) if cand else (bhi if sup else blo)
    top,btm=(far,blo) if sup else (bhi,far)
    return f"legs {legs} base {[T[idx-j] for j in js]} zone {btm:.2f}-{top:.2f}"
print("demand, impulse 2026-03:", detect(False, T.index('2026-03')))
print("supply, impulse 2026-05:", detect(True, T.index('2026-05')))
print("demand, impulse 2025-06:", detect(False, T.index('2025-06')))
