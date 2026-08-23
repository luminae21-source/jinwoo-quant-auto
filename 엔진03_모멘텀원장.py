# -*- coding: utf-8 -*-
"""엔진 03 모멘텀 유니버스 — forward 원장 (2026-08-23 개설)
문제: `유니버스_규칙화_실행.py --now`는 유니버스_규칙화_현재.csv를 **덮어쓴다** →
     매달 돌려도 이력이 남지 않아 forward 검증이 불가능했다(7/31 이후 3주 공백도 못 잡음).
처방: 실행 결과를 append-only 원장에 1행씩 누적. 같은 달 중복은 자동 SKIP.

규칙(기존 동결): 시총 pool100 중 12-1 모멘텀 상위 30, 동일가중, KOSPI<MA200이면 현금 50%.

  py 엔진03_모멘텀원장.py --self-test
  py 엔진03_모멘텀원장.py            # 강화키트/유니버스_규칙화_현재.csv → 원장 1행
  py 엔진03_모멘텀원장.py --run      # 실행기까지 돌린 뒤 기록
"""
import argparse, csv, os, subprocess, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "강화키트")
CUR = os.path.join(KIT, "유니버스_규칙화_현재.csv")
RUNNER = os.path.join(KIT, "유니버스_규칙화_실행.py")
LEDGER = os.path.join(HERE, "엔진03_모멘텀_원장.csv")
COLS = ["ym", "n", "defense", "scalar_s", "top5", "picks", "mom_median", "note"]


def summarize(df: pd.DataFrame):
    df = df.copy()
    df["code"] = df["code"].astype(str).str.zfill(6)
    ym = str(df["ym"].iloc[0])
    top5 = ";".join(df.sort_values("rank").head(5)["name"].astype(str).tolist())
    return {"ym": ym, "n": len(df),
            "defense": str(df["defense"].iloc[0]),
            "scalar_s": float(df["scalar_s"].iloc[0]),
            "top5": top5,
            "picks": ";".join(df.sort_values("rank")["code"].tolist()),
            "mom_median": round(float(pd.to_numeric(df["mom_12_1"], errors="coerce").median()), 1),
            "note": ""}


def self_test():
    df = pd.DataFrame({"rank": [1, 2, 3], "code": ["402340", "5930", "660"],
                       "name": ["SK스퀘어", "삼성전자", "하이닉스"], "mcap_rank": [4, 1, 2],
                       "mom_12_1": [827.3, 100.0, 50.0], "ym": ["2026-08"] * 3,
                       "defense": ["50현금"] * 3, "scalar_s": [1.0] * 3,
                       "ew_weight_pct": [3.33] * 3})
    r = summarize(df)
    assert r["ym"] == "2026-08" and r["n"] == 3
    assert r["picks"].split(";")[1] == "005930", r["picks"]      # zfill 보정
    assert r["top5"].startswith("SK스퀘어") and r["mom_median"] == 100.0
    assert set(COLS) == set(r.keys())
    print("self-test 4/4 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--run", action="store_true", help="실행기부터 돌린다")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    if a.run:
        if not os.path.exists(RUNNER):
            sys.exit("[중단] 유니버스_규칙화_실행.py 없음")
        print("[실행] 유니버스_규칙화_실행.py --now ...", flush=True)
        p = subprocess.run([sys.executable, RUNNER, "--now"], cwd=KIT,
                           capture_output=True, text=True)
        print((p.stdout or "")[-400:])
        if p.returncode != 0:
            sys.exit(f"[중단] 실행기 실패\n{(p.stderr or '')[-400:]}")

    if not os.path.exists(CUR):
        sys.exit("[중단] 유니버스_규칙화_현재.csv 없음 — --run 으로 먼저 생성")
    df = pd.read_csv(CUR, encoding="utf-8-sig")
    row = summarize(df)

    if os.path.exists(LEDGER):
        old = pd.read_csv(LEDGER, dtype=str)
        if row["ym"] in set(old["ym"]) and not a.force:
            print(f"[SKIP] {row['ym']} 이미 기록됨 (재기록은 --force)")
            return
        prev = old.iloc[-1]["picks"].split(";") if len(old) else []
        if prev:
            keep = len(set(prev) & set(row["picks"].split(";")))
            row["note"] = f"직전월 대비 유지 {keep}/{row['n']}종 · 교체 {row['n']-keep}종"
    else:
        row["note"] = "원장 개설 — 이전 기록은 실행기가 덮어써 소실됨(이력 없음)"

    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"기록: {os.path.basename(LEDGER)} — {row['ym']} · {row['n']}종 · 방어 {row['defense']}")
    print(f"  상위5: {row['top5']}")
    if row["note"]:
        print(f"  {row['note']}")


if __name__ == "__main__":
    main()
