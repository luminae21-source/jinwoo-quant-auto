# -*- coding: utf-8 -*-
r"""신규종목_감지.py — 신규 상장·유니버스 신규 편입 감지 및 관찰 대기 관리 (2026-07-28 신설)

[해결하는 문제] "새로 상장한 회사인데 내가 모르고 지나간다."
  → 매월 패널을 훑어 **신규 등장 코드를 전부 잡아내고** 나이(상장 경과월)와 데이터 성숙도를 추적한다.
     모르고 지나가는 일이 없어지되, **아는 것과 사는 것은 분리한다.**

[왜 바로 사지 않는가 — 실측 근거 (검정_신규상장_효과, 2002-2015)]
  상장 경과월별 기성종목(60M+) 대비 연 초과수익:
      0~6개월   −13.19%p (HAC t −2.74)      ← 갓 상장이 가장 나쁘다
      6~12개월  −14.61%p (t −3.32)
      12~24개월  −8.51%p (t −3.33)
      24~36개월  −5.04%p (t −1.97)
      36~60개월  −0.54%p (t −0.30)          ← 여기서 소멸
  **단조 수렴.** 신규 상장은 첫 1년 연 13~15%p 열위이고, 불리함은 약 36개월에 사라진다.
  게다가 0~6개월 소멸 54건 중 **90.7%가 부실(폭락·동결)** 이었다.
  → **모르고 지나간 것은 손해가 아니라 이득이었다.** 규칙은 '추격'이 아니라 '관찰 대기'다.

[규칙 — QUARANTINE_M = 36]
  · 신규 코드는 등장 즉시 관찰 리스트에 올린다 (인지)
  · 상장 경과 36개월 미만이면 **본체·위성 편입 금지** (매매)
  · 36개월 도달 + 팩터 데이터 성숙 → 정상 유니버스로 자동 승격
  · 예외 없음. "이번 건 다르다"는 위 표가 이미 반박했다.

사용:  py 신규종목_감지.py                (최근 12개월 신규분 리포트)
       py 신규종목_감지.py --since 2026-01  (기간 지정)
       py 신규종목_감지.py --all           (관찰 대기 중인 전체 명단)
출력:  신규종목_관찰리스트.csv · 신규종목_리포트.md
⚠️ 정보·관리 도구. 매수 추천 아님. 투자자문 아님.
"""
import os, sys, argparse, datetime
import pandas as pd
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

QUARANTINE_M = 36        # 관찰 대기 개월 — 실측 근거(위 표)
VOL_NEED     = 12        # 변동성 계산 최소 개월
DIV_NEED     = 36        # 배당지속성 계산 최소 개월


def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def mi(ym):
    return int(ym[:4]) * 12 + int(ym[5:7])


