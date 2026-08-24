#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""jq_broker_kis.py — 한국투자증권 KIS Developers REST 어댑터 (Broker 구현체)

계약: jq_broker_base.Broker. 기본 모의투자(paper=True). 실계좌는 allow_real=True 명시 필요(구조적 안전핀).
키: 진우_KIS키.json {appkey, appsecret, account, account_prod} 또는 환경변수(KIS_APPKEY/KIS_APPSECRET/KIS_ACCOUNT).
    account = 계좌번호 앞 8자리, account_prod = 뒤 2자리(보통 "01").

⚠️ 실API 호출은 진우 PC 전용(클라우드 불가) · 자동체결 아님(승인 통과분만 send) · 투자자문 아님·책임 본인.

엔드포인트/tr_id — KIS Developers 포털 확인(2026-07). 포털 개정 시 아래 상수만 고치면 됨.
사용(단독 점검): py jq_broker_kis.py --self-test        # 네트워크 없이 요청조립 검증
              py jq_broker_kis.py --price 005930      # 모의 현재가 조회(키 필요)
"""
import os, sys, json, argparse

BASE = os.path.dirname(os.path.abspath(__file__))
KEYFILE = os.path.join(BASE, "진우_KIS키.json")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ────────── KIS 상수(포털 2026-07) ── 개정 시 여기만 수정 ──────────
DOMAIN = {
    "prod": "https://openapi.koreainvestment.com:9443",     # 실전
    "paper": "https://openapivts.koreainvestment.com:29443",  # 모의투자
}
PATH = {
    "token": "/oauth2/tokenP",
    "hashkey": "/uapi/hashkey",
    "order": "/uapi/domestic-stock/v1/trading/order-cash",
    "price": "/uapi/domestic-stock/v1/quotations/inquire-price",
    "balance": "/uapi/domestic-stock/v1/trading/inquire-balance",
    "psbl": "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
}
# tr_id: (실전, 모의)
TRID = {
    "buy":     ("TTTC0802U", "VTTC0802U"),
    "sell":    ("TTTC0801U", "VTTC0801U"),
    "price":   ("FHKST01010100", "FHKST01010100"),
    "balance": ("TTTC8434R", "VTTC8434R"),
    "psbl":    ("TTTC8908R", "VTTC8908R"),
}
ORD_DVSN = {"limit": "00", "market": "01"}   # 00=지정가, 01=시장가


class KISBroker:
    """KIS Developers REST 어댑터. jq_broker_base.Broker 계약 준수."""
    name = "KIS"

    def __init__(self, paper=True, allow_real=False, keyfile=KEYFILE, keys=None):
        self.paper = paper
        # ★ 안전핀: 실계좌는 allow_real=True를 명시적으로 줘야만 가능
        if not paper and not allow_real:
            raise RuntimeError("실계좌(paper=False)는 allow_real=True를 명시해야 합니다. 기본은 모의투자.")
        self.env = "paper" if paper else "prod"
        self.base = DOMAIN[self.env]
        self._token = None
        self._keys = keys or self._load_keys(keyfile)

    # ── 키 로드(로컬 파일 또는 환경변수) ──
    @staticmethod
    def _load_keys(keyfile):
        if os.path.exists(keyfile):
            with open(keyfile, encoding="utf-8") as f:
                k = json.load(f)
        else:
            k = {}
        k.setdefault("appkey", os.environ.get("KIS_APPKEY", ""))
        k.setdefault("appsecret", os.environ.get("KIS_APPSECRET", ""))
        k.setdefault("account", os.environ.get("KIS_ACCOUNT", ""))
        k.setdefault("account_prod", os.environ.get("KIS_ACCOUNT_PROD", "01"))
        return k

    def _trid(self, kind):
        return TRID[kind][0 if self.env == "prod" else 1]

    # ── 순수 조립부(네트워크 없음 · self-test 대상) ──
    def _order_body(self, o):
        """OrderReq → order-cash 요청 바디(dict)."""
        return {
            "CANO": self._keys["account"],
            "ACNT_PRDT_CD": self._keys["account_prod"],
            "PDNO": o.code,
            "ORD_DVSN": ORD_DVSN[o.ordtype],
            "ORD_QTY": str(int(o.qty)),
            "ORD_UNPR": "0" if o.ordtype == "market" else str(int(o.price)),
        }

    def _order_headers(self, side, hashval):
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._token}",
            "appkey": self._keys["appkey"],
            "appsecret": self._keys["appsecret"],
            "tr_id": self._trid(side),      # side=buy/sell → 실전/모의 자동
            "custtype": "P",
            "hashkey": hashval,
        }

    # ── 네트워크부(requests 지연 임포트 · PC 전용) ──
    def _http(self):
        import requests
        return requests

    def auth(self):
        r = self._http()
        res = r.post(self.base + PATH["token"],
                     json={"grant_type": "client_credentials",
                           "appkey": self._keys["appkey"],
                           "appsecret": self._keys["appsecret"]},
                     timeout=10)
        res.raise_for_status()
        self._token = res.json()["access_token"]
        return self._token

    def _hashkey(self, body):
        r = self._http()
        res = r.post(self.base + PATH["hashkey"], json=body,
                     headers={"content-type": "application/json; charset=utf-8",
                              "appkey": self._keys["appkey"],
                              "appsecret": self._keys["appsecret"]},
                     timeout=10)
        res.raise_for_status()
        return res.json()["HASH"]

    def price(self, code):
        if not self._token: self.auth()
        r = self._http()
        res = r.get(self.base + PATH["price"],
                    headers={"authorization": f"Bearer {self._token}",
                             "appkey": self._keys["appkey"],
                             "appsecret": self._keys["appsecret"],
                             "tr_id": self._trid("price")},
                    params={"FID_COND_MRKT_DIV_CODE": "J",
                            "FID_INPUT_ISCD": str(code).zfill(6)},
                    timeout=10)
        res.raise_for_status()
        return int(res.json()["output"]["stck_prpr"])

    def cash(self):
        """예수금(주문가능현금 근사). inquire-balance output2의 예수금총금액."""
        if not self._token: self.auth()
        r = self._http()
        res = r.get(self.base + PATH["balance"],
                    headers={"authorization": f"Bearer {self._token}",
                             "appkey": self._keys["appkey"],
                             "appsecret": self._keys["appsecret"],
                             "tr_id": self._trid("balance")},
                    params={"CANO": self._keys["account"], "ACNT_PRDT_CD": self._keys["account_prod"],
                            "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
                            "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                            "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""},
                    timeout=10)
        res.raise_for_status()
        out2 = res.json().get("output2", [])
        return int(float(out2[0]["dnca_tot_amt"])) if out2 else 0

    def positions(self):
        if not self._token: self.auth()
        r = self._http()
        res = r.get(self.base + PATH["balance"],
                    headers={"authorization": f"Bearer {self._token}",
                             "appkey": self._keys["appkey"],
                             "appsecret": self._keys["appsecret"],
                             "tr_id": self._trid("balance")},
                    params={"CANO": self._keys["account"], "ACNT_PRDT_CD": self._keys["account_prod"],
                            "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
                            "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                            "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""},
                    timeout=10)
        res.raise_for_status()
        pos = {}
        for row in res.json().get("output1", []):
            q = int(float(row.get("hldg_qty", 0) or 0))
            if q > 0:
                pos[str(row["pdno"]).zfill(6)] = dict(qty=q, avg=float(row.get("pchs_avg_pric", 0) or 0))
        return pos

    def send(self, o):
        """★ 승인 통과분만 호출. order-cash 전송."""
        from jq_broker_base import OrderAck
        if not self._token: self.auth()
        body = self._order_body(o)
        hashval = self._hashkey(body)
        r = self._http()
        res = r.post(self.base + PATH["order"], data=json.dumps(body),
                     headers=self._order_headers(o.side, hashval), timeout=10)
        res.raise_for_status()
        j = res.json()
        ok = str(j.get("rt_cd")) == "0"
        odno = (j.get("output") or {}).get("ODNO", "")
        return OrderAck(ok=ok, order_no=odno, msg=j.get("msg1", ""), raw=j)

    def status(self, order_no):
        from jq_broker_base import OrderAck
        return OrderAck(ok=True, order_no=order_no, msg="체결조회 미구현(포털 주문체결조회 연동 예정)")


# ────────────────────────── self-test (네트워크 없음) ──────────────────────────
def _self_test():
    sys.path.insert(0, BASE)
    from jq_broker_base import OrderReq
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    keys = dict(appkey="AK", appsecret="AS", account="12345678", account_prod="01")
    kb = KISBroker(paper=True, keys=keys)
    kb._token = "TOK"

    chk("기본 모의투자 도메인 :29443", kb.base.endswith(":29443"))
    chk("모의 매수 tr_id VTTC0802U", kb._trid("buy") == "VTTC0802U")
    chk("모의 매도 tr_id VTTC0801U", kb._trid("sell") == "VTTC0801U")

    # 실계좌 안전핀
    try: KISBroker(paper=False, keys=keys); locked = False
    except RuntimeError: locked = True
    chk("실계좌는 allow_real 없이는 생성 거부", locked)
    kbr = KISBroker(paper=False, allow_real=True, keys=keys)
    chk("실계좌 도메인 :9443", kbr.base.endswith(":9443"))
    chk("실전 매수 tr_id TTTC0802U", kbr._trid("buy") == "TTTC0802U")

    # 주문 바디 — 지정가
    o = OrderReq(code="005930", side="buy", qty=10, price=70000)
    b = kb._order_body(o)
    chk("바디 PDNO=005930", b["PDNO"] == "005930")
    chk("바디 지정가 ORD_DVSN=00", b["ORD_DVSN"] == "00")
    chk("바디 수량 문자열 '10'", b["ORD_QTY"] == "10")
    chk("바디 단가 '70000'", b["ORD_UNPR"] == "70000")
    chk("바디 CANO/PRDT", b["CANO"] == "12345678" and b["ACNT_PRDT_CD"] == "01")

    # 주문 바디 — 시장가
    m = OrderReq(code="000660", side="sell", qty=3, ordtype="market")
    bm = kb._order_body(m)
    chk("시장가 ORD_DVSN=01·단가0", bm["ORD_DVSN"] == "01" and bm["ORD_UNPR"] == "0")

    # 헤더 — 모의 매수/매도 tr_id 및 hashkey/토큰
    h = kb._order_headers("buy", "HASHV")
    chk("헤더 tr_id=VTTC0802U", h["tr_id"] == "VTTC0802U")
    chk("헤더 Bearer 토큰", h["authorization"] == "Bearer TOK")
    chk("헤더 hashkey 반영", h["hashkey"] == "HASHV")
    chk("헤더 custtype=P", h["custtype"] == "P")
    hs = kb._order_headers("sell", "H2")
    chk("헤더 매도 tr_id=VTTC0801U", hs["tr_id"] == "VTTC0801U")

    # 환경변수 키 로드
    os.environ["KIS_APPKEY"] = "ENVK"
    k2 = KISBroker._load_keys("/nonexistent.json")
    chk("환경변수 appkey 로드", k2["appkey"] == "ENVK")
    chk("account_prod 기본 '01'", k2["account_prod"] == "01")

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--price", type=str, help="모의 현재가 조회(키 필요)")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    if a.price:
        kb = KISBroker(paper=True)
        print(f"{a.price} 현재가(모의): {kb.price(a.price):,}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
