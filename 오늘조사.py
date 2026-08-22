# -*- coding: utf-8 -*-
r"""오늘조사.py — '오늘 볼 만한 종목'을 별도 원장(조사)에 담고 추적 (2026-08-01)

[왜] 휩쏘 탐지(2일째 정석 자리)는 탐색기가 자동으로 원장에 등록한다.
     그 외에 형이 '오늘 이건 관찰할 가치가 있다' 판단한 종목은 — 휩쏘 원장과 섞지 않고
     **조사 원장**에 따로 담아 같은 방식으로 전진 추적한다. (다른 검색 방식은 형이 채워 넣을 자리)

[관계]  이 도구는 휩쏘_관찰.py 의 엔진을 그대로 쓰되 **원장만 '조사'로 분리**한다.
        휩쏘 원장 : 휩쏘_관찰.csv   (탐색기 자동)
        조사 원장 : 조사_관찰.csv   (이 도구 · 수동)

[사용]
  py 오늘조사.py --codes 005930,000660,대덕전자     # 오늘 종가로 조사 원장에 등록 + 추적
  py 오늘조사.py --codes 005930 --date 20260730     # 특정일 종가로 등록
  py 오늘조사.py                                    # 조사 원장 전진 추적만 (대시보드 갱신)
  py 오늘조사.py --list 조사대상.txt                 # 파일에서 한 줄씩 읽어 등록
                                                    # (한 줄에 코드 또는 종목명)
[손절/목표]  기본 −8% / +15% (일반 눌림 관찰용). 필요하면 --stop, --target 로 조절.
⚠️ 관찰·기록용. 매매 추천 아님.
"""
import os, sys, argparse, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = "조사"


def _engine():
    p = os.path.join(HERE, "휩쏘_관찰.py")
    if not os.path.exists(p):
        sys.exit("휩쏘_관찰.py 가 같은 폴더에 있어야 한다(엔진 공유).")
    spec = importlib.util.spec_from_file_location("gwanchal", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=None, help="코드 또는 종목명 (쉼표)")
    ap.add_argument("--list", default=None, help="종목 목록 파일 (한 줄에 코드/종목명)")
    ap.add_argument("--date", default=None, help="출발일 YYYYMMDD (기본 최신 영업일)")
    ap.add_argument("--stop", type=float, default=8.0, help="손절 %% (기본 8)")
    ap.add_argument("--target", type=float, default=15.0, help="목표 %% (기본 15)")
    ap.add_argument("--days", type=int, default=40, help="만료 거래일")
    ap.add_argument("--noopen", action="store_true")
    a = ap.parse_args()
    g = _engine()

    toks = []
    if a.codes: toks += [x for x in a.codes.split(",") if x.strip()]
    if a.list and os.path.exists(a.list):
        with open(a.list, encoding="utf-8") as f:
            toks += [ln.split("#")[0].strip() for ln in f if ln.split("#")[0].strip()]
    if toks:
        g.add_manual(toks, a.date, LEDGER, stop_pct=a.stop, target_pct=a.target)
    g.track(a.days, a.noopen, LEDGER)


if __name__ == "__main__":
    main()