def load_panel():
    fr = []
    for mkt in ("KOSPI", "KOSDAQ"):
        p = _find(f"_월봉종가캐시_{mkt}.csv")
        if not p:
            continue
        d = pd.read_csv(p, dtype={"code": str}, usecols=["code", "ym", "close"])
        d["code"] = d["code"].str.zfill(6)
        d["mkt"] = mkt
        fr.append(d)
    if not fr:
        sys.exit("❌ _월봉종가캐시_KOSPI/KOSDAQ.csv 를 못 찾음 — 진우퀀트 루트에서 실행할 것")
    return pd.concat(fr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="이 달 이후 신규분만 (기본: 최근 12개월)")
    ap.add_argument("--all", action="store_true", help="관찰 대기 중(경과<36M) 전체 명단")
    a = ap.parse_args()

    px = load_panel()
    panel_end = px["ym"].max()
    ALLC = set(px["code"].unique())
    end_mi = mi(panel_end)
    since = a.since or f"{(end_mi - 12)//12:04d}-{((end_mi - 12) % 12) or 12:02d}"

    # 종목 유형 판별 (2026-07-28 추가 — 실측: 우선주는 배당수익률 2.09배, 고배당 상위20%에 2배 과대표집)
    def kind(c):
        if not c.isdigit():
            return "신형우선주"          # 예 00088K (한화3우B류) — 재무데이터는 보유
        if (not c.endswith("0")) and (c[:5] + "0") in ALLC:
            return "우선주"              # 예 005935 (보통주 005930 존재)
        return "보통주"

    # 코드별 최초·최종 등장
    g = px.groupby("code").agg(first_ym=("ym", "min"), last_ym=("ym", "max"),
                               mkt=("mkt", "last"), n_obs=("ym", "count")).reset_index()
    g["kind"] = g["code"].map(kind)
    g["age_m"] = end_mi - g["first_ym"].map(mi)
    g["alive"] = g["last_ym"] >= panel_end

    # 최근가
    last_px = px.sort_values("ym").groupby("code").tail(1).set_index("code")["close"]
    g["last_close"] = g["code"].map(last_px)

    # 시총(있으면)
    mcp = _find("종목시총_30년.csv")
    if mcp:
        mc = pd.read_csv(mcp, dtype={"code": str})
        mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
        mc["code"] = mc["code"].str.zfill(6)
        mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
        mcl = mc.sort_values("ym").groupby("code").tail(1).set_index("code")["mcap"]
        g["mcap"] = pd.to_numeric(g["code"].map(mcl), errors="coerce")
    else:
        g["mcap"] = np.nan

    # 상태 판정
    def status(r):
        if not r["alive"]:
            return "소멸/정지"
        if r["kind"] != "보통주":
            return f"⚪ {r['kind']} (계열 1종 룰 적용)"
        if r["age_m"] < QUARANTINE_M:
            return f"🟡 관찰대기 (D-{QUARANTINE_M - int(r['age_m'])}개월)"
        return "✅ 편입가능"
    g["status"] = g.apply(status, axis=1)
    g["vol_ready"] = np.where(g["n_obs"] >= VOL_NEED, "O", "X")
    g["div_ready"] = np.where(g["n_obs"] >= DIV_NEED, "O", "X")

    if a.all:
        sel = g[(g["age_m"] < QUARANTINE_M) & g["alive"]].copy()
        title = f"관찰 대기 전체 명단 (상장 경과 < {QUARANTINE_M}개월)"
    else:
        sel = g[(g["first_ym"] >= since) & g["alive"]].copy()
        title = f"{since} 이후 신규 등장 종목"
    sel = sel.sort_values(["first_ym", "mcap"], ascending=[False, False])

    # ── 출력
    print("=" * 92)
    print(f" 신규종목 감지 — {title}   (패널 기준월 {panel_end})")
    print("=" * 92)
    print(f"  규칙: 신규 상장은 **{QUARANTINE_M}개월 관찰 대기** 후 편입 (실측: 첫 1년 −13~15%p 열위)")
    nk = g[g["alive"]]["kind"].value_counts().to_dict()
    print(f"  전체 코드 {len(g):,} · 생존 {int(g['alive'].sum()):,} "
          f"(보통주 {nk.get('보통주',0):,} · 우선주 {nk.get('우선주',0):,} · 신형우선주 {nk.get('신형우선주',0):,}) · "
          f"관찰대기 {int(((g['age_m'] < QUARANTINE_M) & g['alive'] & (g['kind']=='보통주')).sum()):,}")
    if not len(sel):
        print("\n  (해당 없음)")
    else:
        print(f"\n  {'코드':<8}{'시장':<8}{'유형':<10}{'최초등장':<10}{'경과':>5}{'최근가':>11}{'시총(억)':>11}  상태")
        for _, r in sel.head(60).iterrows():
            mcap_s = f"{r['mcap']/1e8:,.0f}" if pd.notna(r["mcap"]) else "-"
            print(f"  {r['code']:<8}{r['mkt']:<8}{r['kind']:<10}{r['first_ym']:<10}{int(r['age_m']):>4}M"
                  f"{r['last_close']:>11,.0f}{mcap_s:>11}  {r['status']}")
        if len(sel) > 60:
            print(f"  … 외 {len(sel)-60}건 (CSV 참조)")

    cols = ["code", "mkt", "kind", "first_ym", "age_m", "last_close", "mcap",
            "vol_ready", "div_ready", "status", "n_obs"]
    sel[cols].to_csv(os.path.join(BASE, "신규종목_관찰리스트.csv"),
                     index=False, encoding="utf-8-sig")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = [f"# 신규종목 감지 리포트 — {now}", "",
          f"- 패널 기준월: **{panel_end}** · 범위: {title}",
          f"- 규칙: 신규 상장 **{QUARANTINE_M}개월 관찰 대기** (편입 금지, 관찰은 함)",
          f"- 근거: 상장 0~6M −13.19%p · 6~12M −14.61%p · 12~24M −8.51%p · 24~36M −5.04%p · "
          f"36~60M −0.54%p (기성 대비 연 초과, HAC t −2.7~−3.3)", "",
          f"| 코드 | 시장 | 유형 | 최초등장 | 경과 | 최근가 | 시총(억) | 상태 |",
          "|---|---|---|---|---:|---:|---:|---|"]
    for _, r in sel.head(80).iterrows():
        mcap_s = f"{r['mcap']/1e8:,.0f}" if pd.notna(r["mcap"]) else "-"
        md.append(f"| {r['code']} | {r['mkt']} | {r['kind']} | {r['first_ym']} | {int(r['age_m'])}M | "
                  f"{r['last_close']:,.0f} | {mcap_s} | {r['status']} |")
    md += ["", "## 운영 규칙",
           "1. 이 리포트는 **인지용**이다 — 여기 실렸다고 사는 것이 아니다.",
           f"2. 경과 {QUARANTINE_M}개월 도달 + 팩터 데이터 성숙(변동성 12M·배당 36M) → 정상 유니버스 자동 편입.",
           "3. 예외 요청('이번 건은 다르다')은 기록만 하고 규칙은 바꾸지 않는다.",
           "4. 매월 본체 사이클 직후 1회 실행 권장.",
           "5. **우선주/신형우선주**는 나이와 무관하게 계열 1종 룰로 처리 — 실측상 배당수익률이 보통주의 "
           "**2.09배**(1.09% vs 2.27%)여서 고배당 상위20%에 2배 과대표집된다(11.5% vs 5.7%). "
           "배당 팩터 자체는 우선주를 빼도 유효(IC t 5.89→5.75)하나, 같은 기업 중복 노출은 막는다.", "",
           "⚠️ 정보·관리 도구 · 매수 추천 아님 · 투자자문 아님 · 결정과 책임은 본인."]
    open(os.path.join(BASE, "신규종목_리포트.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n  저장: 신규종목_관찰리스트.csv · 신규종목_리포트.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
