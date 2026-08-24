#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""broker/kis.py — 한국투자증권 KIS Developers 어댑터 (모의투자 우선) · 개선안 ⑥

진우_증권사API_설계.md §3 채택: KIS 1순위(문서·파이썬 예제·모의도메인 분리).
흐름: App Key/Secret → access_token → (매수 시 hashkey) → 현금주문(tr_id로 실전/모의 구분)
      → 주문번호(ODNO) → 잔고/체결 조회.

★ 안전 설계
  · 기본 paper=True. 모의 도메인(openapivts, 포트 29443) 고정. 실전은 명시적으로만.
  · 키는 코드에 절대 하드코딩 금지 → 로컬 파일 .kis_key.json 에서만 로드(.gitignore 필수).
  · tr_id 가 실전/모의를 가른다(오발주 방지): 매수 VTTC0802U(모의)/TTTC0802U(실전) 등.

.kis_key.json 예시(진우 PC, 이 폴더 또는 상위):
  { "app_key":"...", "app_secret":"...", "cano":"50123456", "acnt_prdt_cd":"01" }
  (cano=계좌 앞 8자리, acnt_prdt_cd=뒤 2자리. 모의계좌는 KIS 포털에서 발급)

선행: pip install requests
사용:
  py broker/kis.py --selftest        # 네트워크 없이 서명·페이로드 조립 검증(가짜 키)
  py broker/kis.py --price 005930    # 실제 현재가(키 필요·PC)
  from broker.kis import KIS ; b=KIS(paper=True); b.auth(); b.price("005930")

