# -*- coding: utf-8 -*-
r"""krx_주식탐색.py — KRX 공식 Open API 의 '주식(sto)' 서비스에 재무가 있는지 탐색. (2026-08-20)

배경
----
2026-08-20 pykrx(스크래핑)로 KRX KDM 이 IP 1일 차단. 안내문이 직접 권고한 정식 경로가
**KRX Open API(openapi.krx.co.kr)** 이고, 우리는 이미 인증키(krx_authkey.txt)를 갖고 있다.
2026-06-23 탐색에서 지수(idx)·파생(drv)은 확인됐으나 **주식(sto)은 시험한 적이 없다.**
`fetch_fundamental_panel.py` 가 필요로 하는 PER·PBR·EPS·DIV·DPS 가 여기 있는지가 관건.

⚠️ 호출 상한
-----------
차단 직후이므로 **최대 12회**만 부른다(엔드포인트당 1회, 1초 간격).
차단 징후(401/403/HTML)가 보이면 즉시 중단한다. 절대 반복 실행하지 말 것.

    py krx_주식탐색.py
"""
import os, sys, time, json, importlib.util

BASE = os.path.dirname(os.path.abspath(__file__))
MAX_CALLS = 12
SLEEP = 1.0

# 재무로 볼 수 있는 컬럼 후보 (KRX 영문 약칭)
FIN_KEYS = ["PER", "PBR", "EPS", "BPS", "DVD_YLD", "DPS", "DIV"]

# 주식(sto) 서비스 후보 — 되는 것만 골라 쓴다
CANDIDATES = [
    ("sto/stk_bydd_trd",      "유가증권 일별매매정보"),
    ("sto/ksq_bydd_trd",      "코스닥 일별매매정보"),
    ("sto/knx_bydd_trd",      "코넥스 일별매매정보"),
    ("sto/stk_isu_base_info", "유가증권 종목기본정보"),
    ("sto/ksq_isu_base_info", "코스닥 종목기본정보"),
]


def load_krx_openapi():
    """기존 krx_openapi.py 의 인증·호출 함수를 그대로 재사용한다."""
    p = os.path.join(BASE, "krx_openapi.py")
    if not os.path.exists(p):
        sys.exit("krx_openapi.py 를 못 찾음 — 진우퀀트 폴더에서 실행하세요.")
    spec = importlib.util.spec_from_file_location("krxapi", p)
    m = importlib.util.module_from_spec(spec)
    sys.argv = [sys.argv[0]]          # 원본 main() 인자 오염 방지
    spec.loader.exec_module(m)
    return m


def main():
    K = load_krx_openapi()
    key = K.auth_key()
    if not key:
        print("❌ 인증키 없음 — krx_authkey.txt(한 줄) 또는 KRX_AUTH_KEY")
        return 1
    print("=" * 62)
    print(" KRX Open API — 주식(sto) 서비스 탐색")
    print("=" * 62)
    print("  인증키: 로드됨(길이 %d, 값 미표시)" % len(key))
    try:
        bd = K.nearest_bday()
    except Exception:
        bd = None
    if not bd:
        print("  기준일 확인 실패 — 중단")
        return 1
    print("  기준일: %s · 호출 상한 %d회" % (bd, MAX_CALLS))

    calls = 0
    out = []
    found_fin = []
    for path, label in CANDIDATES:
        if calls >= MAX_CALLS:
            print("\n  [상한 도달] 더 부르지 않는다.")
            break
        print("\n[%s]  %s" % (label, path))
        try:
            j = K.call(path, key, bd)
            calls += 1
        except Exception as e:
            print("  ⛔ 호출 예외: %s" % str(e)[:90])
            break
        time.sleep(SLEEP)

        if j is None:
            print("  ❌ 응답 없음/실패 (미신청 또는 권한 없음일 수 있음)")
            out.append((label, path, "실패", [], 0))
            continue
        if isinstance(j, str) and "<" in j[:200]:
            print("  ⛔ HTML 응답 — 차단/점검 의심. 즉시 중단한다.")
            break
        try:
            rows = K.rows_of(j)
        except Exception:
            rows = []
        if not rows:
            print("  ❌ 빈 배열 — 미신청 서비스일 가능성 (마이페이지에서 이용신청)")
            out.append((label, path, "빈배열", [], 0))
            continue

        cols = list(rows[0].keys())
        fin = [c for c in cols if any(k in c.upper() for k in FIN_KEYS)]
        print("  ✅ rows=%d" % len(rows))
        print("  컬럼(%d): %s" % (len(cols), cols))
        if fin:
            print("  ★ 재무성 컬럼 발견: %s" % fin)
            print("  샘플: %s" % json.dumps({k: rows[0].get(k) for k in (["ISU_CD", "ISU_NM"] + fin)
                                             if k in rows[0]}, ensure_ascii=False)[:200])
            found_fin.append((label, path, fin))
        else:
            print("  (재무 컬럼 없음 — 시세·기본정보만)")
        out.append((label, path, "성공", cols, len(rows)))

    print("\n" + "=" * 62)
    print(" 결론")
    print("=" * 62)
    print("  호출 %d회 사용" % calls)
    if found_fin:
        print("  ✅ 재무를 주는 서비스:")
        for lab, path, fin in found_fin:
            print("     %-24s %s → %s" % (path, lab, fin))
        print("\n  → 이걸로 fetch_fundamental_panel.py 의 pykrx 를 대체할 수 있다.")
    else:
        print("  ❌ 주식 서비스에서 재무 컬럼을 못 찾았다.")
        print("     선택지: (a) 마이페이지에서 해당 서비스 이용신청 후 재탐색")
        print("             (b) 재무는 DART 로, 시세는 Open API 로 분리")
        print("             (c) 수정된 pykrx(1회 3콜)를 저빈도로만 사용")

    fn = os.path.join(BASE, "krx_주식탐색_결과.txt")
    with open(fn, "w", encoding="utf-8") as f:
        f.write("KRX Open API 주식(sto) 탐색 — 기준일 %s\n" % bd)
        f.write("인증키: 로드됨(길이 %d, 값 미표시)\n\n" % len(key))
        for lab, path, st, cols, n in out:
            f.write("[%s] %s → %s · rows=%d\n" % (lab, path, st, n))
            if cols:
                f.write("  컬럼: %s\n" % cols)
        f.write("\n재무 발견: %s\n" % (found_fin or "없음"))
    print("\n  → %s" % os.path.basename(fn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
