# -*- coding: utf-8 -*-
"""jq_kakao.py — 카카오톡 '나에게 보내기' 공용 모듈 (진우퀀트)
================================================================================
목적 : 카드뉴스 PNG/텍스트를 진우님 카카오톡 '나와의 채팅방'으로 자동 발송.
방식 : 카카오 REST API (developers.kakao.com) 나에게 보내기(memo/default/send).
       - 이미지 카드: message/image/upload 로 카카오 서버에 올려 image_url 확보 → feed 템플릿 발송.
       - 실패/미설정 시: text 템플릿(요약문 + 링크)으로 폴백(항상 전송되는 안전장치).
인증 : OAuth refresh_token 을 jq_kakao_config.txt 에 저장해 두고, 실행 때마다
       access_token 을 자동 재발급(캐시). 최초 1회 발급은 jq_kakao_auth.py 참고.
설정 : jq_kakao_config.txt (KEY=VALUE, UTF-8)
       REST_API_KEY=...        (카카오 앱 REST API 키)
       REDIRECT_URI=...        (앱에 등록한 리다이렉트 URI, 인증 때만 사용)
       REFRESH_TOKEN=...       (jq_kakao_auth.py 로 발급, 자동 갱신됨)
       IMAGE_BASE_URL=         (선택: 카드 PNG를 공개 서빙하는 https 주소 접두어)
한글경로 SSL : 배치(jq_kakao_send.bat)가 C:\\Users\\Public\\jq_cacert.pem 로
       인증서를 복사하고 REQUESTS_CA_BUNDLE 등을 지정함(기존 jq_cards_run.bat 동일 패턴).
사용 : import 해서 send_image()/send_text() 호출. 단독: python jq_kakao.py --selftest
"""
import os, sys, json, time, glob
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

def _pick_encoding(is_win, cp):
    """콘솔 코드페이지(cp)에 맞는 파이썬 인코딩 이름을 고름(순수함수, 테스트용).
    비Windows=utf-8, 65001=utf-8, 그 외 코드페이지=cpNNN, 알 수 없으면 cp949."""
    if not is_win:
        return "utf-8"
    if not cp:
        return "cp949"
    return "utf-8" if cp == 65001 else ("cp%d" % cp)


def setup_console():
    """콘솔/파이프 출력 인코딩을 '실제 콘솔 코드페이지'에 맞춤.
    한글 사용자경로 PC의 PowerShell/cmd는 보통 CP949라, 파이썬이 UTF-8 바이트를
    그대로 뿌리면 한글이 깨짐(mojibake). chcp 사용하지 않고(기존 함정 회피),
    콘솔이 949면 949로, 65001이면 utf-8로 자동 감지해 emit → 어떤 콘솔에서도 안 깨짐.
    (이모지 등 CP949로 표현 불가한 문자는 '?'로 대체되며, 실제 카톡 메시지는 영향 없음.)
    발송/토큰 로직과 무관한 '표시 전용' 설정."""
    is_win = sys.platform.startswith("win")
    cp = 0
    if is_win:
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetConsoleOutputCP() or ctypes.windll.kernel32.GetACP()
        except Exception:
            cp = 0
    enc = _pick_encoding(is_win, cp)
    for _name in ("stdout", "stderr"):
        _s = getattr(sys, _name, None)
        if _s is None:
            continue
        try:
            _s.reconfigure(encoding=enc, errors="replace")
        except Exception:
            pass


setup_console()

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "jq_kakao_config.txt")
TOKEN_CACHE = os.path.join(HERE, "jq_kakao_token.json")

AUTH_HOST = "https://kauth.kakao.com"
API_HOST = "https://kapi.kakao.com"
TOKEN_URL = AUTH_HOST + "/oauth/token"
IMG_UPLOAD_URL = API_HOST + "/v2/api/talk/message/image/upload"
MEMO_SEND_URL = API_HOST + "/v2/api/talk/memo/default/send"
SCOPE = "talk_message"


