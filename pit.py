import glob, sys
import pandas as pd
f = glob.glob("**/*시총*.csv", recursive=True)
print("FOUND FILES:", f[:5])
if not f: sys.exit("no mcap csv found")
p = f[0]
d = None
for enc in ("utf-8","cp949","utf-8-sig","euc-kr"):
    try:
        d = pd.read_csv(p, dtype=str, encoding=enc); print("ENCODING:", enc); break
    except UnicodeDecodeError: pass
print("FILE:", p)
print("ROWS:", len(d), "COLS:", list(d.columns))
print(d.head(3).to_string())
def g(hs):
    for h in hs:
        for c in d.columns:
            if h in str(c).lower(): return c
dc, cc, mc = g(["date","ym","일자","날짜","기준"]), g(["code","종목","ticker"]), g(["mcap","시총","cap"])
print("GUESS date=%s code=%s mcap=%s" % (dc, cc, mc))
d[cc] = d[cc].astype(str).str.zfill(6)
d[mc] = pd.to_numeric(d[mc], errors="coerce")
t = pd.to_datetime(d[dc], errors="coerce", format="mixed")
d["ym"] = t.dt.strftime("%Y-%m")
ys = sorted(d["ym"].dropna().unique())
print("PERIOD:", ys[0], "~", ys[-1], "| points:", len(ys))
MOD = {"035720":"KAKAO","373220":"LGES","207940":"SBL","247540":"ECOPRO-BM",
       "086520":"ECOPRO","323410":"KBANK","259960":"KRAFTON","302440":"SKBS",
       "326030":"SKBP","091990":"CELLTRION-H","196170":"ALTEOGEN"}
OLD = {"005930":"SamsungElec","015760":"KEPCO","017670":"SKT","005490":"POSCO","005380":"HyundaiMotor"}
for tgt in [x for x in ("1999-12","2004-12","2009-12") if x in ys][:3] or ys[:2]:
    s = d[(d["ym"]==tgt) & d[mc].notna()].nlargest(30, mc)
    print("\n=== TOP30 @", tgt, "===")
    bad = []
    for i,(_,r) in enumerate(s.iterrows(),1):
        tag = "  <<< FUTURE " + MOD[r[cc]] if r[cc] in MOD else ("  ok " + OLD[r[cc]] if r[cc] in OLD else "")
        if r[cc] in MOD: bad.append(MOD[r[cc]])
        print("%2d %s %18.0f%s" % (i, r[cc], r[mc], tag))
    print("VERDICT:", ("!!! LOOKAHEAD - future tickers: " + ",".join(bad)) if bad else "clean")
last = ys[-1]
alive = set(d.loc[d["ym"]==last, cc]); ever = set(d[cc]); dead = ever - alive
print("\nDELISTED CHECK: total %d, alive %d, dead %d (%.1f%%)" % (len(ever), len(alive), len(dead), 100*len(dead)/len(ever)))
print("VERDICT:", "!!! SURVIVORSHIP BIAS" if len(dead)/len(ever) < 0.05 else "ok")
sam = d[d[cc]=="005930"].dropna(subset=[mc]).sort_values("ym")
print("\nSAMSUNG MCAP uniq values:", sam[mc].nunique())
print("VERDICT:", "!!! CONSTANT = BACKFILLED" if sam[mc].nunique() <= 2 else "ok, varies over time")
