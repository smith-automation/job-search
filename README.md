# 공공기관 채용 알리미 (recruit)

대한민국 공공기관 채용 포털을 매일 크롤링해서, 내 자격 기준 **서류 합격 확률 점수(100점)**를 매기고 Discord로 알려주는 프로그램.

- 수집 대상: 잡알리오(`job.alio.go.kr`), 클린아이 잡플러스(`job.cleaneye.go.kr`), 나라일터(`www.gojobs.go.kr`), 지자체 6곳(남양주·의정부·강동·강남·광진·노원)
- **여러 사람 지원**: 키워드·근무지·고용형태·스펙이 다른 사람을 `config.py`에 여러 명 등록 → 순서대로 실행해 `👤 [이름]` 태그로 각자 알림
- 첨부파일(pdf/hwp/hwpx) 본문까지 파싱해서 키워드 재매칭

---

## 1. 파일 구조와 역할

| 파일 | 역할 | 언제 수정하나 |
|---|---|---|
| `config.py` | **모든 사용자 설정** (키워드/지역/프로필/웹훅) | 조건 변경 시 |
| `crawlers/alio.py` | 잡알리오 수집 | 사이트 구조가 바뀌었을 때 |
| `crawlers/cleaneye.py` | 클린아이 잡플러스 수집 | 〃 |
| `crawlers/gojobs.py` | 나라일터 수집 | 〃 |
| `crawlers/localgov.py` | 지자체 6곳 수집 (지역 추가도 여기) | 지자체 추가/변경 시 |
| `crawlers/base.py` | 크롤러 공통 부모 (HTTP/파싱 유틸) | 공통 동작 변경 시 |
| `crawlers/__init__.py` | **크롤러 등록 목록** (`CRAWLERS`) | 새 사이트 추가 시 |
| `attach.py` | pdf/hwp/hwpx 첨부 텍스트 추출 | 파서 문제 시 |
| `scorer.py` | 점수 계산 + 정규직/마감 판정 | 점수 정책 변경 시 |
| `notifier.py` | Discord 전송 (메시지 포맷) | 메시지 형식 변경 시 |
| `models.py` | JobPosting 데이터클래스 + 중복제거 | — |
| `main.py` | 일일 파이프라인 (사람별 루프: 수집→필터→점수→전송) | 파이프라인 순서 변경 시 |
| `run.bat` | Windows 실행 래퍼 (UTF-8 + 로그) | Python 경로 바뀔 때 |
| `recruit_seen_<이름>.json` | 사람별 알림 이력 (재발송 차단) | 손대지 말 것 (삭제하면 그 사람 전체 재알림) |
| `recruit.log` | 실행 로그 누적 파일 | 필요 없으면 삭제해도 무방 |

---

## 2. 내 조건 바꾸기 → `config.py` 만 수정

**다른 파일은 건드릴 필요 없습니다.** 사람별 조건은 `PROFILES` 리스트의 dict 하나입니다.

```python
# config.py
PROFILES = [
    {
        "name": "나",                                   # Discord 👤[이름] 태그 + seen 파일명
        "keywords": ["전산", "IT", "정보화"],            # 추적 키워드 (제목·본문·첨부 검색용)
        "regions": ["서울", "경기"],                     # 근무지역 화이트리스트 (부분 문자열)
        # 제외할 고용형태 키워드. 빈 리스트 [] = 계약직·임기제도 전부 허용
        "exclude_employment": ["기간제", "계약직", "임기제", "촉탁", "시간선택제", "일용", "위촉", "인턴"],
        "title_exclude": [],                            # 제목 블랙리스트 (예: ["통장"])
        "profile": {                                    # 점수 계산 기준(지원자 스펙)
            "education": "4년제 학사",
            "major": "물리학과",
            "certificates": [],                         # 보유 자격증 나열: ["정보처리기사", "SQLD"]
            "target_cert": "정보처리기사",                # '취득하면 몇 점?' 시뮬레이션 대상
        },
    },
    {
        "name": "동생",
        # 공고는 '사무직'보다 '사무'/'행정직'/'일반직'으로 표기되는 경우가 대부분 (2026-08-24 26건 실측)
        "keywords": ["사무직", "사무", "행정직", "일반직"],
        "regions": ["남양주", "진접"],
        "exclude_employment": [],
        "title_exclude": ["통장"],
        "profile": {
            "education": "4년제 학사", "major": "물리학과",
            "certificates": ["컴퓨터활용능력 2급"],
            "target_cert": "정보처리기사",
        },
    },
]

DETAIL_LIMIT = 60                        # 하루에 사람당 상세 분석할 최대 건수
SINCE_DAYS = 3                           # 최근 N일 이내 게시분까지 수집
```

