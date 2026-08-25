# AGENTS.md — AI 에이전트용 프로젝트 브리핑

대한민국 공공기관 채용공고를 크롤링해 사람별 자격 기준으로 점수화(100점) 후 Discord로 알림하는 Python 프로그램. Windows 로컬 수동실행 + GitHub Actions 매일 KST 10시 자동실행.

## 파일 지도

| 파일 | 역할 |
|---|---|
| `config.py` | **모든 사용자 설정**. `PROFILES` 리스트(사람별 dict), `DISCORD_WEBHOOK_URL`(기본값 ''), 공통 상수 |
| `main.py` | 파이프라인. `run_profile(prof)`이 사람별 실행 단위, `main()`에서 PROFILES 루프 |
| `models.py` | `JobPosting` dataclass + 사이트간 중복제거(`dedup_key` = md5(정규화 기관명+제목)) |
| `scorer.py` | 점수 계산, `is_regular`, `deadline_open`, `parse_headcount`. `__main__` 셀프체크 포함 |
| `notifier.py` | Discord embed 전송(배치 10개). URL 없으면 콘솔 폴백. 빈 목록도 하트비트 전송 |
| `crawlers/base.py` | `BaseCrawler`: session/UA, `get()`, `soup()`, `hit_keyword`, `region_ok`, `norm_deadline` |
| `crawlers/alio.py` | 잡알리오 job.alio.go.kr (GET recruit.do, HTML table 파싱) |
| `crawlers/cleaneye.py` | 클린아이 잡플러스 job.cleaneye.go.kr (POST selectYpRecruitment.do → JSON) |
| `crawlers/gojobs.py` | 나라일터 www.gojobs.go.kr (GET apmList.do, fn_apmView href/onclick 양쪽 대응) |
| `crawlers/localgov.py` | 지자체 통합. `SITES` 리스트에 게시판 dict 추가로 확장 |
| `attach.py` | pdf/hwp/hwpx 첨부 텍스트 추출(pypdf, zipfile, HWP5 레코드 walk, HWP3 PrvText 폴백) |
| `run.bat` | 로컬 수동실행용. 웹훅 환경변수 주입 포함 — **gitignored, 절대 커밋 금지** |
| `.github/workflows/daily.yml` | cron '0 1 * * *'(=KST 10시) + 실행 후 `recruit_seen_*.json` 커밋·push |

## 불변식 (깨뜨리면 안 되는 설계 계약)

1. **프로필 전환 메커니즘**: `main.run_profile()`이 실행 시작에 `config.KEYWORDS`, `config.REGIONS`, `config.PROFILE`, `config.EXCLUDE_EMPLOYMENT`, `config.TITLE_EXCLUDE` 등 모듈 전역을 해당 사람 값으로 **교체**한다. scorer/notifier/crawlers는 호출 시점에 `config.*`를 읽는다(모듈 임포트 시점 고정 아님 — notifier는 `import config` 후 속성 접근 방식 유지 필수). "파라미터로 넘기게 리팩터"하려면 이 계약 전체를 같이 옮겨야 한다.
2. **seen 상태**: `recruit_seen_<이름>.json`(사람별 분리, 이름 sanitize됨). 재알림 방지용. **삭제 금지, .gitignore에 넣지 말 것** — Actions의 'save seen state' 스텝이 커밋·push로 영속화한다(로컬과 원격이 이 파일로 동기화됨).
3. **시크릿**: 웹훅 URL은 config 기본값 '' 이고, 로컬은 run.bat가 `set DISCORD_WEBHOOK_URL=...` 주입, Actions는 repository secret. 하드코딩으로 되돌리면 저장소 유출 위험.
4. **필터 순서**(main.py kept 루프): 키워드(제목→본문→첨부 순, 제목 미매칭시만 첨부 다운로드) → 제목 블랙리스트(`TITLE_EXCLUDE`) → 신분(`EXCLUDE_EMPLOYMENT` 블랙리스트, [] = 전부 허용) → 지역(`REGIONS` 부분문자열, region 없으면 본문 판정) → 마감. alio만 리스트단계 선필터(EXCLUDE_EMPLOYMENT 반영) 있음.
5. **예외 격리**: 사이트별/사람별 실패는 로그 남기고 계속. 하나가 죽어도 전체 실행은 살아있어야 한다.

## 도메인 팩트 (실측, 되돌리기 금지)

- 구주소 소멸 도메인: `jobplus.or.kr`→`job.cleaneye.go.kr`, `gojobs.or.kr`→`www.gojobs.go.kr`. 의정부=`ui4u.go.kr`, 남양주=`nyj.go.kr`, 노원=`nowon.kr`.
- 공공 공고는 '사무직'이라는 단어를 잘 안 쓴다('사무'/'행정직'/'일반직' 표기). bare '행정' 키워드는 행정복지센터 지명 오매칭이라 배제.
- gojobs식 JS-POST 첨부다운로드(gfn_fileDown)는 미지원 — 직접링크(filedown/download/attach 계열 href)만 파싱.
- HWP3(HWP 97) 본문은 암호화되어 PrvText 미리보기(~1KB)만 추출 가능.

## 검증 절차 (작업 완료 조건)

```bash
C:/Python314/python.exe -m py_compile main.py config.py models.py scorer.py notifier.py attach.py crawlers/*.py
C:/Python314/python.exe scorer.py          # 셀프체크 assert 4케이스 출력되면 OK
C:/Python314/python.exe main.py            # E2E: 실네트워크 요청 발생. 사람별 '[소유자] ...' 로그 + Discord 하트비트 확인
```

- LSP가 `import config` 등에 reportMissingImports를 내면 flat-script 구조 오탐이다(`python main.py` 직접실행 전제 설계). 수정하지 말 것.
- yml 수정 후 YAML 파싱 검증할 것.

## 환경 함정 (Windows)

- git-bash에서 `schtasks /Query` 등 슬래시 인자는 경로로 치환돼 깨진다 → `cmd //c "schtasks ..."` 전체따움표 패턴 사용.
- printf/heredoc으로 .bat 작성하면 `\r` 등 이스케이프 사고 → bat/bom 파일은 write 도구로 생성.
- 백슬래시 경로 인자(E:\...)도 git-bash가 먹는다 → cmd //c 래핑 또는 POSIX 경로(/e/IdeaProjects/...).

## 확장 방법 (요청받으면)

- **지자체 추가**: `localgov.py` SITES에 dict. 3유형 지원(표형/div앵커형/js_view호출형) — README §3A 참조.
- **새 사람 추가**: config.PROFILES에 dict 하나 복사(name/keywords/regions/exclude_employment/title_exclude/profile). seen 파일은 자동 분리.
- **새 포털 추가**: BaseCrawler 상속(crawl/fetch_detail 필수, fetch_attachment_text 선택) + crawlers/__init__.py CRAWLERS 등록.
