"""클린아이 잡플러스(job.cleaneye.go.kr) 크롤러 — 검증된 실제 엔드포인트 사용.

목록: POST https://job.cleaneye.go.kr/user/selectYpRecruitment.do  → JSON
  row: {empyear, ypEntId, entSeq, entName, entTitle, pubDate(게시일), pubEndDate(마감), ...}
상세: GET https://job.cleaneye.go.kr/user/ypCareersData.do?empyear&ypEntId&entSeq
  (지역·고용형태 정보가 목록에 없어 상세 본문에서 판정)
"""
from __future__ import annotations

import json
from datetime import date, datetime

import config
from crawlers.base import BaseCrawler
from models import JobPosting

POST_URL = "https://job.cleaneye.go.kr/user/selectYpRecruitment.do"
VIEW_URL = "https://job.cleaneye.go.kr/user/ypCareersData.do"


class CleanEyeCrawler(BaseCrawler):
    source = "잡플러스"

    def crawl(self, keywords: list[str], since: date) -> list[JobPosting]:
        out: list[JobPosting] = []
        today = date.today().isoformat()

        for page in range(1, config.MAX_PAGES + 1):
            r = self.s.post(
                POST_URL,
                data={"pageIndex": str(page), "status": "", "pubDate": "",
                      "pubEndDate": "", "entName": ""},
                timeout=config.HTTP_TIMEOUT, verify=False,
                headers={"X-Requested-With": "XMLHttpRequest",
                         "Referer": "https://job.cleaneye.go.kr/user/ypRecruitment.do"},
            )
            rows = (r.json() or {}).get("list", []) or []
            if not rows:
                break

            oldest = None
            for w in rows:
                pd = w.get("pubDate") or ""           # 게시(접수시작)일 YYYY-MM-DD
                oldest = min(filter(None, [oldest, pd])) if oldest or pd else oldest
                if not pd or pd < since.isoformat():   # 오늘 이전 게시 제외
                    continue
                pe = w.get("pubEndDate") or ""
                if pe and pe < today:                  # 이미 마감된 공고 제외
                    continue
                title = (w.get("entTitle") or "").strip()
                if not self.hit_keyword(title, keywords):
                    continue
                ref = json.dumps([w.get("empyear"), w.get("ypEntId"), w.get("entSeq")])
                out.append(JobPosting(
                    source=self.source,
                    org=(w.get("entName") or "").strip(),
                    title=title,
                    url=(f"{VIEW_URL}?empyear={w.get('empyear')}"
                         f"&ypEntId={w.get('ypEntId')}&entSeq={w.get('entSeq')}"),
                    deadline=pe or "미공개",
                    headcount_text="", detail_text="", ref=ref,
                ))
            # 페이지 전체가 어제 이전이면 더 볼 필요 없음 (최신순 정렬 전제)
            try:
                if oldest and datetime.strptime(oldest, "%Y-%m-%d").date() < since:
                    break
            except ValueError:
                pass
        return out

    def fetch_detail(self, p: JobPosting) -> str:
        empyear, yp_ent_id, ent_seq = json.loads(p.ref)
        html = self.get(VIEW_URL, params={"empyear": empyear, "ypEntId": yp_ent_id,
                                          "entSeq": ent_seq})
        return self.soup(html).get_text("\n", strip=True)[:4000]
