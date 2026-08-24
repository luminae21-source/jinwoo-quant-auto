# -*- coding: utf-8 -*-
r"""청산규율_알림.py — 청산 규율 일일 점검 + 카카오톡 알림 (2026-07-30 신설)

[하는 일]
  ① 보유종목의 분산 단계(🟡1~⚫4) 판정
  ② 시장 폭 다이버전스 상태
  ③ 신규 분산일 발생 종목 (대형주 우선)
  → 카카오톡 '나에게 보내기'로 발송 (jq_kakao 모듈 재사용)

[발송 정책 — 알림 피로 방지]
  · 🟡 이상 단계가 하나라도 있으면 **즉시 발송**
  · 전부 🟢 이면 **주 1회(월요일)만** 요약 발송  (--force 로 강제 발송 가능)
  · 같은 내용 연속 발송 방지: 직전 발송 해시와 같으면 생략 (--force 무시)

[시장별 신뢰도 — 검정 실측 (일봉·20일 −20% 급락 배수)]
  KOSPI  ×2.33 (z 15.1)  ← 신호가 강하다. 대형주에서 쓴다.
  KOSDAQ ×1.37 (z 8.9)   ← 유의하나 약하다. 참고로만.
  ※ KOSDAQ은 '10일내 2회+' 반복 신호가 무의미(z 1.1) — 1회 신호만 본다.

사용:  py 청산규율_알림.py              (정책대로)
       py 청산규율_알림.py --force      (무조건 발송)
       py 청산규율_알림.py --dry-run    (발송 없이 메시지만 출력)
자동화: 청산규율_알림.bat 을 작업 스케줄러에 등록 (장 마감 후 16:00 권장)
⚠️ 위험 경보 · 매도 추천 아님 · 투자자문 아님.
"""
import os, sys, json, hashlib, datetime, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 2.0, 0.03, 0.02
PX_FLOOR, AMT_FLOOR, BREADTH_REL = 1000, 10e8, 0.70
STATE = os.path.join(HERE, "_청산규율_발송상태.json")


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


SPLICE_INFO = {"n": 0, "from": None, "to": None}

def build():
    """수정주가 패널 + (최신분) 원주가 패널 이어붙이기.

    증분수집(진우_일봉_증분수집.py)은 종목일봉_30년_*.csv(원주가)만 갱신하고
    _일봉OHLCV_*_adj.csv 는 건드리지 않는다. 그런데 **최근 며칠의 원주가는
    수정주가와 같다** — 그 이후에 CA가 없었으므로 조정계수가 1이기 때문이다.
    따라서 adj 마지막 날짜 이후의 원주가 행만 이어붙이면 신선도가 회복된다.
    (그 며칠 안에 CA가 나면 과거 adj가 낡는다 → 주 1회 collect_adjusted_daily.py 재수집으로 해소)
    """
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["mkt"] = m; fr.append(d)
    if not fr: sys.exit("❌ _일봉OHLCV_*_adj.csv 없음")
    D = pd.concat(fr, ignore_index=True)
    D["code"] = D["code"].str.zfill(6)

    adj_max = D["date"].max()
    add = []
    for m in ("KOSPI", "KOSDAQ"):
        rp = _find(f"종목일봉_30년_{m}.csv")
        if not rp: continue
        try:
            raw = pd.read_csv(rp, dtype={"code": str})
        except Exception:
            continue
        need = {"date", "code", "open", "high", "low", "close", "volume"}
        if not need.issubset(set(raw.columns)): continue
        raw = raw[raw["date"] > adj_max]
        if len(raw):
            raw = raw.copy()
            raw["code"] = raw["code"].astype(str).str.zfill(6); raw["mkt"] = m
            add.append(raw[["code", "date", "open", "high", "low", "close", "volume", "mkt"]])
    if add:
        A = pd.concat(add, ignore_index=True)
        SPLICE_INFO["n"] = len(A); SPLICE_INFO["from"] = A["date"].min(); SPLICE_INFO["to"] = A["date"].max()
        D = pd.concat([D, A], ignore_index=True)

    D = D.drop_duplicates(["code", "date"], keep="last")
    D = D.sort_values(["code", "date"]).reset_index(drop=True)
    g = D.groupby("code")
    D["hi252"] = g["high"].transform(lambda s: s.rolling(252, min_periods=120).max())
    D["volma"] = g["volume"].transform(lambda s: s.rolling(60, min_periods=40).mean())
    D["body"] = D["close"] / D["open"] - 1
    D["wick"] = (D["high"] - D[["open", "close"]].max(axis=1)) / D["high"]
    D["amt"] = D["close"] * D["volume"]
    D["volx"] = D["volume"] / D["volma"]
    D["hi_pct"] = D["close"] / D["hi252"] - 1
    D["nearhi"] = (D["close"] >= D["hi252"] * NEAR_HIGH) & (D["close"] >= PX_FLOOR) & \
                  (D["amt"] >= AMT_FLOOR) & D["hi252"].notna() & D["volma"].notna()
    D["sig"] = D["nearhi"] & (D["volx"] >= VOL_MULT) & (D["wick"] >= WICK_MIN) & (D["body"] <= BODY_SMALL)
    D["sig10"] = D.groupby("code")["sig"].transform(lambda s: s.rolling(10, min_periods=1).sum())
    return D


def smart_out_set():
    out = set()
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"flow_ext_weekly_{m}.csv")
        if not p: continue
        f = pd.read_csv(p, dtype={"code": str})
        f.columns = [c.strip().lstrip("﻿") for c in f.columns]
        s = f[f["date"] == f["date"].max()]
        out |= set(s[(pd.to_numeric(s["foreign_net"], errors="coerce") < 0) &
                     (pd.to_numeric(s["inst_net"], errors="coerce") < 0)]["code"].str.zfill(6))
    return out


