"""실행 설정 - 환경변수가 우선, 없으면 아래 기본값 사용."""
import os

# 웹훅 주소는 코드에 넣지 않는다(깃허브 유출 방지).
#  - GitHub Actions: 저장소 Secret 'DISCORD_WEBHOOK_URL' 에서 자동 주입
#  - 로컬: run.bat 의 set DISCORD_WEBHOOK_URL=... 사용
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# ── 사람별 조건 ──
# 새 사람 추가 = 이 리스트에 dict 하나 복사해서 고치기. 각 사람은 순서대로 한 번씩 실행된다.
PROFILES = [
    {
        "name": "나",
        "keywords": ["전산", "IT", "정보화"],          # 추적 키워드 (제목·본문·첨부 검색용)
        "regions": ["서울", "경기"],                    # 근무지역 화이트리스트(부분 문자열)
        # 제외할 고용형태 키워드(제목·본문에 있으면 탈락). [] = 전부 허용
        "exclude_employment": ["기간제", "계약직", "임기제", "촉탁", "시간선택제", "일용", "위촉", "인턴"],
        # 제목 블랙리스트 — 제목에 이 단어가 있으면 무조건 알림 제외
        "title_exclude": [],
        "profile": {                                   # 점수 계산 기준(지원자 스펙)
            "education": "4년제 학사",
            "major": "물리학과",
            "it_major": False,
            # 환경변수로 덮어쓰려면 예: PROFILE_CERTS="정보처리기사,SQLD"
            "certificates": [c.strip() for c in os.environ.get("PROFILE_CERTS", "").split(",") if c.strip()],
            "target_cert": "정보처리기사",
        },
    },
    {
        "name": "동생",
        # 공고는 '사무직'보다 '사무'/'행정직'/'일반직'으로 표기되는 경우가 대부분 (2026-08-24 26건 실측)
        "keywords": ["사무직", "사무", "행정직", "일반직"],
        "regions": ["남양주", "진접"],
        "exclude_employment": [],                      # 계약직·임기제도 받음
        "title_exclude": ["통장"],
        "profile": {
            "education": "4년제 학사",
            "major": "물리학과",
            "it_major": False,
            # PROFILE_CERTS2 = 동생 전용 환경변수(같은 PC에서 두 프로필 충돌 방지)
            "certificates": [c.strip() for c in os.environ.get("PROFILE_CERTS2", "컴퓨터활용능력 2급").split(",") if c.strip()],
            "target_cert": "정보처리기사",
        },
    },
]

# ── 공통 실행 설정 ──

# 상세 페이지 분석 최대 건수 (요청 폭주 방지) — 사람별 적용
DETAIL_LIMIT = 60

# 각 사이트별 최근 N페이지까지 확인
MAX_PAGES = 3

# 최근 N일 이내 게시 공고까지 수집 (주말 사이 신규분 누락 방지)
SINCE_DAYS = 3

HTTP_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
