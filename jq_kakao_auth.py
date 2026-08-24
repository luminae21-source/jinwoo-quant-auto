# -*- coding: utf-8 -*-
"""jq_kakao_auth.py — 카카오 '나에게 보내기' 최초 1회 인증 (진우퀀트)
================================================================================
하는 일 : 브라우저로 카카오 로그인/동의 → 인가코드 수신 → 토큰 발급 →
          REFRESH_TOKEN 을 jq_kakao_config.txt 에 저장(+저장 검증). 로그는
          jq_kakao_auth_log.txt 에도 남음. 자동수신 실패 시 코드 수동입력 폴백.
사전준비 : jq_kakao_config.txt 에 REST_API_KEY, REDIRECT_URI 필요.
          REDIRECT_URI 는 카카오 앱에 '똑같이' 등록(기본: http://localhost:8910/oauth).
실행    : jq_kakao_auth.bat  또는  py -X utf8 jq_kakao_auth.py
"""
import os, sys, json, time, webbrowser, threading
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jq_kakao as K

K.setup_console()  # 콘솔 한글 안 깨지게(콘솔 코드페이지 자동 감지). 표시 전용.

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "jq_kakao_auth_log.txt")
_logf = None


def log(*args):
    msg = " ".join(str(a) for a in args)
    print(msg, flush=True)
    try:
        _logf.write(msg + "\n"); _logf.flush()
    except Exception:
        pass


_code_box = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if "code" in q:
            _code_box["code"] = q["code"][0]
            msg = "인증 완료! 이 창을 닫고 터미널로 돌아가세요."
        elif "error" in q:
            _code_box["error"] = q.get("error_description", q.get("error"))[0]
            msg = "카카오 인증 오류: " + msg_err(q)
        else:
            msg = "code 파라미터가 없습니다."
        self.wfile.write(f"<html><meta charset='utf-8'><body style='font-family:sans-serif;padding:40px'><h2>{msg}</h2></body></html>".encode("utf-8"))

    def log_message(self, *a):
        pass


def msg_err(q):
    return (q.get("error_description") or q.get("error") or ["?"])[0]


def exchange_and_save(cfg, key, redirect, code):
    """code → token 교환 후 REFRESH_TOKEN 저장 + 저장 검증. 성공 시 True."""
    data = {"grant_type": "authorization_code", "client_id": key,
            "redirect_uri": redirect, "code": code}
    if cfg.get("CLIENT_SECRET"):
        data["client_secret"] = cfg["CLIENT_SECRET"]
    log("● 토큰 교환 요청 중... (https://kauth.kakao.com/oauth/token)")
    try:
        st, res = K._post_form(K.TOKEN_URL, data)
    except Exception as e:
        log(f"❌ 토큰 교환 중 예외: {type(e).__name__}: {e}")
        return False
    log(f"  응답 status={st}")
    if not isinstance(res, dict) or "refresh_token" not in res:
        log(f"❌ 토큰 발급 실패. 카카오 응답: {res}")
        _hint(res)
        return False
    # 저장
    K.save_config_value("REFRESH_TOKEN", res["refresh_token"])
    if res.get("access_token"):
        try:
            json.dump({"access_token": res["access_token"],
                       "expires_at": time.time() + int(res.get("expires_in", 3600)) - 120},
                      open(K.TOKEN_CACHE, "w"))
        except Exception as e:
            log(f"  (토큰 캐시 저장 경고: {e})")
    # 저장 검증 — config를 다시 읽어 실제로 들어갔는지 확인
    cfg2 = K.load_config()
    saved = cfg2.get("REFRESH_TOKEN", "")
    if saved and saved == res["refresh_token"]:
        log("✅ 인증 성공! REFRESH_TOKEN 저장 확인 완료.")
        log(f"   저장 위치: {K.CONFIG}")
        log(f"   scope={res.get('scope')}  refresh_token 만료(초)={res.get('refresh_token_expires_in')}")
        log("   → 이제 jq_kakao_send.bat --all 로 발송 테스트하세요.")
        return True
    log(f"❌ REFRESH_TOKEN 저장 검증 실패! config에 값이 반영되지 않았습니다. 경로: {K.CONFIG}")
    log(f"   (수동조치) jq_kakao_config.txt 의 REFRESH_TOKEN= 뒤에 아래 값을 직접 붙여넣으세요:")
    log(f"   {res['refresh_token']}")
    return False


