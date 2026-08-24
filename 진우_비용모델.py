#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_비용모델.py — 거래비용 모델 (세금·수수료) · 로드맵 §3-3 비용검증의 단일 진실원천

"제안이 슬리피지·세금·수수료를 다 물고도 이기는가"를 판정하기 위한 비용 계층.
순수함수 + self-test. 진우_전진기록.py(성과 정산)와 향후 진우_모의매매.py가 이 모듈 하나만 import한다.

세율(2026년 기준, 웹 확인):
  · 증권거래세(농특세 포함) = 매도 시에만, **코스피·코스닥 모두 0.20%**.
    - 코스피: 거래세 0.05% + 농특세 0.15% = 0.20%
    - 코스닥: 거래세 0.20%(농특세 없음)   = 0.20%
    - 2025년 0.15% → 2026년 0.20%로 환원(금투세 폐지에 따른 과세형평). 매수엔 거래세 없음.
  · 위탁수수료 = 매수·매도 각각. 증권사·이벤트별 편차 큼(무료~0.015%). 기본 0.015%로 보수적 가정(편집 가능).
  ⚠️ 세율·수수료는 바뀐다. 값은 전부 인자/설정으로 외부화 — 바뀌면 여기 기본값이나 진우_비용설정.json만 고친다.

⚠️ 검증용 비용 추정치다. 실제 원천징수·유관기관 제비용은 증권사 확인. 투자자문 아님·책임 본인.
"""
import os, sys, json, argparse
from dataclasses import dataclass, asdict

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "진우_비용설정.json")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

@dataclass
class CostModel:
    tax_kospi: float = 0.0020      # 매도 세금(농특세 포함), 코스피
    tax_kosdaq: float = 0.0020     # 매도 세금, 코스닥
    commission: float = 0.00015    # 위탁수수료(매수·매도 각 편도), 기본 0.015%

    @staticmethod
    def load(path=CFG_PATH):
        base = CostModel()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                for k, v in d.items():
                    if hasattr(base, k): setattr(base, k, float(v))
            except Exception:
                pass
        return base

    def save(self, path=CFG_PATH):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    def sell_tax_rate(self, market="kosdaq"):
        return self.tax_kospi if str(market).lower() in ("kospi", "코스피") else self.tax_kosdaq

# ────────────────────────── 순수 비용 함수(self-test 대상) ──────────────────────────
def buy_cost(price, qty, commission):
    """매수 비용 = 수수료만(매수엔 거래세 없음). 반환 원(정수 내림 아님, 실수)."""
    return max(price, 0) * max(qty, 0) * max(commission, 0)

def sell_cost(price, qty, tax_rate, commission):
    """매도 비용 = 거래세(농특세 포함) + 수수료."""
    gross = max(price, 0) * max(qty, 0)
    return gross * (max(tax_rate, 0) + max(commission, 0))

def roundtrip_cost(buy_price, sell_price, qty, tax_rate, commission):
    """한 종목 왕복(매수→매도) 총비용(원)."""
    return buy_cost(buy_price, qty, commission) + sell_cost(sell_price, qty, tax_rate, commission)

def breakeven_move(tax_rate, commission):
    """왕복 비용을 상쇄하려면 최소 몇 % 올라야 하나(근사, 동일가 가정).
    ≈ 매수수수료 + 매도수수료 + 매도세금. 예: 0.015+0.015+0.20 = 0.23%."""
    return commission * 2 + tax_rate

def net_realized(buy_price, sell_price, qty, tax_rate, commission):
    """비용 반영 실현손익 = (매도−매수)*수량 − 왕복비용."""
    gross = (sell_price - buy_price) * qty
    return gross - roundtrip_cost(buy_price, sell_price, qty, tax_rate, commission)

# ────────────────────────── 장부 전체 비용 집계 ──────────────────────────
def ledger_costs(trades, model: CostModel, market_of=None):
    """체결 장부의 실제 발생 비용 합.
    trades: [{code,side('매수'/'매도'),price,qty,...}]. market_of(code)->'kospi'/'kosdaq'(없으면 kosdaq 가정, 2026엔 세율 동일).
    반환 dict(buy_fee, sell_tax, sell_fee, total, n_buy, n_sell)."""
    buy_fee = sell_tax = sell_fee = 0.0
    n_buy = n_sell = 0
    for t in trades:
        gross = t["price"] * t["qty"]
        if t["side"] == "매수":
            buy_fee += gross * model.commission; n_buy += 1
        elif t["side"] == "매도":
            mk = market_of(t["code"]) if market_of else "kosdaq"
            sell_tax += gross * model.sell_tax_rate(mk)
            sell_fee += gross * model.commission; n_sell += 1
    total = buy_fee + sell_tax + sell_fee
    return dict(buy_fee=buy_fee, sell_tax=sell_tax, sell_fee=sell_fee, total=total,
                n_buy=n_buy, n_sell=n_sell)

# ────────────────────────── self-test ──────────────────────────
def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    m = CostModel()  # 세금 0.20%, 수수료 0.015%
    # 매수: 100만원어치 → 수수료 150원
    chk("매수비용=수수료만(거래세 없음)", abs(buy_cost(50000, 20, 0.00015) - 150.0) < 1e-6)
    # 매도: 100만원어치 → 세금 2000 + 수수료 150 = 2150
    chk("매도비용=세금+수수료", abs(sell_cost(50000, 20, 0.0020, 0.00015) - 2150.0) < 1e-6)
    # 왕복: 매수100만(수수료150) + 매도100만(2150) = 2300
    chk("왕복비용 = 매수수수료+매도(세금+수수료)", abs(roundtrip_cost(50000, 50000, 20, 0.0020, 0.00015) - 2300.0) < 1e-6)
    # 손익분기 이동: 0.00015*2 + 0.0020 = 0.0023 = 0.23%
    chk("손익분기 이동 0.23%", abs(breakeven_move(0.0020, 0.00015) - 0.0023) < 1e-12)
    # 순실현손익: 5만→5만(변동0) 20주 → gross0 − 왕복2300 = −2300
    chk("변동0이면 순손익=−왕복비용", abs(net_realized(50000, 50000, 20, 0.0020, 0.00015) + 2300.0) < 1e-6)
    # 순실현손익: 5만→5.5만 20주 → gross 10만 − 비용(매수150+매도세금2200+수수료165=2515) = 97485
    #   매도gross=110만 → 세금2200 + 수수료165. 매수gross=100만→수수료150. 왕복=2515.
    chk("순실현손익 = 총손익 − 왕복비용", abs(net_realized(50000, 55000, 20, 0.0020, 0.00015) - (100000 - 2515.0)) < 1e-6)

    # 시장별 세율(2026엔 동일하지만 필드 분리 유지)
    chk("코스피 세율 0.20%", abs(m.sell_tax_rate("kospi") - 0.0020) < 1e-12)
    chk("코스닥 세율 0.20%", abs(m.sell_tax_rate("kosdaq") - 0.0020) < 1e-12)
    chk("한글 시장명도 인식", abs(m.sell_tax_rate("코스피") - 0.0020) < 1e-12)

    # 장부 집계
    trades = [dict(code="000001", side="매수", price=50000, qty=20),   # 매수 100만 → 수수료150
              dict(code="000001", side="매도", price=55000, qty=20)]   # 매도 110만 → 세금2200+수수료165
    c = ledger_costs(trades, m)
    chk("장부: 매수수수료 150", abs(c["buy_fee"] - 150.0) < 1e-6)
    chk("장부: 매도세금 2200", abs(c["sell_tax"] - 2200.0) < 1e-6)
    chk("장부: 매도수수료 165", abs(c["sell_fee"] - 165.0) < 1e-6)
    chk("장부: 총비용 2515", abs(c["total"] - 2515.0) < 1e-6)
    chk("장부: 매수1·매도1 카운트", c["n_buy"] == 1 and c["n_sell"] == 1)

    # 설정 저장/로드
    tmp = os.path.join(BASE, "_cost_test.json")
    try:
        CostModel(commission=0.0, tax_kosdaq=0.0015).save(tmp)
        L = CostModel.load(tmp)
        chk("설정: 저장→로드 왕복", L.commission == 0.0 and L.tax_kosdaq == 0.0015)
    finally:
        if os.path.exists(tmp): os.remove(tmp)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot

def main():
    ap = argparse.ArgumentParser(description="진우 거래비용 모델(§3-3)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--save-config", action="store_true", help="기본 비용을 진우_비용설정.json에 저장")
    ap.add_argument("--show", action="store_true", help="현재 비용 가정·손익분기 출력")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    m = CostModel.load()
    if a.save_config:
        m.save(); print("저장: 진우_비용설정.json")
    if a.show or not a.save_config:
        be = breakeven_move(m.tax_kosdaq, m.commission)
        print("\n[진우 비용 모델 · 2026 기준]")
        print(f"  매도 거래세: 코스피 {m.tax_kospi*100:.2f}% · 코스닥 {m.tax_kosdaq*100:.2f}% (농특세 포함, 매도만)")
        print(f"  위탁수수료: 편도 {m.commission*100:.3f}% (매수·매도 각각)")
        print(f"  → 손익분기: 한 종목이 왕복 비용을 넘으려면 최소 +{be*100:.2f}% 상승 필요")
        print("  ※ 값은 진우_비용설정.json으로 편집 가능. 실제 제비용은 증권사 확인.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
