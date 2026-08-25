"""잡알리오(job.alio.go.kr) 크롤러 — 검증된 실제 엔드포인트 사용.

목록: GET https://job.alio.go.kr/recruit.do?keyword={kw}&pageNo={n}&pageSet=50
  table.tbl.type_03 td 순서: [checkbox, 번호, 채용제목, 기관명, 근무지, 고용형태, 등록일, 마감일, 상태]
상세: GET https://job.alio.go.kr/recruitview.do?idx={idx}
"""
from __future__ import annotations

import re
from datetime import date

import config
from crawlers.base import BaseCrawler
from models import JobPosting

LIST_URL = "https://job.alio.go.kr/recruit.do"
VIEW_URL = "https://job.alio.go.kr/recruitview.do"


class AlioCrawler(BaseCrawler):
    source = "알리오"

    def crawl(self, keywords: list[str], since: date) -> list[JobPosting]:
        out: list[JobPosting] = []
        seen: set[str] = set()
        today = since.strftime("%Y.%m.%d")

        for kw in keywords:
            for page in range(1, config.MAX_PAGES + 1):
                html = self.get(LIST_URL, params={"keyword": kw, "pageNo": page, "pageSet": 50})
                rows = self._rows(html)
                reached_old = False
                for tr in rows:
                    tds = tr.find_all("td")
                    if len(tds) < 9:
                        continue
                    reg_date = tds[6].get_text(strip=True)
                    if reg_date and reg_date < today:      # 등록일 내림차순 정렬 전제
                        reached_old = True
                        continue
                    if tds[8].get_text(strip=True) != "진행중":     # 마감 제외
                        continue
                    emp_type = tds[5].get_text(strip=True)
                    excl = getattr(config, "EXCLUDE_EMPLOYMENT", None) or ["기간제", "계약직", "임기제", "촉탁", "인턴"]
                    if any(k in emp_type for k in excl):
                        continue
                    region = tds[4].get_text(strip=True)
                    if not self.region_ok(region):          # 서울/경기만
                        continue
                    a = tds[2].find("a", href=True)
                    if not a:
                        continue
                    m = re.search(r"idx=(\d+)", str(a["href"]))
                    if not m or m.group(1) in seen:
                        continue
                    seen.add(m.group(1))
                    out.append(JobPosting(
                        source=self.source,
                        org=tds[3].get_text(strip=True),
                        title=a.get_text(strip=True),
                        url=f"{VIEW_URL}?idx={m.group(1)}",
                        deadline=self.norm_deadline(tds[7].get_text(strip=True)),
                        headcount_text="",
                        detail_text="", ref=m.group(1), region=region,
                    ))
                if reached_old or len(rows) < 10:
                    break
        return [p for p in out if self.hit_keyword(p.title, keywords)]

    def fetch_detail(self, p: JobPosting) -> str:
        html = self.get(f"{VIEW_URL}?idx={p.ref}")
        return self.soup(html).get_text("\n", strip=True)[:4000]

    def _rows(self, html: str):
        table = self.soup(html).select_one("table.tbl.type_03")
        return table.find_all("tr") if table else []