def _hint(res):
    s = json.dumps(res, ensure_ascii=False).lower()
    if "invalid_client" in s or "koe010" in s:
        log("   [힌트] Client Secret 문제일 수 있음 → 앱>보안의 Client Secret 을 껐거나,")
        log("          켰다면 그 값을 jq_kakao_config.txt 의 CLIENT_SECRET= 에 넣으세요.")
    if "koe320" in s or "redirect" in s or "invalid_grant" in s:
        log("   [힌트] Redirect URI 불일치 또는 코드 만료/재사용. 앱에 등록한 URI와")
        log("          config의 REDIRECT_URI 가 정확히 같은지 확인 후 다시 실행하세요.")
    if "scope" in s:
        log("   [힌트] 동의항목 talk_message 를 '사용'으로 켠 뒤 다시 인증하세요.")


def manual_fallback(cfg, key, redirect):
    log("")
    log("● (수동 폴백) 자동 수신이 안 됐습니다. 브라우저 주소창을 확인하세요.")
    log("  로그인/동의 후 이동된 주소가 다음과 같을 겁니다:")
    log(f"    {redirect}?code=XXXXXXXX...")
    log("  그 주소 전체(또는 code= 뒤의 값)를 붙여넣고 Enter:")
    try:
        raw = input("  코드/주소 > ").strip()
    except EOFError:
        return False
    code = raw
    if "code=" in raw:
        code = parse_qs(urlparse(raw).query).get("code", [raw])[0]
    if not code:
        log("  코드가 비어 있습니다. 종료.")
        return False
    return exchange_and_save(cfg, key, redirect, code)


def main():
    global _logf
    _logf = open(LOG, "w", encoding="utf-8")
    log(f"=== jq_kakao_auth {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    K.ensure_ca()
    cfg = K.load_config()
    key = cfg.get("REST_API_KEY", "").strip()
    redirect = cfg.get("REDIRECT_URI", "http://localhost:8910/oauth").strip()
    log(f"config 경로: {K.CONFIG}")
    log(f"REST_API_KEY 설정됨: {'예' if key else '아니오(비어있음)'}")
    log(f"REDIRECT_URI: {redirect}")
    if not key:
        log("❌ jq_kakao_config.txt 의 REST_API_KEY 가 비어 있습니다. 먼저 채우고 다시 실행하세요.")
        return 2

    pr = urlparse(redirect)
    host = pr.hostname or "localhost"
    port = pr.port or 8910

    auth_url = K.AUTH_HOST + "/oauth/authorize?" + urlencode({
        "client_id": key, "redirect_uri": redirect,
        "response_type": "code", "scope": K.SCOPE,
    })
    log("● 브라우저에서 카카오 로그인/동의를 진행하세요. (창이 자동으로 열립니다)")
    log("  자동으로 안 열리면 아래 주소를 복사해 붙여넣으세요:")
    log("  " + auth_url)

    server = None
    try:
        server = HTTPServer((host, port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        log(f"● http://{host}:{port} 에서 인가코드 대기 중... (최대 3분)")
    except Exception as e:
        log(f"  (로컬 서버 시작 실패: {e}) — 수동 입력으로 진행합니다.")

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    code = None
    if server is not None:
        for _ in range(180):
            if "code" in _code_box or "error" in _code_box:
                break
            time.sleep(1)
        try:
            server.shutdown()
        except Exception:
            pass
        if _code_box.get("error"):
            log(f"❌ 카카오가 오류를 반환했습니다: {_code_box['error']}")
            _hint({"error": _code_box["error"]})
            return 3
        code = _code_box.get("code")

    ok = False
    if code:
        log("● 인가코드 수신 완료 → 토큰 교환 진행")
        ok = exchange_and_save(cfg, key, redirect, code)
    else:
        log("● 자동 수신 실패(타임아웃/서버). 수동 입력 폴백으로 전환합니다.")
        ok = manual_fallback(cfg, key, redirect)

    if not ok:
        log("")
        log("※ 실패 원인은 위 메시지를 확인하세요. 로그: jq_kakao_auth_log.txt")
    return 0 if ok else 4


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        import traceback
        try:
            log("❌ 예기치 못한 오류:\n" + traceback.format_exc())
        except Exception:
            traceback.print_exc()
        rc = 9
    finally:
        try:
            _logf and _logf.close()
        except Exception:
            pass
    sys.exit(rc)