- **새 사람 추가** = dict 하나 복사해서 고치기. 알림 이력(`recruit_seen_<이름>.json`)도 자동 분리됩니다.
- 웹훅 주소는 코드에 없습니다 — 환경변수 `DISCORD_WEBHOOK_URL` 사용 (로컬은 `run.bat`에서 주입, GitHub Actions는 저장소 Secret).

### 점수 정책을 바꾸고 싶으면 → `scorer.py`

현재 규칙: 대졸 충족 +40 / 전공 요건 있음 +20(충족 시) / 자격증 불필요 +30·가산점 +20·필수 미보유 0점(지원불가) / 선발인원 1명+10·2~4명+20·5명↑+30. 80↑ 상 · 60~79 중 · 60↓ 하. 모든 공고에 '정보처리기사 취득 시' 점수를 병기합니다.

---

## 3. 사이트 추가하기

### A. 지자체 하나 더 추가 (가장 흔한 경우) → `crawlers/localgov.py` 의 `SITES` 에 딕셔너리 한 줄

```python
SITES = [
    {
        "org": "수원시",
        "list_url": "https://www.suwon.go.kr/.../list.do?pageIndex={page}",
        ...
    },
]
```

게시판 유형은 3가지를 지원합니다 (기존 항목들을 예제로 참고):
1. **표형**: th에 '제목'이 있는 `<table>` (남양주 방식)
2. **div/앵커형**: `view.do?nttId=...` 링크 나열 (광진 방식)
3. **JS호출형**: 행의 `onclick="js_view('123','456')"` → `js_view` 패턴 리스트에 정규식+URL템플릿 등록 (의정부/노원 방식)

새 지자체를 추가했으면 반드시 실제 페이지에서 ①리스트가 잡히는지 ②상세 URL 생성이 되는지 ③첨부 다운로드 링크(filedown/download 등 직접 링크형인지)를 확인하세요. gojobs식 JS-POST 다운로드(gfn_fileDown)는 첨부 파싱 미지원입니다.

### B. 완전히 새로운 포털 추가 (예: 사람인공공) → 크롤러 파일 1개 신규 + 등록 2곳

1. `crawlers/mysite.py` 생성 — `BaseCrawler` 상속, 최소 2개 메서드만 구현:

```python
from crawlers.base import BaseCrawler
from models import JobPosting

class MySiteCrawler(BaseCrawler):
    source = "마이사이트"          # Discord 메시지 [출처] 표기

    def crawl(self, keywords, since) -> list[JobPosting]:
        # since( date ) 이후 게시된 공고만 JobPosting 리스트로 반환
        ...

    def fetch_detail(self, p: JobPosting) -> str:
        # 상세페이지 본문 텍스트 반환 (자격요건 분석에 쓰임)
        ...

    # 선택: 첨부파일 텍스트도 보고 싶으면 오버라이드
    def fetch_attachment_text(self, p: JobPosting) -> str:
        return attach.extract_text(name, data)
```

2. `crawlers/__init__.py` 에 등록:

```python
from crawlers.mysite import MySiteCrawler
CRAWLERS = [AlioCrawler, CleanEyeCrawler, GoJobsCrawler, LocalGovCrawler, MySiteCrawler]
```

3. 검증: `python main.py` 실행 → `[마이사이트] 신규 후보 N건` 로그 확인.

`JobPosting` 필수 필드: `source, org, title, url, deadline`. 나머지(`region`, `detail_text`, 점수들)는 파이프라인이 채웁니다. `models.dedup_key()`가 기관명+제목으로 중복을 걸러주므로 사이트 간 겹침은 신경 쓸 필요 없습니다.

---

## 4. 필터 파이프라인 (변경 위치)

`main.py` 79~86행에서 순서대로 적용됩니다:

| 단계 | 조건 | 고치려면 |
|---|---|---|
| 키워드 | 제목 → 없으면 상세본문 → 없으면 **첨부파일 본문** | profile의 `keywords` |
| 신분 | `exclude_employment`에 있는 단어가 있으면 탈락 (예: 정규직만 원하면 8종 등록) | profile의 `exclude_employment` |
| 제목 블랙리스트 | 제목에 `title_exclude` 단어가 있으면 무조건 탈락 (예: 통장 모집) | profile의 `title_exclude` |
| 지역 | `regions` 중 하나라도 포함 (부분 문자열) | profile의 `regions` |
| 마감 | 마감일 지난 것 제외 | 자동 |

---

## 5. 자동 실행 등록

### 현재 운영 방식 — GitHub Actions 단일 (2026-08-26~)

