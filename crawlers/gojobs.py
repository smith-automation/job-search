"""나라일터(gojobs.go.kr) 크롤러 — 검증된 실제 엔드포인트 사용.

목록: GET https://www.gojobs.go.kr/apmList.do?menuNo=401&...&searchKeyword={kw}&pageIndex={n}
  표: [번호, 공고명(a onclick=fn_apmView('코드','일련번호')), 기관명, 공고게시일, 접수마감일, 조회]
상세: GET /apmView.do?...&searchEmpmnsecode={코드}&empmnsn={일련번호}  (근무지역 th/td 존재)
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlencode

import config
from crawlers.base import BaseCrawler
from models import JobPosting

LIST_URL = "https://www.gojobs.go.kr/apmList.do"
VIEW_URL = "https://www.gojobs.go.kr/apmView.do"
BASE_PARAMS = {"menuNo": "401", "mngrMenuYn": "N", "selMenuNo": "400", "upperMenuNo": ""}
_ONCLICK_RE = re.compile(r"fn_apmView\('(\w+)',\s*'(\d+)'\)")


class GoJobsCrawler(BaseCrawler):
    source = "나라일터"

    def crawl(self, keywords: list[str], since: date) -> list[JobPosting]:
        out: list[JobPosting] = []
        seen: set[str] = set()
        today_iso = date.today().isoformat()

        for kw in keywords:
            for page in range(1, config.MAX_PAGES + 1):
                params = {**BASE_PARAMS, "searchKeyword": kw, "pageIndex": str(page)}
                html = self.get(LIST_URL, params=params)
                reached_old = False
                for tr in self._rows(html):
                    tds = tr.find_all("td")
                    if len(tds) < 6:
                        continue
                    posted = tds[3].get_text(strip=True)
                    if posted and posted < since.isoformat():   # 게시일 내림차순 전제
                        reached_old = True
                        continue
                    dl = tds[4].get_text(strip=True)
                    if dl and dl < today_iso:                   # 마감 제외
                        continue
                    m = _ONCLICK_RE.search(str(tds[1]))
                    if not m:
                        continue
                    key = f"{m.group(1)}-{m.group(2)}"
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(JobPosting(
                        source=self.source,
                        org=tds[2].get_text(strip=True),
                        title=tds[1].get_text(strip=True),
                        url=f"{VIEW_URL}?{urlencode({**BASE_PARAMS, 'searchEmpmnsecode': m.group(1), 'empmnsn': m.group(2)})}",
                        deadline=dl or "미공개",
                        headcount_text="", detail_text="", ref=key,
                    ))
                if reached_old:
                    break
        return [p for p in out if self.hit_keyword(p.title, keywords)]

    def fetch_detail(self, p: JobPosting) -> str:
        ecode, sn = p.ref.split("-")
        html = self.get(VIEW_URL, params={**BASE_PARAMS,
                                          "searchEmpmnsecode": ecode, "empmnsn": sn})
        soup = self.soup(html)
        # 근무지역 th 옆 td 값을 region 으로 확정
        for th in soup.find_all("th"):
            if th.get_text(strip=True).startswith("근무지역"):
                td = th.find_next("td")
                if td:
                    p.region = td.get_text(strip=True)
                break
        return soup.get_text("\n", strip=True)[:4000]

    def _rows(self, html: str):
        for t in self.soup(html).find_all("table"):
            first_th = t.find("th")
            if first_th and first_th.get_text(strip=True) == "번호":
                return t.find_all("tr")[1:]
        return []
