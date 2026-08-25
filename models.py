"""공고 데이터 모델 + 사이트 간 중복 제거."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


@dataclass
class JobPosting:
    source: str            # 출처: 알리오 / 잡플러스 / 나라일터
    org: str               # 기관명
    title: str             # 공고 제목
    url: str               # 상세 페이지 URL
    deadline: str          # 접수 마감일 (원문 텍스트)
    headcount_text: str = ""   # 선발 인원 원문 (예: "2명")
    detail_text: str = ""      # 자격요건 분석용 본문 발췌(선택)
    score: int | None = None       # 현재 프로필 점수 (0~100)
    grade: str | None = None       # 상/중/하/지원불가
    sim_score: int | None = None   # 정보처리기사 취득 가정 점수
    sim_grade: str | None = None   # 시나리오 등급
    ref: str = ""                  # 사이트별 상세조회 키
    region: str = ""               # 근무지역 (판별 가능 시)
    advice: str | None = None      # 추천 전략 한 줄
    cert_req: str = ""             # 공고가 요구하는 필수 자격증 문구(추출 성공 시)

    # ── 중복 제거 키: 정규화된 (기관명 + 공고제목) ──
    def dedup_key(self) -> str:
        def norm(s: str) -> str:
            s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)     # 괄호 안 내용 제거
            s = re.sub(r"[^\w가-힣]", "", s)            # 특수문자 제거
            return s.lower()

        raw = f"{norm(self.org)}::{norm(self.title)}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


def deduplicate(postings: list[JobPosting]) -> list[JobPosting]:
    """출처가 달라도 기관명+제목이 같으면 첫 번째 것만 유지."""
    seen: set[str] = set()
    unique: list[JobPosting] = []
    for p in sorted(postings, key=lambda x: x.source):  # 알리오 우선 정렬 안정화
        k = p.dedup_key()
        if k not in seen:
            seen.add(k)
            unique.append(p)
    return unique
