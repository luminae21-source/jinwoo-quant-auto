# 진우퀀트 — API 키 설정 가이드 (1회만, 비개발자용)

> 엔진들이 실데이터를 받으려면 키가 필요. 대부분 **이미 있고**, 뉴스 엔진만 무료 키 1개 추가하면 됨.

## 1. 이미 있는 것 (할 일 없음)
- **DART**(공시) = `.dart_key` 있음 → `kosdaq_catalyst_scan_v1.py` 바로 됨.
- **pykrx·FDR**(가격·수급·美) = 설치됨 → 리드래그·촉매수급 바로 됨.

## 2. 추가할 것 — Naver 검색 API (무료, 뉴스 엔진용)
1. `developers.naver.com` 접속 → 네이버 로그인
2. **Application → 애플리케이션 등록**: 이름 아무거나, 사용 API에 **"검색"** 체크
3. 등록되면 **Client ID** · **Client Secret** 복사
4. `Desktop\진우퀀트`에 **`naver_api.json`** 파일 만들고 아래처럼 저장:
   ```
   {"id": "여기에_ClientID", "secret": "여기에_ClientSecret"}
   ```
5. `python kosdaq_news_scan_v1.py` 실행 → 종목별 뉴스 촉매가 뜸.

## 3. 선택(나중)
- **금통위 8·10·11월 정확일**: 한국은행 일정표 보고 `theme_calendar_fixed.csv`에 한 줄씩 추가(형식: `날짜,이벤트,테마,메모`). 7월(7/16)·FOMC는 이미 입력됨.
- **美 CPI 정확일**: 현재 매월 ~12일 근사(BLS 일정으로 정밀화 가능, 급하지 않음).

> 키는 전부 로컬 파일에만 저장. production·C·D·영역3·v41 무수정.