로컬 작업스케줄러(`RecruitDailyAlert`)와 부팅실행(`recruit_boot.bat`)은 **제거됨**.
매일 아침 10시(KST) 알림은 GitHub Actions만 담당. 세팅 절차는 아래 "서버성 실행" 참고.

PC에서 수동으로 돌리고 싶을 때만 `run.bat` 실행 (웹훅은 이 파일 안의 환경변수로 주입).

### Windows 로컬 스케줄이 다시 필요해지면 (참고용)

```bat
schtasks /Create /TN RecruitDailyAlert /TR "E:\IdeaProjects\recruit\run.bat" /SC DAILY /ST 10:00 /F

:: 부팅 실행은 시작폴더(shell:startup)에 아래 내용의 bat 하나 두면 됨:
:: timeout /t 90 /nobreak >nul
:: call E:\IdeaProjects\recruit\run.bat
```

> 주의: Actions와 로컬을 동시에 쓰면 seen 기록이 저장소(커밋)와 로컬 파일로 갈라져 중복 알림이 날 수 있다. 한쪽만 쓸 것.

### macOS

`launchd` (권장) — `~/Library/LaunchAgents/com.recruit.daily.plist` 생성:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.recruit.daily</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>/Users/YOUR_ID/recruit/main.py</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/recruit.log</string>
  <key>StandardErrorPath</key><string>/tmp/recruit.log</string>
</dict></plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.recruit.daily.plist   # 등록
launchctl list | grep recruit                                   # 확인
```

간단한 대안 — crontab:

```bash
crontab -e
# 아래 한 줄 추가 (매일 10시)
0 10 * * * cd ~/recruit && /usr/bin/python3 main.py >> recruit.log 2>&1
```

> macOS는 잠자기 상태면 예약 실행이 밀릴 수 있습니다. 노트북이라면 GitHub Actions 방식이 확실합니다.

### 서버성 실행 — GitHub Actions (PC 끄고 다니는 경우, 현재 사용 방식)

`.github/workflows/daily.yml` 포함되어 있음 — 매일 한국시간 오전 10시(cron `0 1 * * *`) 자동 실행.

**업로드 절차:**

1. GitHub에서 **Private** 저장소 생성 (공개 저장소 금지 — 채용 조건이 노출됨)
2. 로컬에서 푸시:
   ```bash
   cd E:\IdeaProjects\recruit
   git init && git add . && git commit -m "init recruit alert"
   git remote add origin https://github.com/<계정>/<저장소>.git
   git push -u origin main
   ```
   > `.gitignore`가 `run.bat`(웹훅 포함)·`recruit.log`·`__pycache__`를 제외하므로 `git add .`로 안전합니다.
3. 저장소 Settings → Secrets and variables → Actions → New repository secret:
   | Secret 이름 | 값 |
   |---|---|
   | `DISCORD_WEBHOOK_URL` | Discord 웹훅 URL (**필수** — 없으면 전송 안 됨) |
4. Actions 탭 → "daily recruit alert" 활성화. 수동 테스트는 Run workflow 버튼(`workflow_dispatch`).

**seen 상태 영속화 방식**: 러너는 매번 초기화되므로, 실행 후 워크플로가 `recruit_seen_*.json`을 저장소에 자동 커밋해 다음 날 이어받습니다(중복 알림 방지). 이 커밋을 위해 `permissions: contents: write`가 yml에 들어있습니다. seen 파일은 삭제하지 마세요 — 삭제 시 그 사람 전체 재알림됩니다.

---

## 6. 수동 실행 / 로그 / 문제 확인

```bat
:: Windows
E:\IdeaProjects\recruit\run.bat          :: 실행 + recruit.log 누적
type E:\IdeaProjects\recruit\recruit.log :: 최근 결과 확인
```

```bash
# macOS/Linux
cd recruit && python3 main.py            # PYTHONIOENCODING=utf-8 권장
```

| 증상 | 원인/처치 |
|---|---|
| Discord에 아무것도 안 옴 | `recruit.log` 확인. '최종 알림 대상 0건'이면 조건 부합 공고가 없던 것 (하트비트 메시지는 전송됨) |
| 같은 공고가 또 옴 | `recruit_seen_<이름>.json` 삭제 여부 확인 (삭제/미커밋 시 재알림됨). GitHub Actions라면 seen 커밋 스텝 실패 여부 확인 |
| 특정 사이트만 0건 | 사이트 개편 가능성 → 해당 crawler 파일의 엔드포인트/HTML구조 점검 |
| 첨부 키워드 못 찾음 | gojobs식 JS-POST 다운로드는 미지원. 직접링크 형태인지 확인 |
| 설치 | `pip install -r requirements.txt` (requests, beautifulsoup4, pypdf, olefile) |
