"""공통 크롤러 베이스."""
from __future__ import annotations

import warnings

import requests
import urllib3
from bs4 import BeautifulSoup

import config
from models import JobPosting

warnings.filterwarnings("ignore")
urllib3.disable_warnings()


class BaseCrawler:
    """사이트별 크롤러 공통 부모. crawl() / fetch_detail() 만 구현하면 됨."""

    source: str = ""

    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9",
        })

    def crawl(self, keywords: list[str], since) -> list[JobPosting]:
        """since( date ) 이후 게시된 키워드 매칭 공고 수집."""
        raise NotImplementedError

    def fetch_detail(self, p: JobPosting) -> str:
        """상세 페이지 본문 텍스트 반환(자격요건 분석용)."""
        raise NotImplementedError

    def fetch_attachment_text(self, p: JobPosting) -> str:
        """첨부파일 본문 텍스트. 기본 미지원, 필요한 크롤러만 오버라이드."""
        return ""

    # ── 공용 유틸 ──
    def get(self, url: str, **kw) -> str:
        kw.setdefault("timeout", config.HTTP_TIMEOUT)
        kw.setdefault("verify", False)
        return self.s.get(url, **kw).text

    @staticmethod
    def soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def hit_keyword(title: str, keywords: list[str]) -> bool:
        t = title.lower()
        return any(k.lower() in t for k in keywords)

    @staticmethod
    def region_ok(text: str) -> bool:
        """config.REGIONS(서울/경기) 중 하나라도 포함되면 통과."""
        return any(r in (text or "") for r in config.REGIONS)

    @staticmethod
    def norm_deadline(raw: str) -> str:
        """'26.09.08D-14' → '2026-09-08' (표시용 정규화, 실패 시 원문)."""
        import re
        m = re.match(r"(\d{2})\.(\d{1,2})\.(\d{1,2})", (raw or "").strip())
        if m:
            yy, mm, dd = m.groups()
            return f"20{yy}-{int(mm):02d}-{int(dd):02d}"
        return (raw or "").strip()
