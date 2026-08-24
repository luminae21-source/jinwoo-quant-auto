#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""kakao_send_recommend.py — 추천/매도신호 요약을 카카오톡 '나에게' 발송

recommend_dashboard.py 가 저장한 추천대시보드_결과.json 을 읽어 ≤1000자 텍스트로
요약해 진우님 기존 jq_kakao.send_text() 로 발송(토큰/설정 재사용).
사용: py kakao_send_recommend.py   (recommend_pipeline 마지막에 자동 호출)
⚠️ 정보·검증용·투자자문 아님·책임 본인.
"""
import os, sys, json
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
sys.path.insert(0, PARENT); sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def find(name):
    for d in (HERE,PARENT):
        p=os.path.join(d,name)
        if os.path.exists(p): return p
    return None

def build_text(D):
    pym=D.get("pym","?"); fym=D.get("fym","?")
    L=[f"[진우퀀트] 추천 {pym} (재무 {fym})"]
    # 매도신호(중요: sev>=2)
    sells=[h for h in D.get("holds",[]) if h.get("sev",0)>=2]
    if sells:
        L.append("■ 보유 매도신호")
        for h in sells[:5]:
            L.append(f"· {h['name']} {h['signal']} ({h.get('ret',0):+.0f}%)")
    warns=[h for h in D.get("holds",[]) if h.get("sev",0)==1]
    if warns:
        L.append("■ 보유 주의: "+", ".join(h['name'] for h in warns[:5]))
    # 추천 A진입 상위
    def top(track,label):
        rows=D.get(track,[])[:4]
        if not rows: return
        L.append(f"■ {label}")
        for r in rows:
            L.append(f"· {r['name']} 비중{r['weight']:.1f}% 손절{r['stop']:,.0f}")
    top("value","가치 트랙"); top("growth","성장 트랙")
    L.append("※ 정보용·투자자문 아님·책임 본인")
    t="\n".join(L)
    return t[:990]

def send_text_nolink(K, tok, text):
    """카카오 '나에게 보내기' text 발송.

    [실측 확인 2026-07-28]
      카카오 memo text 템플릿은 link 를 비워도(link={}) '자세히 보기' 버튼을 항상 붙이고,
      열 주소가 없으면 앱에 등록된 웹 도메인(= REDIRECT_URI 호스트 localhost:8910)으로
      보내버린다 → 폰에서 ERR_CONNECTION_REFUSED.
      따라서 버튼을 없앨 방법은 없고, '열리는 실제 주소'를 주는 것만이 해결책이다.

    순서: ① CARD_LINK_URL(앱 웹 도메인에 등록해 둔 실주소)  ② link={}  ③ kakaocdn
    반환: (ok, res, mode)
    """
    import json as _j
    cfg={}
    try: cfg=K.load_config() or {}
    except Exception: pass
    custom=(cfg.get("CARD_LINK_URL","") or "").strip()

    def post(obj):
        try:
            st,res=K._post_form(K.MEMO_SEND_URL,
                                {"template_object": _j.dumps(obj, ensure_ascii=False)},
                                headers={"Authorization":"Bearer "+tok})
            return res.get("result_code")==0, res
        except Exception as e:
            return False, {"error": str(e)}

    if custom:
        ok,res=K.send_text(tok, text, link_url=custom)
        if ok: return True,res,"custom"
    ok,res=post({"object_type":"text","text":text[:1000],"link":{}})
    if ok: return True,res,"nolink"
    ok,res=K.send_text(tok, text, link_url="https://k.kakaocdn.net")
    return ok,res,"cdn"


def main():
    p=find("추천대시보드_결과.json")
    if not p:
        print("추천대시보드_결과.json 없음 — recommend_dashboard 먼저 실행"); return
    D=json.load(open(p,encoding="utf-8"))
    text=build_text(D)
    if "--dry-run" in sys.argv or "--print" in sys.argv:
        print(text); return
    try:
        import jq_kakao as K
    except Exception as e:
        print("KAKAO SEND: SKIP (jq_kakao import fail:", e, ")"); return
    try:
        tok=K.get_access_token()
        if not tok:
            print("KAKAO SEND: FAIL (no token - run jq_kakao_auth.bat)"); return
        ok,res,mode=send_text_nolink(K, tok, text)
        if ok:
            note={"nolink":"no link (clean)","custom":"CARD_LINK_URL","cdn":"kakaocdn fallback"}.get(mode,mode)
            print(f"KAKAO SEND: OK [{note}] - check your KakaoTalk (me)")
        else:
            print(f"KAKAO SEND: FAIL ({res}) - run jq_kakao_auth.bat")
    except Exception as e:
        print("KAKAO SEND: ERROR", e)

def _selftest():
    import json as _j
    n=[0,0]
    def chk(name,cond):
        n[1]+=1; n[0]+=1 if cond else 0
        print(("  OK  " if cond else "  FAIL")+" "+name)

    class FakeK:
        MEMO_SEND_URL="u"
        def __init__(self, ok_nolink=True, cfg=None):
            self.ok_nolink=ok_nolink; self.cfg=cfg or {}; self.sent=[]
        def load_config(self): return self.cfg
        def _post_form(self, url, data, headers=None):
            obj=_j.loads(data["template_object"]); self.sent.append(obj)
            return 200, {"result_code": 0 if self.ok_nolink else -2}
        def send_text(self, tok, text, link_url=None):
            self.sent.append({"object_type":"text","text":text,
                              "link":{"web_url":link_url} if link_url else {}})
            return True, {"result_code":0}

    k1=FakeK(True)
    ok,res,mode=send_text_nolink(k1,"t","hello")
    chk("CARD_LINK_URL 없으면 link={} 사용", ok and mode=="nolink")
    chk("payload에 link 키 존재(카카오 필수)", "link" in k1.sent[0])
    chk("payload link는 빈 오브젝트", k1.sent[0]["link"]=={})
    chk("text 1000자 컷", len(_j.dumps(k1.sent[0]))>0)

    k2=FakeK(True, {"CARD_LINK_URL":"https://my.site/x"})
    ok,res,mode=send_text_nolink(k2,"t","hello")
    chk("CARD_LINK_URL 있으면 최우선", ok and mode=="custom")
    chk("custom 링크 반영", k2.sent[-1]["link"]["web_url"]=="https://my.site/x")
    chk("custom 성공시 link={} 시도 안 함", len(k2.sent)==1)

    k3=FakeK(False, {})
    ok,res,mode=send_text_nolink(k3,"t","hello")
    chk("CARD_LINK_URL 없으면 cdn 폴백", ok and mode=="cdn")

    D={"pym":"2026-07","fym":"2026-06",
       "holds":[{"name":"AA","signal":"추세이탈","ret":-12.0,"sev":2},
                {"name":"BB","signal":"주의","ret":3.0,"sev":1}],
       "value":[{"name":"VV","weight":4.2,"stop":13500}],
       "growth":[{"name":"GG","weight":3.1,"stop":22000}]}
    t=build_text(D)
    chk("요약 990자 이하", len(t)<=990)
    chk("매도신호 포함", "AA" in t and "추세이탈" in t)
    chk("면책 문구 포함", "투자자문 아님" in t)
    print(f"SELFTEST {n[0]}/{n[1]}")
    return n[0]==n[1]


if __name__=="__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    main()