⚠️ 실집행은 진우 PC에서 모의계좌로만 시작. 실전 전환 전 §3-2·3-3 통과 필수. 투자자문 아님·책임 본인.
"""
import os, sys, json, time
try:
    from .base import Broker, OrderReq, OrderAck
except Exception:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from base import Broker, OrderReq, OrderAck

PAPER_HOST = "https://openapivts.koreainvestment.com:29443"   # 모의투자
LIVE_HOST  = "https://openapi.koreainvestment.com:9443"        # 실전(신중)

# tr_id: 모의(V…) vs 실전(T…). 국내주식 현금주문/잔고/시세.
TRID = {
    "buy":   {"paper":"VTTC0802U", "live":"TTTC0802U"},
    "sell":  {"paper":"VTTC0801U", "live":"TTTC0801U"},
    "balance":{"paper":"VTTC8434R","live":"TTTC8434R"},
    "price": {"paper":"FHKST01010100","live":"FHKST01010100"},  # 시세는 공통
}

def load_keys(path=None):
    """.kis_key.json 로드. 코드/레포에 키를 두지 않기 위한 유일 경로."""
    cands=[]
    if path: cands.append(path)
    here=os.path.dirname(os.path.abspath(__file__))
    cands += [os.path.join(here,".kis_key.json"),
              os.path.join(os.path.dirname(here),".kis_key.json"),
              os.path.join(os.getcwd(),".kis_key.json")]
    for c in cands:
        if os.path.exists(c):
            with open(c, encoding="utf-8") as f: return json.load(f), c
    return None, None

class KIS(Broker):
    def __init__(self, paper=True, key_path=None, timeout=7):
        super().__init__(paper=paper)
        self.host = PAPER_HOST if paper else LIVE_HOST
        self.timeout=timeout
        self.keys, self.key_src = load_keys(key_path)
        self.token=None
        self._mode = "paper" if paper else "live"

    # ── 인증 ──
    def auth(self):
        import requests
        if not self.keys: raise RuntimeError(".kis_key.json 없음 — 키 파일 필요(PC 로컬)")
        r=requests.post(f"{self.host}/oauth2/tokenP", timeout=self.timeout,
                        json={"grant_type":"client_credentials",
                              "appkey":self.keys["app_key"], "appsecret":self.keys["app_secret"]})
        r.raise_for_status(); self.token=r.json()["access_token"]; self._authed=True
        return True

    def _headers(self, tr_id, hashkey=None):
        h={"content-type":"application/json; charset=utf-8",
           "authorization":f"Bearer {self.token}",
           "appkey":self.keys["app_key"], "appsecret":self.keys["app_secret"],
           "tr_id":tr_id, "custtype":"P"}
        if hashkey: h["hashkey"]=hashkey
        return h

    def _hashkey(self, body):
        """매수/매도 바디 위변조 방지 해시(KIS 요구)."""
        import requests
        r=requests.post(f"{self.host}/uapi/hashkey", timeout=self.timeout,
                        headers={"content-type":"application/json; charset=utf-8",
                                 "appkey":self.keys["app_key"], "appsecret":self.keys["app_secret"]},
                        data=json.dumps(body))
        r.raise_for_status(); return r.json()["HASH"]

    # ── 시세 ──
    def price(self, code):
        import requests
        try:
            r=requests.get(f"{self.host}/uapi/domestic-stock/v1/quotations/inquire-price",
                           timeout=self.timeout, headers=self._headers(TRID["price"][self._mode]),
                           params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":code})
            r.raise_for_status(); return int(r.json()["output"]["stck_prpr"])
        except Exception as e:
            print(f"  price({code}) 실패: {e}"); return 0

    # ── 잔고 ──
    def balance(self):
        import requests
        params={"CANO":self.keys["cano"],"ACNT_PRDT_CD":self.keys["acnt_prdt_cd"],
                "AFHR_FLPR_YN":"N","OFL_YN":"","INQR_DVSN":"02","UNPR_DVSN":"01",
                "FUND_STTL_ICLD_YN":"N","FNCG_AMT_AUTO_RDPT_YN":"N","PRCS_DVSN":"01",
                "CTX_AREA_FK100":"","CTX_AREA_NK100":""}
        r=requests.get(f"{self.host}/uapi/domestic-stock/v1/trading/inquire-balance",
                       timeout=self.timeout, headers=self._headers(TRID["balance"][self._mode]), params=params)
        r.raise_for_status(); j=r.json()
        pos={}
        for it in j.get("output1",[]):
            q=int(it.get("hldg_qty",0))
            if q>0: pos[it["pdno"]]={"qty":q,"avg":float(it.get("pchs_avg_pric",0))}
        out2=(j.get("output2") or [{}])[0]
        cash=int(float(out2.get("dnca_tot_amt",0)))
        equity=int(float(out2.get("tot_evlu_amt",cash)))
        return dict(cash=cash, equity=equity, positions=pos)

    # ── 주문 ──
    def _order_body(self, order: OrderReq):
        return {"CANO":self.keys["cano"], "ACNT_PRDT_CD":self.keys["acnt_prdt_cd"],
                "PDNO":order.code, "ORD_DVSN":"00" if order.price>0 else "01",   # 00 지정가/01 시장가
                "ORD_QTY":str(int(order.qty)), "ORD_UNPR":str(int(order.price))}

    def submit(self, order: OrderReq) -> OrderAck:
        import requests
        try:
            body=self._order_body(order)
            hk=self._hashkey(body)
            tr=TRID[order.side][self._mode]
            r=requests.post(f"{self.host}/uapi/domestic-stock/v1/trading/order-cash",
                            timeout=self.timeout, headers=self._headers(tr, hashkey=hk), data=json.dumps(body))
            j=r.json()
            if j.get("rt_cd")=="0":
                o=j.get("output",{})
                return OrderAck(True, order_no=o.get("ODNO",""), filled_qty=int(order.qty),
                                avg_price=order.price, raw=j)
            return OrderAck(False, error=j.get("msg1","주문거절"), raw=j)
        except Exception as e:
            return OrderAck(False, error=str(e))

# ────────────────────────── self-test (네트워크 없이 조립 검증) ──────────────────────────
def _selftest():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 가짜 키 주입(파일 없이도 조립 로직 검증)
    b=KIS(paper=True); b.keys={"app_key":"AK","app_secret":"AS","cano":"50123456","acnt_prdt_cd":"01"}
    chk("모의 호스트 고정", b.host==PAPER_HOST and ":29443" in b.host)
    chk("모드=paper", b._mode=="paper")
    chk("매수 tr_id=모의(V…)", TRID["buy"]["paper"].startswith("V"))
    chk("실전 tr_id=T… 분리", TRID["buy"]["live"].startswith("T"))
    body=b._order_body(OrderReq("005930","buy",10,70000))
    chk("주문바디 지정가 ORD_DVSN=00", body["ORD_DVSN"]=="00")
    chk("주문바디 수량/단가 문자열", body["ORD_QTY"]=="10" and body["ORD_UNPR"]=="70000")
    body2=b._order_body(OrderReq("005930","buy",10,0))
    chk("시장가 ORD_DVSN=01", body2["ORD_DVSN"]=="01")
    h=b._headers("VTTC0802U")
    chk("헤더 tr_id 반영", h["tr_id"]=="VTTC0802U" and h["custtype"]=="P")
    # 실전 어댑터는 호스트/모드가 바뀌는지
    live=KIS(paper=False); chk("실전 호스트 분리", live.host==LIVE_HOST)
    print(f"\n셀프테스트: {ok}/{tot}  (네트워크·실주문 없음 — 조립·분기만 검증)")
    print("실제 시세/주문은 진우 PC에서 .kis_key.json + 모의계좌로: py broker/kis.py --price 005930")
    return ok==tot

def main():
    import argparse
    ap=argparse.ArgumentParser(description="KIS 어댑터(모의 우선)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--price", help="현재가 조회(키 필요)")
    ap.add_argument("--live", action="store_true", help="실전(신중 — 기본 모의)")
    a=ap.parse_args()
    if a.selftest: return 0 if _selftest() else 1
    if a.price:
        b=KIS(paper=not a.live)
        if not b.keys: print("키 없음(.kis_key.json 필요)"); return 1
        b.auth(); print(f"{a.price} 현재가: {b.price(a.price):,}원  ({'실전' if a.live else '모의'})")
    else:
        print(__doc__)
    return 0

if __name__=="__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    sys.exit(main())