def stage_of(sig, sig10, smart, div, mkt):
    # KOSDAQ은 반복신호(sig10)가 무의미(z 1.1) → 3단계 승격에서 제외
    rep = (sig10 >= 2) and (mkt == "KOSPI")
    if rep and div:   return 4, "⚫4", "재량 신규 전면중단 · 비중 1/2 이하"
    if rep:           return 3, "🔴3", "비중 1/2 이하 · 트레일 −15% 강제"
    if sig and smart: return 2, "🟠2", "비중 1/3 축소"
    if sig:           return 1, "🟡1", "신규진입·추가매수 중단"
    return 0, "🟢", ""


def main():
    force = "--force" in sys.argv
    dry = "--dry-run" in sys.argv
    D = build()
    last = D["date"].max()
    smart = smart_out_set()
    names = {}
    p = _find("종목명_맵.csv")
    if p:
        try:
            nm = pd.read_csv(p, dtype=str); names = dict(zip(nm.iloc[:, 0].str.zfill(6), nm.iloc[:, 1]))
        except Exception: pass

    # 시장 폭
    b = D[D["nearhi"]].groupby("date").size().rename("n").reset_index()
    b["ma"] = b["n"].rolling(65, min_periods=40).mean()
    cur = b[b["date"] <= last].tail(1)
    rel = float(cur["ma"].iloc[0]) and float(cur["n"].iloc[0]) / float(cur["ma"].iloc[0]) if len(cur) else np.nan
    nh = int(cur["n"].iloc[0]) if len(cur) else 0
    div = bool(np.isfinite(rel) and rel <= BREADTH_REL)

    # 보유 점검
    lines, worst = [], 0
    hp = _find("my_holdings.csv")
    holds = []
    if hp:
        try:
            r = pd.read_csv(hp, comment="#", dtype=str).dropna(subset=["code"])
            holds = [(str(c).zfill(6), (n or c)) for c, n in zip(r["code"], r.get("name", r["code"]))]
        except Exception: pass
    for c, nm in holds:
        s = D[D["code"] == c].tail(1)
        if not len(s):
            lines.append(f"· {nm}: 데이터없음"); continue
        r = s.iloc[0]
        lv, tag, act = stage_of(bool(r["sig"]), int(r["sig10"]), c in smart, div, r["mkt"])
        worst = max(worst, lv)
        lines.append(f"{tag} {nm} {r['close']:,.0f} (고점比{r['hi_pct']*100:+.0f}%)" + (f" → {act}" if act else ""))

    # 신규 분산일 (당일)
    today_sig = D[(D["date"] == last) & D["sig"]].sort_values("amt", ascending=False)
    ks = today_sig[today_sig["mkt"] == "KOSPI"]

    now = datetime.datetime.now().strftime("%m/%d %H:%M")
    try:
        gap = (datetime.date.today() - datetime.date.fromisoformat(last)).days
    except Exception:
        gap = 0
    msg = [f"🔍 청산규율 {now} (기준 {last})"]
    if SPLICE_INFO["n"]:
        msg.append(f"※원주가 이어붙임 {SPLICE_INFO['from']}~{SPLICE_INFO['to']} ({SPLICE_INFO['n']:,}행)")
    if gap >= 5:
        msg.append(f"⚠️데이터 {gap}일 지연 — 일봉 갱신 필요")
    msg.append(f"시장폭: 고점권 {nh}종목 ({rel:.2f}x) {'🔴다이버전스' if div else '🟢정상'}")
    if lines:
        msg.append("─ 보유 ─"); msg += lines
    if len(ks):
        msg.append(f"─ 신규 분산일(KOSPI {len(ks)}) ─")
        for _, r in ks.head(5).iterrows():
            sm = "🔴수급" if r["code"] in smart else ""
            msg.append(f"· {names.get(r['code'], r['code'])} {r['close']:,.0f} "
                       f"거래량{r['volx']:.1f}x 꼬리{r['wick']*100:.0f}% {sm}")
    if len(today_sig) - len(ks) > 0:
        msg.append(f"(KOSDAQ {len(today_sig)-len(ks)}건 — 신호 약함, 참고)")
    if worst == 0 and not len(ks):
        msg.append("이상 없음. 규칙대로 유지.")
    msg.append("⚠️경보이지 매도추천 아님")
    text = "\n".join(msg)

    print(text)
    h = hashlib.md5(text.split("\n", 1)[1].encode()).hexdigest()[:12]   # 시각 제외 해시
    prev = {}
    if os.path.exists(STATE):
        try: prev = json.load(open(STATE, encoding="utf-8"))
        except Exception: pass

    is_mon = datetime.date.today().weekday() == 0
    should = force or worst >= 1 or len(ks) > 0 or is_mon
    if not should:
        print("\n[발송 생략] 이상 없음 + 월요일 아님"); return 0
    if not force and prev.get("hash") == h:
        print("\n[발송 생략] 직전과 동일 내용"); return 0
    if dry:
        print("\n[dry-run] 발송하지 않음"); return 0

    try:
        import jq_kakao as K
        cfg = K.load_config()
        tok = K.get_access_token(cfg)
        if not tok:
            print("\n❌ 카카오 토큰 없음 — jq_kakao_auth.py 로 최초 발급 필요"); return 2
        ok, res = K.send_text(tok, text, link_url=cfg.get("LINK_URL") or "https://finance.naver.com")
        print(f"\n{'✅ 카톡 발송 완료' if ok else '❌ 발송 실패'}: {res}")
        if ok:
            json.dump({"hash": h, "at": datetime.datetime.now().isoformat(), "worst": worst},
                      open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        print(f"\n❌ 카톡 모듈 오류: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
