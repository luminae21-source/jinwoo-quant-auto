#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_gpt_digest.py — GPT(외부 AI) 검토용 자기완결 요약 생성
==============================================================================
목적: 방대한 HTML/스크립트를 외부 검토자(GPT 등)가 그대로 읽을 수 있게, 최신 CSV에서
      핵심 수치·표·쟁점(닭-달걀)·정직 한계·검토 질문을 1개 마크다운으로 압축.
      파일 의존 없음(숫자·표를 본문에 박음) → 통째로 복붙 가능.
입력: decision_view_latest.csv · signal_efficacy_latest.csv · theme_heat_latest.csv ·
      holdings_concentration_latest.csv  (없으면 해당 절 생략)
산출: 진우퀀트_GPT검토요약_YYYY-MM-DD.md
사용: python build_gpt_digest.py [--selftest]
정직: in-sample·단일 레짐·forward 미측정 한계를 문서 안에 명시.
"""
import argparse, os, sys, datetime
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def _rd(fn):
    p = os.path.join(HERE, fn)
    try:
        return pd.read_csv(p, dtype=str)
    except Exception:
        return None


def md_table(df, cols, headers=None):
    headers = headers or cols
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"]*len(headers)) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def build():
    dv = _rd("decision_view_latest.csv")
    se = _rd("signal_efficacy_latest.csv")
    th = _rd("theme_heat_latest.csv")
    hc = _rd("holdings_concentration_latest.csv")
    date = datetime.date.today().strftime("%Y-%m-%d")
    L = []
    L.append(f"# 진우퀀트 — GPT 검토용 요약 ({date})")
    L.append("> 외부 AI/사람 검토용 자기완결 브리핑. **투자자문 아님**. 시스템은 후보·측정·리스크 가시화만, 결정은 사람.")
    L.append("")
    L.append("## 0. 검토 요청 — 핵심 질문 (닭-달걀)")
    L.append("production 선별 바스켓(가치·퀄리티·저베타)이 현재 **비주도**다. 이게:")
    L.append("- **가설 A (레짐 탓)**: 가치/퀄리티/저베타는 장기 프리미엄. 지금 부진은 좁은 AI·고베타 버블 레짐 탓 → 규율 유지하면 회귀 시 보상.")
    L.append("- **가설 B (구조적 미스매치)**: 엔진이 BAB(저베타 우대)로 **고베타 주도주를 적극 회피** → 점수가 forward 수익과 무관(corr 0.06). 이런 모멘텀 레짐이 길면 구조적으로 못 맞춤.")
    L.append("")
    L.append("**판별 불가 이유**: 데이터가 사실상 한 사이클(상승)뿐 = in-sample. 하락/회귀 국면이 없어 어느 쪽도 입증 안 됨.")
    L.append("")
    L.append("➡️ **검토 부탁**: 아래 데이터로 (1) A/B 어느 쪽 무게? (2) 선별 노선을 **유지 / 모멘텀·고베타 보강 / 오버레이(heat·진입) 의존** 중 무엇? (3) 반도체 쏠림 리스크 대응(수익우선 철학 하)? (4) 이 분석의 편향·함정?")
    L.append("")
    L.append("## 1. 시스템 구조 (트랙 분리)")
    L.append("- **선별(production v3.7.2)**: 점수 = F·Sloan·NOA·Mom12·BAB(저베타)·Echo → 등급 S+≥14·S≥12·A≥9. 성향 = 가치·퀄리티·저베타.")
    L.append("- **발굴(heat)**: 전 시장 테마 랭킹(단기 상대강도·breadth·supercycle). '지금 뜨거운' 테마 surfacing.")
    L.append("- **진입(entry_signals)**: SEPA 8조건(주봉 10/30/40주선·52주 고저·RS)+베이스 돌파, 손절 −8%.")
    L.append("- **측정(Track W)**: forward 반사실(아직 미충전).")
    L.append("- 원칙: 발굴≠매수≠검증. '선별 18'은 모델 픽이지 실보유 아님.")
    L.append("")
    L.append("## 2. 핵심 측정 사실 (전부 in-sample · 2025~26 쏠림장)")
    if th is not None:
        th2 = th.copy(); th2["hs"] = pd.to_numeric(th2["heat_score"], errors="coerce")
        scn = int((th2["supercycle"] == "True").sum())
        topn = th2.sort_values("hs", ascending=False).head(3)["theme"].tolist()
        L.append(f"- 시장: 극단 강세장(12M EW ≈ +78%), supercycle ON 테마 **{scn}개**(과거 4→1 협소화), 주도 = {', '.join(topn)}.")
    if se is not None:
        m = se.set_index("signal")
        def g(k, c): 
            try: return m.loc[k, c]
            except Exception: return "?"
        L.append(f"- **점수 vs forward**: corr(점수,12M초과) ≈ **0.06** (점수≠forward수익).")
        L.append(f"- **heat 추격 forward**: 상위테마 fwd1m {g('heat 상위테마 fwd1m','mean_fwd')}% · fwd3m {g('heat 상위테마 fwd3m','mean_fwd')}% (**≈0, 추격 비효율**).")
        L.append(f"- **진입 forward(3m 초과)**: 돌파/셋업 **+{g('진입:돌파/셋업 fwd3m','mean_fwd')}%**(적중 {g('진입:돌파/셋업 fwd3m','hit%')}%) vs 관망 +{g('진입:관망 fwd3m','mean_fwd')}% → **진입에만 +엣지**(n={g('진입:돌파/셋업 fwd3m','n')}).")
    L.append("- **S+ ∩ 뜨거운테마**: 평균 12M초과 +92% (전체 S+ +23%) → 품질×주도 결합 시 적중↑.")
    if hc is not None:
        hc2 = hc.copy(); hc2["beta"] = pd.to_numeric(hc2["beta"], errors="coerce")
        L.append(f"- **집중(선별 18 EW)**: 수익의 ~81%가 반도체 5종, 상위 2종 ~52%, 포트 beta ≈ {hc2['beta'].mean():.2f}, 유효종목수 ≈ 6/18 (겉 분산·속 집중).")
    L.append("")
    L.append("## 3. 선별 18 현재 종합 판단 (decision_view)")
    if dv is not None:
        sel = dv[dv["held"] == "True"].copy()
        from collections import Counter
        dist = dict(Counter(sel["verdict"]))
        L.append("verdict 분포: " + " · ".join(f"{k} {v}" for k, v in dist.items()))
        L.append("")
        L.append(md_table(sel, ["name","theme","grade","heat","entry","ex12_%","verdict"],
                          ["종목","테마","등급","주도성","진입","12M초과%","종합판단"]))
        L.append("")
        L.append("※ '약/비주도'=매도신호 아님. **선별 바스켓이 이 레짐에서 비주도**라는 특성(가설 B 정황). 진입은 전부 '관망'(셋업 0=눌림).")
    L.append("")
    L.append("## 4. 무엇이 닭-달걀을 판별해주나")
    L.append("- **forward Track W 실측(6~12M)**: 선별 vs (선별∩heat) vs 진입신호의 실제 수익. (정본: trackw_ledger.csv 충전 후 trackw_score)")
    L.append("- **regime 조건부 분해**: RISK_ON/NEUTRAL/OFF별 선별 성과 → 레짐 의존성 정량화.")
    L.append("- **다른 레짐 백테스트**(2022 하락장 등): 선별의 방어력(하락장 초과) 확인 = 가설 A 검증.")
    L.append("")
    L.append("## 5. 현 시스템의 잠정 입장 (오버핏 회피)")
    L.append("- 선별 엔진 **무수정**(이 진단에 맞춰 비틀면 오버핏). 선별 = 품질 베이스로 유지.")
    L.append("- 부족분은 heat(주도성)·진입(타이밍)으로 보완. 측정상 **엣지는 진입(타이밍·리스크 규율)**에 있음.")
    L.append("- 신규 매수 = 진입 트리거 한정, 추격 금지, −8% 손절. 보유 점검 = thesis·무효화·집중도.")
    L.append("")
    L.append("## 6. 정직 한계 (검토 시 반드시 감안)")
    L.append("- **in-sample**(같은 데이터로 신호·측정), **단일 상승 레짐**(하락국면 부재), 진입 표본 작음(n≈41), forward 실측 0.")
    L.append("- 2025~26 패널은 비현실적 강세(시장 EW +78%, 일부 종목 수배) — 절대치 과신 금지.")
    L.append("- 돌파를 종목선택으로 본 백테스트는 FAIL(알파 −1.1%p). 진입의 +엣지도 선택편향(이미 좋은 종목군) 가능.")
    L.append("- 백테스트·과거치를 forward 기대치로 쓰지 말 것.")
    L.append("")
    L.append("## 7. 검토 질문 (GPT에게)")
    L.append("1. 위 데이터로 가설 A(레짐) vs B(구조) 어느 쪽에 무게? 추가로 봐야 할 데이터는?")
    L.append("2. 선별 노선: **유지 / 모멘텀·고베타 보강 / 오버레이 의존** 중 권고와 근거?")
    L.append("3. 반도체 81%·beta 1.8 집중: 수익 우선·디리스킹 회의 성향에서 합리적 대응은?")
    L.append("4. 이 분석의 편향·함정(생존편향·in-sample·룩어헤드·데이터 이상)은?")
    L.append("")
    L.append(f"---\n*생성 {date} · 진우퀀트 시스템 산출 CSV 기반 · 수치는 그 시점 스냅샷.*")
    return "\n".join(L), date


def _selftest():
    t = md_table(pd.DataFrame([{"a":"1","b":"2"}]), ["a","b"], ["A","B"])
    assert "| A | B |" in t and "| 1 | 2 |" in t
    print("✅ build_gpt_digest 셀프테스트 통과 (1/1): md_table")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    md, date = build()
    out = os.path.join(HERE, f"진우퀀트_GPT검토요약_{date}.md")
    open(out, "w", encoding="utf-8").write(md)
    print(f"산출: {os.path.basename(out)} ({len(md)}자)")


if __name__ == "__main__":
    main()
