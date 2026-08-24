#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""data_snapshot.py — 핵심 데이터 패널 스냅샷·버전링·롤백 (데이터 인프라 안전판)

문제: 수집(pykrx 증분)이 데이터를 '덮어쓴' 뒤 깨진 걸 발견하면 되돌릴 수가 없다.
해결: 수집 직전에 핵심 패널을 _백업/<타임스탬프>/ 로 복사해 둔다. 최근 N개만 보관.
      깨졌을 때 rollback 으로 마지막 정상 스냅샷으로 복원.

대상(있는 것만): _월봉종가캐시_KOSPI/KOSDAQ.csv · 종목시총_30년.csv ·
                 종목재무_KRX_KOSPI/KOSDAQ.csv · 종목일봉_30년.csv · my_holdings.csv
사용:
  py data_snapshot.py                 # 스냅샷 생성(직전과 동일하면 스킵)
  py data_snapshot.py --list          # 스냅샷 목록
  py data_snapshot.py --rollback      # 가장 최근 스냅샷으로 복원(현재본은 _되돌리기전 로 백업)
  py data_snapshot.py --rollback 2026-07-26_0530
  py data_snapshot.py --keep 8        # 보관 개수 지정(기본 5)
⚠️ 정보·검증용·투자자문 아님·책임 본인.
"""

# ── 경로 자립화 (2026-07-27) — 샌드박스 하드코딩 제거 ──────────────
import os as _os, glob as _glob
_JQ_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _jqroot():
    d = _JQ_HERE
    for _ in range(5):
        if _os.path.exists(_os.path.join(d, "종목시총_30년.csv")):
            return d
        d = _os.path.dirname(d)
    return _os.path.dirname(_JQ_HERE)


BASE = _os.environ.get("JQ_BASE", _jqroot())


def _jqfind(name):
    """이름으로 파일 자동탐색 (백업/보관 폴더 제외)."""
    for b in (BASE, _JQ_HERE, _os.getcwd()):
        hits = [h for h in _glob.glob(_os.path.join(b, "**", name), recursive=True)
                if not any(s in h for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if hits:
            return sorted(hits, key=len)[0]
    raise FileNotFoundError(f"{name} 를 못 찾음 (루트={BASE})")
# ────────────────────────────────────────────────────────────────

import os, sys, json, shutil, datetime, argparse
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# 데이터 루트 후보(진우퀀트 폴더). 강화키트의 부모가 보통 루트.
ROOTS=[PARENT, HERE, os.getcwd()]
TARGETS=["_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv","종목시총_30년.csv",
         "종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv","종목일봉_30년.csv","my_holdings.csv"]

def data_root(override=None):
    if override: return os.path.abspath(override)
    # 대상 파일이 가장 많이 있는 폴더를 데이터 루트로 본다.
    best,bestn=PARENT,-1
    for d in ROOTS:
        if not os.path.isdir(d): continue
        n=sum(1 for t in TARGETS if os.path.exists(os.path.join(d,t)))
        if n>bestn: best,bestn=d,n
    return best

def backup_dir(root):
    p=os.path.join(root,"_백업"); os.makedirs(p,exist_ok=True); return p

def _sig(path):
    st=os.stat(path); return (st.st_size, int(st.st_mtime))

def _manifest_of_dir(d):
    m={}
    for t in TARGETS:
        p=os.path.join(d,t)
        if os.path.exists(p): m[t]=_sig(p)
    return m

def list_snaps(root):
    bd=backup_dir(root)
    return sorted([n for n in os.listdir(bd) if os.path.isdir(os.path.join(bd,n)) and not n.startswith("_")])

def latest_manifest(root):
    snaps=list_snaps(root)
    if not snaps: return None
    mf=os.path.join(backup_dir(root),snaps[-1],"manifest.json")
    if os.path.exists(mf):
        try: return {k:tuple(v) for k,v in json.load(open(mf,encoding="utf-8")).get("files",{}).items()}
        except Exception: return None
    return None

def snapshot(root, keep=5):
    cur={t:_sig(os.path.join(root,t)) for t in TARGETS if os.path.exists(os.path.join(root,t))}
    if not cur:
        print("스냅샷 대상 파일이 없음 — 데이터 루트 확인:",root); return None
    # 직전 스냅샷과 완전히 동일하면 스킵(중복 방지)
    prev=latest_manifest(root)
    if prev is not None and prev=={k:tuple(v) for k,v in cur.items()}:
        print("직전 스냅샷과 동일 — 스킵"); return None
    stamp=datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dst=os.path.join(backup_dir(root),stamp); os.makedirs(dst,exist_ok=True)
    total=0
    for t in cur:
        shutil.copy2(os.path.join(root,t), os.path.join(dst,t)); total+=cur[t][0]
    json.dump({"stamp":stamp,"ts":datetime.datetime.now().isoformat(timespec="seconds"),
               "files":{k:list(v) for k,v in cur.items()}},
              open(os.path.join(dst,"manifest.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print(f"스냅샷 생성: _백업/{stamp}  ({len(cur)}개 · {total/1e6:.1f}MB)")
    # 오래된 것 정리
    snaps=list_snaps(root)
    for old in snaps[:-keep]:
        shutil.rmtree(os.path.join(backup_dir(root),old),ignore_errors=True)
        print(f"  오래된 스냅샷 삭제: {old}")
    return stamp

def rollback(root, stamp=None):
    snaps=list_snaps(root)
    if not snaps: print("복원할 스냅샷이 없음"); return False
    stamp=stamp or snaps[-1]
    src=os.path.join(backup_dir(root),stamp)
    if not os.path.isdir(src): print("해당 스냅샷 없음:",stamp); return False
    # 현재본을 먼저 안전 백업
    safe=os.path.join(backup_dir(root),"_되돌리기전_"+datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    os.makedirs(safe,exist_ok=True)
    restored=0
    for t in TARGETS:
        s=os.path.join(src,t)
        if not os.path.exists(s): continue
        cur=os.path.join(root,t)
        if os.path.exists(cur): shutil.copy2(cur,os.path.join(safe,t))
        shutil.copy2(s,cur); restored+=1
    print(f"복원 완료: _백업/{stamp} → 데이터 루트 ({restored}개 파일)")
    print(f"  (복원 전 현재본은 {os.path.basename(safe)} 에 백업됨)")
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--list",action="store_true"); ap.add_argument("--rollback",nargs="?",const="__latest__")
    ap.add_argument("--keep",type=int,default=5); ap.add_argument("--root")
    a=ap.parse_args()
    root=data_root(a.root); print("데이터 루트:",root)
    if a.list:
        snaps=list_snaps(root)
        print("스냅샷 목록:", "(없음)" if not snaps else "")
        for s in snaps:
            mf=os.path.join(backup_dir(root),s,"manifest.json")
            n=len(json.load(open(mf,encoding="utf-8")).get("files",{})) if os.path.exists(mf) else "?"
            print(f"  {s}  ({n}개 파일)")
        return
    if a.rollback:
        rollback(root, None if a.rollback=="__latest__" else a.rollback); return
    snapshot(root, keep=a.keep)

if __name__=="__main__": main()