# ------------------------------------------------------------------ 설정 I/O
def load_config():
    cfg = {}
    if os.path.exists(CONFIG):
        for ln in open(CONFIG, encoding="utf-8-sig"):
            ln = ln.rstrip("\n")
            if ln.strip().startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def save_config_value(key, value):
    """config 파일에서 key 라인만 교체(없으면 추가). 다른 라인·주석 보존."""
    lines, found = [], False
    if os.path.exists(CONFIG):
        for ln in open(CONFIG, encoding="utf-8-sig"):
            raw = ln.rstrip("\n")
            if "=" in raw and not raw.strip().startswith("#") and raw.split("=", 1)[0].strip() == key:
                lines.append(f"{key}={value}"); found = True
            else:
                lines.append(raw)
    if not found:
        lines.append(f"{key}={value}")
    with open(CONFIG, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ------------------------------------------------------------------ 인증서(SSL)
def ensure_ca():
    """한글 사용자경로 SSL 이슈 회피: 인증서를 ASCII 경로로 복사 후 환경변수 지정.
    배치에서 이미 지정했다면 그대로 두고, 아니면 여기서 보강."""
    if os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists(os.environ["REQUESTS_CA_BUNDLE"]):
        return
    try:
        import certifi, shutil
        dst = r"C:\Users\Public\jq_cacert.pem"
        try:
            shutil.copyfile(certifi.where(), dst)
        except Exception:
            dst = certifi.where()
        for k in ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE"):
            os.environ.setdefault(k, dst)
    except Exception:
        pass


def _ssl_ctx():
    import ssl
    ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    try:
        if ca and os.path.exists(ca):
            return ssl.create_default_context(cafile=ca)
    except Exception:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


# ------------------------------------------------------------------ HTTP (stdlib)
def _read_json(raw):
    txt = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw
    try:
        return json.loads(txt)
    except Exception:
        return {"_raw": txt}


def _send_request(req, timeout):
    """urlopen 실행. 4xx/5xx도 예외 대신 (status, body) 로 반환.
    SSL 실패 시 certifi 컨텍스트로 1회 재시도(한글경로 이슈 대비)."""
    import ssl
    try:
        with urlopen(req, context=_ssl_ctx(), timeout=timeout) as r:
            return r.status, _read_json(r.read())
    except HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, _read_json(body)
    except (URLError, ssl.SSLError) as e:
        # SSL/네트워크 오류 → certifi 명시 컨텍스트로 재시도
        try:
            import ssl as _ssl, certifi
            ctx = _ssl.create_default_context(cafile=certifi.where())
            with urlopen(req, context=ctx, timeout=timeout) as r:
                return r.status, _read_json(r.read())
        except HTTPError as e2:
            try:
                body = e2.read()
            except Exception:
                body = b""
            return e2.code, _read_json(body)
        except Exception as e2:
            return 0, {"_error": f"{type(e2).__name__}: {e2}", "_orig": f"{type(e).__name__}: {e}"}


def _post_form(url, data, headers=None):
    body = urlencode(data).encode("utf-8")
    h = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
    if headers:
        h.update(headers)
    req = Request(url, data=body, headers=h, method="POST")
    return _send_request(req, 30)


def _post_multipart(url, field, filepath, headers=None):
    """단일 파일 multipart/form-data POST (stdlib만 사용)."""
    import uuid, mimetypes
    boundary = "----jqk" + uuid.uuid4().hex
    fn = os.path.basename(filepath)
    ctype = mimetypes.guess_type(fn)[0] or "image/png"
    with open(filepath, "rb") as fp:
        content = fp.read()
    pre = (f"--{boundary}\r\n"
           f'Content-Disposition: form-data; name="{field}"; filename="{fn}"\r\n'
           f"Content-Type: {ctype}\r\n\r\n").encode("utf-8")
    post = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = pre + content + post
    h = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if headers:
        h.update(headers)
    req = Request(url, data=body, headers=h, method="POST")
    return _send_request(req, 60)


# ------------------------------------------------------------------ 토큰
def _refresh_access_token(cfg):
    rt = cfg.get("REFRESH_TOKEN", "")
    key = cfg.get("REST_API_KEY", "")
    if not rt or not key:
        raise RuntimeError("REST_API_KEY 또는 REFRESH_TOKEN 미설정 — jq_kakao_auth.py 로 최초 인증 필요")
    data = {"grant_type": "refresh_token", "client_id": key, "refresh_token": rt}
    if cfg.get("CLIENT_SECRET"):
        data["client_secret"] = cfg["CLIENT_SECRET"]
    st, res = _post_form(TOKEN_URL, data)
    if "access_token" not in res:
        raise RuntimeError(f"토큰 갱신 실패: {res}")
    # 리프레시 토큰이 갱신되어 내려오면 config에 반영(카카오는 만료 1개월 이하일 때 재발급)
    if res.get("refresh_token"):
        save_config_value("REFRESH_TOKEN", res["refresh_token"])
    tok = {"access_token": res["access_token"],
           "expires_at": time.time() + int(res.get("expires_in", 3600)) - 120}
    try:
        json.dump(tok, open(TOKEN_CACHE, "w"))
    except Exception:
        pass
    return tok["access_token"]


def get_access_token(cfg=None):
    cfg = cfg or load_config()
    if os.path.exists(TOKEN_CACHE):
        try:
            tok = json.load(open(TOKEN_CACHE))
            if tok.get("access_token") and tok.get("expires_at", 0) > time.time():
                return tok["access_token"]
        except Exception:
            pass
    return _refresh_access_token(cfg)


# ------------------------------------------------------------------ 전송 프리미티브
def upload_image(access_token, filepath):
    """PNG를 카카오 서버에 업로드 → image_url 반환. 실패 시 None."""
    st, res = _post_multipart(IMG_UPLOAD_URL, "file", filepath,
                              headers={"Authorization": "Bearer " + access_token})
    try:
        return res["infos"]["original"]["url"]
    except Exception:
        return None


def _png_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def _build_feed(image_url, title, description, link_url=None):
    """feed 카드 페이로드. link_url 이 없으면 content.link 자체를 넣지 않음.
    카카오 '자세히 보기' 기본 버튼은 content.link 로부터 생성되므로,
    link 를 아예 빼면 버튼이 생기지 않는다(공식 문서: 링크 미설정 시 버튼 미노출).
    → 죽은 localhost 링크가 카드에 노출되지 않음. 이미지 탭은 확대뷰로 동작.
    link_url 을 명시하면(등록된 웹 도메인 사용 시) 그 링크로 버튼이 생성됨."""
    content = {
        "title": title[:100],
        "description": (description or "")[:200],
        "image_url": image_url,
    }
    if link_url:
        content["link"] = {"web_url": link_url, "mobile_web_url": link_url}
    return {"object_type": "feed", "content": content}


def _build_text(text, link_url=None):
    """text 페이로드. link_url 없으면 link 생략(단, 카카오는 link 필수라 실제 전송 시엔 link 필요)."""
    obj = {"object_type": "text", "text": text[:1000]}
    if link_url:
        obj["link"] = {"web_url": link_url, "mobile_web_url": link_url}
    return obj


def _to_https(url):
    """버튼 링크는 https 로. (등록 도메인 https://k.kakaocdn.net 와 스킴 일치 목적)"""
    if isinstance(url, str) and url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


def send_feed(access_token, image_url, title, description, link_url=None):
    obj = _build_feed(image_url, title, description, link_url)
    st, res = _post_form(MEMO_SEND_URL,
                         {"template_object": json.dumps(obj, ensure_ascii=False)},
                         headers={"Authorization": "Bearer " + access_token})
    return res.get("result_code") == 0, res


def send_text(access_token, text, link_url=None):
    obj = _build_text(text, link_url)
    st, res = _post_form(MEMO_SEND_URL,
                         {"template_object": json.dumps(obj, ensure_ascii=False)},
                         headers={"Authorization": "Bearer " + access_token})
    return res.get("result_code") == 0, res


# ------------------------------------------------------------------ 상위 API
def card_link(image_url, cfg):
    """버튼(자세히 보기)이 열 링크 결정.
    - CARD_LINK_URL 이 설정돼 있으면 그 값(그 도메인을 웹 도메인에 등록해야 열림).
    - 없으면 업로드된 카드 이미지의 https URL → 누르면 카드 이미지가 브라우저에 뜸.
      (이때 image 호스트 k.kakaocdn.net 를 앱 웹 도메인에 등록해야 치환 안 됨)"""
    custom = cfg.get("CARD_LINK_URL", "").strip()
    return custom or _to_https(image_url)


def send_image(access_token, filepath, title, description="", cfg=None):
    """카드 1장 발송. IMAGE_BASE_URL 있으면 그 URL, 없으면 업로드 → feed(버튼 링크 포함).
    content.link 는 카카오 필수(-2 방지). 버튼 링크는 card_link()로 결정하며,
    해당 도메인을 앱 [제품 링크 관리 > 웹 도메인]에 등록하면 localhost 치환 없이 실제로 열림.
    (성공여부, 방식) 반환."""
    cfg = cfg or load_config()
    fn = os.path.basename(filepath)
    image_url = None
    base = cfg.get("IMAGE_BASE_URL", "").strip()
    if base:
        image_url = base.rstrip("/") + "/" + fn
    else:
        try:
            image_url = upload_image(access_token, filepath)
        except Exception as e:
            print(f"    [업로드 실패] {fn}: {e}")
    if image_url:
        link = card_link(image_url, cfg)
        try:
            ok, res = send_feed(access_token, image_url, title, description, link_url=link)
            if ok:
                print(f"    [링크] {link}")  # 이 호스트를 웹 도메인에 등록하면 버튼이 정상 오픈
                return True, "feed"
            print(f"    [feed 실패] {fn}: {res}")
        except Exception as e:
            print(f"    [feed 예외] {fn}: {e}")
    # 폴백: 텍스트 (카카오 필수 link 포함)
    try:
        flink = cfg.get("CARD_LINK_URL", "").strip() or "https://k.kakaocdn.net"
        ok, res = send_text(access_token, f"{title}\n{description}\n(이미지 전송 실패 — 폴더에서 확인)", link_url=flink)
        return ok, "text-fallback"
    except Exception as e:
        print(f"    [text 폴백 예외] {fn}: {e}")
        return False, "fail"


# ------------------------------------------------------------------ 셀프테스트
def _selftest():
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 설정 파서 (시스템 임시폴더 사용 — 프로젝트 폴더 오염 방지)
    import tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "_jqk_selftest_cfg.txt")
    open(tmp, "w", encoding="utf-8").write("# 주석\nREST_API_KEY=abc123\nREFRESH_TOKEN=rt_xyz\nIMAGE_BASE_URL=https://ex.com/c\n")
    globals()["CONFIG"] = tmp
    c = load_config()
    chk("설정 파싱 REST_API_KEY", c.get("REST_API_KEY") == "abc123")
    chk("설정 파싱 REFRESH_TOKEN", c.get("REFRESH_TOKEN") == "rt_xyz")
    chk("주석 무시", "# 주석" not in c)
    save_config_value("REFRESH_TOKEN", "rt_new")
    save_config_value("NEW_KEY", "v")
    c2 = load_config()
    chk("값 교체 유지", c2.get("REFRESH_TOKEN") == "rt_new" and c2.get("REST_API_KEY") == "abc123")
    chk("신규 키 추가", c2.get("NEW_KEY") == "v")
    # 템플릿 JSON 구성(전송은 안 함) — 실제 빌더 함수 사용
    obj_feed = _build_feed("https://ex.com/c/시장브리핑_카톡.png", "t", "d")
    j = json.dumps(obj_feed, ensure_ascii=False)
    chk("feed JSON 한글 보존", "시장브리핑" in j and "feed" in j)
    # 버튼 제거의 핵심: 무링크 feed 는 content.link 자체가 없어야 함(→ 자세히 보기 버튼 미노출)
    chk("무링크 feed: content.link 없음", "link" not in obj_feed["content"])
    chk("무링크 feed: buttons 키 없음", "buttons" not in obj_feed)
    chk("무링크 feed: 이미지 유지", obj_feed["content"].get("image_url", "").endswith(".png"))
    # 링크 명시 시에는 link 포함(등록 도메인 사용 케이스)
    obj_feed_l = _build_feed("https://ex.com/i.png", "t", "d", link_url="https://ex.com/i.png")
    chk("링크 feed: content.link 포함", obj_feed_l["content"].get("link", {}).get("web_url") == "https://ex.com/i.png")
    obj_text = _build_text("hello")
    chk("무링크 text: link 없음", "link" not in obj_text)
    # 이미지 URL 조합 로직(base 있을 때)
    base = "https://ex.com/c"
    url = base.rstrip("/") + "/" + "마감브리핑_카톡.png"
    chk("IMAGE_BASE_URL 조합", url == "https://ex.com/c/마감브리핑_카톡.png")
    # 버튼 링크 로직: http→https 변환, 기본=이미지 https, custom 우선
    chk("http→https 변환", _to_https("http://k.kakaocdn.net/dn/a/i.png") == "https://k.kakaocdn.net/dn/a/i.png")
    chk("card_link 기본=이미지https", card_link("http://k.kakaocdn.net/dn/a/i.png", {}) == "https://k.kakaocdn.net/dn/a/i.png")
    chk("card_link custom 우선", card_link("http://k.kakaocdn.net/dn/a/i.png", {"CARD_LINK_URL": "https://my.site/x"}) == "https://my.site/x")
    # 콘솔 인코딩 자동 감지
    chk("enc: 비Windows→utf-8", _pick_encoding(False, 0) == "utf-8")
    chk("enc: 콘솔 949→cp949", _pick_encoding(True, 949) == "cp949")
    chk("enc: 콘솔 65001→utf-8", _pick_encoding(True, 65001) == "utf-8")
    chk("enc: 감지실패→cp949", _pick_encoding(True, 0) == "cp949")
    try:
        os.remove(tmp)
    except Exception:
        pass
    globals()["CONFIG"] = os.path.join(HERE, "jq_kakao_config.txt")
    print(f"✅ jq_kakao 셀프테스트 ({ok}/19)")
    return ok == 19


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    print(__doc__)
