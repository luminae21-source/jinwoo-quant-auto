#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
krx_openapi.py — KRX 공식 Open API(data-dbg.krx.co.kr) 탐색·수집 클라이언트
원칙: 공식 실데이터만. 실패=데이터부족. 가짜·추정 절대 금지.
인증키: krx_authkey.txt(파일 한 줄) 또는 환경변수 KRX_AUTH_KEY. ⚠️ 키는 채팅에 붙이지 말 것(로컬만).
구조: GET {BASE}/{분류}/{서비스}  헤더 AUTH_KEY  파라미터 basDd=YYYYMMDD → JSON OutBlock_1.
목적: 선물/옵션 일별매매(종가·미결제약정·거래량) + 지수(VKOSPI 검색)가 실제 오는지 확인 → v2 연동.
출력: 콘솔 + krx_openapi_결과.txt. [PC 실행]. production·기존 무수정.
"""
import sys, json, traceback
from datetime import date, timedelta
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from pathlib import Path
BASE_DIR = Path(__file__).parent.resolve()
OUT = []
def emit(s=""):
    print(s); OUT.append(s)

API = "http://data-dbg.krx.co.kr/svc/apis"

# 후보 서비스(공식 패턴 — 키 받은 뒤 실호출로 ✅확정). basDd=영업일.
CANDIDATES = [
    # ★ 확정 API ID (KRX Open API 서비스목록 2026-01 기준). 우리 5목표 우선순.
    ("지수: 파생상품지수(VKOSPI 후보)  drvprod_dd_trd", "idx/drvprod_dd_trd"),
    ("지수: KRX시리즈 일별(VKOSPI 백업)  krx_dd_trd", "idx/krx_dd_trd"),
    ("지수: KOSPI시리즈 일별(현물·베이시스용)  kospi_dd_trd", "idx/kospi_dd_trd"),
    ("파생: 선물 일별매매(종가+미결제약정)  fut_bydd_trd", "drv/fut_bydd_trd"),
    ("파생: 옵션 일별매매(풋/콜)  opt_bydd_trd", "drv/opt_bydd_trd"),
]


def auth_key():
    f = BASE_DIR / "krx_authkey.txt"
    if f.exists():
        # utf-8-sig = BOM 자동 제거. + 보이지 않는 BOM/제로폭/공백/따옴표 명시 제거(메모장 저장 대비)
        k = f.read_text(encoding="utf-8-sig")
        k = k.replace("\ufeff", "").replace("\u200b", "").strip()
        # 첫 비어있지 않은 줄만 사용(여러 줄/설명 방어). 주석(#)줄은 건너뜀.
        for ln in k.splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                k = ln; break
        # 'key=' / 'AUTH_KEY=' / 'authkey:' 같은 접두어 자동 제거
        import re as _re
        k = _re.sub(r'(?i)^\s*(auth[_-]?key|key)\s*[:=]\s*', '', k)
        k = k.strip().strip('"').strip("'").strip()
        if k:
            return k
    import os
    v = os.environ.get("KRX_AUTH_KEY")
    return v.strip() if v else None


def nearest_bday():
    try:
        from pykrx import stock
        return stock.get_nearest_business_day_in_a_week(date.today().strftime("%Y%m%d"))
    except Exception:
        d = date.today()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.strftime("%Y%m%d")


def recent_bdays(n=8):
    """오늘부터 과거로 평일(영업일 근사) YYYYMMDD 리스트. 휴장일은 빈배열로 자동 스킵됨."""
    out = []; d = date.today()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def call(path, key, basDd):
    import requests
    url = "%s/%s" % (API, path)
    try:
        r = requests.get(url, params={"basDd": basDd}, headers={"AUTH_KEY": key}, timeout=15)
        try:
            j = r.json()
        except Exception:
            j = None
        return r.status_code, j, (r.text[:400] if r.status_code != 200 else r.text[:200])
    except Exception as e:
        return None, None, "%s: %s" % (type(e).__name__, str(e)[:160])


def rows_of(j):
    if isinstance(j, dict):
        for k in ("OutBlock_1", "OutBlock", "output", "block1"):
            if isinstance(j.get(k), list):
                return j[k]
        for v in j.values():
            if isinstance(v, list) and v:
                return v
    return None


def scan_field(rows, keys):
    """행 컬럼명에 keys 중 하나라도 포함되면 (컬럼, 첫값) 반환."""
    if not rows:
        return None
    for c in rows[0].keys():
        if any(k in c for k in keys):
            return c, rows[0].get(c)
    return None


def main():
    key = auth_key()
    bd = nearest_bday()
    emit("=" * 60)
    emit("KRX 공식 Open API 탐색 — 기준일 %s" % bd)
    emit("원칙: 공식 실데이터만. 실패=데이터부족. 가짜 금지.")
    emit("=" * 60)
    if not key:
        emit("\n❌ 인증키 없음 — krx_authkey.txt(한 줄) 또는 KRX_AUTH_KEY 환경변수 설정 후 재실행.")
        emit("   신청: openapi.krx.co.kr 회원가입 → 마이페이지 'API 인증키 신청' → 서비스 이용신청.")
        (BASE_DIR / "krx_openapi_결과.txt").write_text("\n".join(OUT), encoding="utf-8")
        return
    emit("\n인증키: 로드됨(길이 %d, 값은 미표시)" % len(key))
    import re as _re
    _ws = bool(_re.search(r"\s", key))
    emit("  키 지문: 앞2='%s…%s' 뒤2 · 내부공백/줄바꿈 %s (발급내역 키와 길이·앞2/뒤2 일치하는지 대조)" % (
        key[:2], key[-2:], "있음 ⚠️키 손상 가능(복사 중 줄바꿈/공백)" if _ws else "없음"))

    vkospi_hit = None
    codes401 = [0]; codes_total = [0]
    for label, path in CANDIDATES:
        emit("\n[%s] GET %s" % (label, path))
        rows = None; used = None; st0 = None; raw0 = ""
        for d in recent_bdays(8):
            st, j, raw = call(path, key, d)
            codes_total[0]+=1
            if st==401: codes401[0]+=1
            if st0 is None: st0, raw0 = st, raw
            r = rows_of(j)
            if r:
                rows, used = r, d; break
        emit("  최초 HTTP=%s · raw앞: %s" % (st0, raw0[:160]))
        if not rows:
            emit("  ❌ 데이터부족(최근 8영업일 모두 빈배열 — 미발행/휴장·일시 오류 가능. 전 서비스는 승인 완료)")
            continue
        emit("  ✅ [%s] rows=%d · 컬럼: %s" % (used, len(rows), list(rows[0].keys())))
        emit("  샘플행: %s" % json.dumps(rows[0], ensure_ascii=False)[:300])
        # 미결제약정/거래량/풋콜/변동성 자동탐지
        oi = scan_field(rows, ["미결제", "약정", "OPNINT", "OI"])
        if oi:
            emit("  → 미결제약정(OI) 컬럼 발견: %s = %s" % oi)
        vk = [r for r in rows if any("변동성" in str(v) or "VKOSPI" in str(v).upper() for v in r.values())]
        if vk:
            vkospi_hit = (path, vk[0])
            emit("  → ★ VKOSPI/변동성지수 행 발견: %s" % json.dumps(vk[0], ensure_ascii=False)[:200])

    if codes401[0] and codes401[0] == codes_total[0]:
        emit("\n⚠️ 전 서비스 401(Unauthorized Key) — 코드형식은 정상(URL·AUTH_KEY헤더·BOM처리).")
        emit("   점검: ① 사용기간 시작일(승인일 다음/당일) 지났나 ② 키 재복사(공백/누락) ③ 활성 배치 지연(잠시 후 재시도)")
        emit("   키 길이 %d자 로드됨(값 미표시)." % (len(key)))
    emit("\n" + "=" * 60)
    emit("요약: ✅ 뜬 서비스만 v2 연동. VKOSPI=%s" % ("발견:" + vkospi_hit[0] if vkospi_hit else "미발견(서비스 추가신청/다른 idx 확인)"))
    emit("※ 선물·옵션 포함 전 서비스 승인 완료(2026-06). 빈배열이면 미발행/휴장 또는 일시 오류 — 가짜 금지, 재시도.")
    (BASE_DIR / "krx_openapi_결과.txt").write_text("\n".join(OUT), encoding="utf-8")
    emit("[저장] krx_openapi_결과.txt")


# ===== v2 브리핑 연동용 재사용 함수 (키워드 컬럼탐지 — 추정 아님, 못 찾으면 None) =====
def _num(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except Exception:
        return None

def _pick(rows, keys):
    """행 컬럼명에 keys 중 하나라도 포함하는 첫 컬럼명. 없으면 None."""
    if not rows:
        return None
    for c in rows[0].keys():
        if any(k in c for k in keys):
            return c
    return None

def _fetch(path, key, bd=None):
    """bd 우선 시도 → 비었으면 최근 영업일 역순으로 데이터 있는 첫날 사용. rows 반환."""
    seq = ([bd] if bd else []) + [d for d in recent_bdays(8) if d != bd]
    for d in seq:
        st, j, raw = call(path, key, d)
        rows = rows_of(j)
        if rows:
            return rows
    return None

def get_vkospi(key, bd=None):
    """파생상품지수에서 코스피200 변동성지수(VKOSPI). 확정컬럼 IDX_NM/CLSPRC_IDX/FLUC_RT. → (값, 등락%) or None."""
    rows = _fetch("idx/drvprod_dd_trd", key, bd) or _fetch("idx/krx_dd_trd", key, bd)
    if not rows:
        return None
    for r in rows:
        if "변동성" in str(r.get("IDX_NM", "")):
            v = _num(r.get("CLSPRC_IDX")); fl = _num(r.get("FLUC_RT"))
            if v is not None:
                return (v, fl)
    return None

def get_kospi200_spot(key, bd=None):
    """KOSPI200 현물 종가. 코스피 시리즈 IDX_NM '코스피 200'. → 값 or None."""
    rows = _fetch("idx/kospi_dd_trd", key, bd)
    if not rows:
        return None
    for r in rows:
        if str(r.get("IDX_NM", "")).replace(" ", "") in ("코스피200", "KOSPI200"):
            v = _num(r.get("CLSPRC_IDX"))
            if v is not None:
                return v
    return None

def get_futures_k200(key, bd=None):
    """코스피200 지수선물 정규·근월물: (종가, 미결제약정, 현물가SPOT) or None. 확정 컬럼."""
    rows = _fetch("drv/fut_bydd_trd", key, bd)
    if not rows:
        return None
    def is_k200(r):
        nm = (str(r.get("PROD_NM", "")) + str(r.get("ISU_NM", ""))).replace(" ", "")
        return ("코스피200" in nm) and ("주식" not in nm)   # 지수선물(주식선물 제외)
    reg = [r for r in rows if is_k200(r) and "정규" in str(r.get("MKT_NM", ""))]
    cand = reg or [r for r in rows if is_k200(r)]
    if not cand:
        return None
    cand.sort(key=lambda r: -(_num(r.get("ACC_OPNINT_QTY")) or 0))   # 미결제 최대=근월물
    top = cand[0]
    return (_num(top.get("TDD_CLSPRC")), _num(top.get("ACC_OPNINT_QTY")), _num(top.get("SPOT_PRC")))

def get_putcall_ratio(key, bd=None):
    """옵션 풋/콜 비율(전체 지수옵션·주식옵션外). 거래량·거래대금 PCR 둘 다.
    컬럼: 권리유형 RGHT_TP_NM(CALL/PUT), 거래량 ACC_TRDVOL, 거래대금 ACC_TRDVAL.
    → dict{vol, val, c_vol, p_vol, c_val, p_val} or None.
    NOTE: opt 응답이 대용량(~2만행)이라 requests에서 지연/타임아웃 발생 → urllib 직접 fetch(검증된 방식, timeout 40s)."""
    import urllib.request as _u, json as _j
    def _opt_rows(d):
        try:
            req = _u.Request("%s/drv/opt_bydd_trd?basDd=%s" % (API, d), headers={"AUTH_KEY": key})
            o = _j.loads(_u.urlopen(req, timeout=40).read().decode("utf-8", "replace"))
            return o.get("OutBlock_1", []) if isinstance(o, dict) else []
        except Exception:
            return []
    rows = None
    for d in ([bd] if bd else []) + [x for x in recent_bdays(8) if x != bd]:
        rows = _opt_rows(d)
        if rows:
            break
    if not rows:
        return None
    volcol = _pick(rows, ["ACC_TRDVOL", "거래량", "TRDVOL"])
    valcol = _pick(rows, ["ACC_TRDVAL", "거래대금", "TRDVAL"])
    rcol = _pick(rows, ["RGHT", "CP_", "콜풋", "권리"])
    if not volcol:
        return None
    def side(r):
        if rcol:
            t = str(r.get(rcol, ""))
            if t.upper().startswith(("C",)) or "콜" in t: return "C"
            if t.upper().startswith(("P",)) or "풋" in t: return "P"
        nm = str(r.get("ISU_NM", "")) + str(r.get("PROD_NM", ""))
        if "콜" in nm or " C " in nm: return "C"
        if "풋" in nm or " P " in nm: return "P"
        return None
    c_vol = sum(_num(r.get(volcol)) or 0 for r in rows if side(r) == "C")
    p_vol = sum(_num(r.get(volcol)) or 0 for r in rows if side(r) == "P")
    c_val = sum(_num(r.get(valcol)) or 0 for r in rows if side(r) == "C") if valcol else 0
    p_val = sum(_num(r.get(valcol)) or 0 for r in rows if side(r) == "P") if valcol else 0
    if c_vol <= 0:
        return None
    return {"vol": p_vol / c_vol,
            "val": (p_val / c_val) if c_val > 0 else None,
            "c_vol": c_vol, "p_vol": p_vol, "c_val": c_val, "p_val": p_val}

def get_kr_bond_yield(key, bd):
    """채권지수에서 국채 대표(10년물 우선) 금리/지수. 컬럼 키워드탐지. → (이름, 값) or None."""
    rows = _fetch("idx/bon_dd_trd", key, bd) or _fetch("bon/kts_bydd_trd", key, bd)
    if not rows:
        return None
    namecol = _pick(rows, ["IDX_NM", "ISU_NM", "지수", "종목"])
    valcol = _pick(rows, ["CLSPRC", "종가", "수익률", "YD", "PRC"])
    if not (namecol and valcol):
        return None
    pref = [r for r in rows if "국채" in str(r.get(namecol, "")) and ("10" in str(r.get(namecol, "")))]
    cand = pref or [r for r in rows if "국채" in str(r.get(namecol, ""))] or rows
    top = cand[0]
    return (str(top.get(namecol, "국채")), _num(top.get(valcol)))


def _fetch_dated(path, key, bd=None):
    """rows + 실제 사용된 날짜 반환."""
    seq = ([bd] if bd else []) + [d for d in recent_bdays(8) if d != bd]
    for d in seq:
        st, j, raw = call(path, key, d)
        rows = rows_of(j)
        if rows:
            return rows, d
    return None, None


def bdays_before(dstr, n=6):
    from datetime import datetime
    d = datetime.strptime(dstr, "%Y%m%d").date() - timedelta(days=1)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def _k200_fut_row(rows):
    cand = [r for r in rows
            if ("코스피200" in (str(r.get("PROD_NM", "")) + str(r.get("ISU_NM", ""))).replace(" ", ""))
            and ("주식" not in str(r.get("PROD_NM", "")))
            and ("정규" in str(r.get("MKT_NM", "")))]
    if not cand:
        return None
    cand.sort(key=lambda r: -(_num(r.get("ACC_OPNINT_QTY")) or 0))
    return cand[0]


def get_futures_oi_change(key, bd=None):
    """코스피200 근월물 OI 전일대비 증감: (당일OI, 전일OI, 증감) or None. 동일 ISU 기준."""
    rows, d = _fetch_dated("drv/fut_bydd_trd", key, bd)
    if not rows:
        return None
    top = _k200_fut_row(rows)
    if not top:
        return None
    oi_t = _num(top.get("ACC_OPNINT_QTY")); isu = top.get("ISU_CD")
    if oi_t is None:
        return None
    for pd in bdays_before(d, 6):
        st, j, raw = call("drv/fut_bydd_trd", key, pd)
        r2 = rows_of(j)
        if not r2:
            continue
        match = [r for r in r2 if r.get("ISU_CD") == isu]
        if match:
            oi_p = _num(match[0].get("ACC_OPNINT_QTY"))
            if oi_p is not None:
                return (oi_t, oi_p, oi_t - oi_p)
        break
    return None


def get_basis(key, bd=None):
    """베이시스 = 선물종가 − 현물(선물행 SPOT_PRC 우선). → (현물,선물,베이시스) or None."""
    fut = get_futures_k200(key, bd)
    if not fut:
        return None
    fclose, oi, spot = fut
    if spot is None:
        spot = get_kospi200_spot(key, bd)
    if spot is None or fclose is None:
        return None
    return (spot, fclose, fclose - spot)


def selftest():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    mock = {"OutBlock_1": [{"ISU_NM": "KOSPI200 F 202609", "TDD_CLSPRC": "440.10", "OPNINT_QTY": "12,345"}]}
    rows = rows_of(mock)
    chk("OutBlock_1 추출", isinstance(rows, list) and len(rows) == 1)
    chk("OI 컬럼 탐지", scan_field(rows, ["미결제", "OPNINT", "OI"])[0] == "OPNINT_QTY")
    chk("빈입력 None", rows_of({"x": 1}) is None)
    vk = [r for r in [{"IDX_NM": "코스피200 변동성지수"}] if any("변동성" in str(v) for v in r.values())]
    chk("변동성 행 필터", len(vk) == 1)
    chk("_num 콤마/퍼센트", _num("1,234.5") == 1234.5 and _num("-0.13%") == -0.13)
    chk("_pick 키워드", _pick([{"TDD_CLSPRC": "1", "OPNINT_QTY": "2"}], ["미결제", "OPNINT"]) == "OPNINT_QTY")
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try:
            main()
        except Exception:
            print("\n[치명 에러]"); traceback.print_exc()
