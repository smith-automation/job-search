"""지자체 6곳 채용게시판 크롤러 (남양주/의정부/강동/강남/광진/노원).

리스트 단계에서는 키워드 필터를 하지 않고(제목에 직무가 안 나오는 공고 보호),
상세 본문+첨부파일명까지 main.py 에서 키워드 매칭한다.
js_view: 목록 앵커가 javascript 함수형인 사이트용 상세 URL 빌더.

ponytail: HWP/PDF 첨부 본문은 파싱하지 않는다(첨부 '파일명'만 매칭 대상).
본문까지 필요해지면 그때 pdfminer/olefile 도입.
"""
from __future__ import annotations

import re
import sys
from datetime import date

import requests.compat

import attach
import config
from crawlers.base import BaseCrawler
from models import JobPosting
from scorer import is_regular

MAX_ATTACHMENTS = 3
MAX_ATTACH_BYTES = 10 * 1024 * 1024
ATTACH_LINK_RE = re.compile(r"(?i)(filedown|download|attach|atchmnfl|atchfileid)")
FILE_EXT_RE = re.compile(r"\.(pdf|hwp|hwpx)\b", re.I)

SITES = [
    {"name": "남양주시청", "region": "경기 남양주시",
     "urls": ["https://www.nyj.go.kr/www/selectBbsNttList.do?key=2497&bbsNo=67&pageUnit=10&searchCnd=all&pageIndex={page}"]},
    {"name": "의정부시청", "region": "경기 의정부시",
     "urls": ["https://www.ui4u.go.kr/portal/contents.do?mId=0301110000&page={page}",    # 채용공고(공무직 등)
              "https://www.ui4u.go.kr/portal/contents.do?mId=0301120000&page={page}"],   # 임용시험 공고(공무원)
     "js_view": [
         (r"boardView\('\d+',\s*'(?P<id>\d+)'\)",
          "https://www.ui4u.go.kr/portal/saeol/gosiView.do?notAncmtMgtNo={id}&mId={mid}"),
         (r"boardView\('portal',\s*'listForm',\s*'\w+',\s*'\w',\s*'(?P<id>\d+)',\s*'(?P<pt>\d+)',\s*'(?P<mid>\d+)'",
          "https://www.ui4u.go.kr/portal/bbs/view.do?mId={mid}&bIdx={id}&ptIdx={pt}"),
     ]},
    {"name": "강동구청", "region": "서울 강동구",
     "urls": ["https://www.gangdong.go.kr/web/newportal/notice/02?cp={page}&pageSize=10"]},
    {"name": "강남구청", "region": "서울 강남구",
     "urls": ["https://www.gangnam.go.kr/notice/list.do?mid=ID05_040202&pgno={page}&gubunfield=05"]},  # 05=채용공고만
    {"name": "광진구청", "region": "서울 광진구",
     "urls": ["https://www.gwangjin.go.kr/portal/bbs/B0000004/list.do?menuNo=200193&pSiteId=portal&pageIndex={page}"]},
    {"name": "노원구청", "region": "서울 노원구",
     "urls": ["https://www.nowon.kr/www/user/bbs/BD_selectBbsList.do?q_bbsCode=1003&q_estnColumn7=Y&q_currPage={page}"],
     "js_view": [
         (r"opView\('(?P<id>\d+)'\)",
          "https://www.nowon.kr/www/user/bbs/BD_selectBbs.do?q_bbsCode=1003&q_bbscttSn={id}&q_estnColumn7=Y"),
     ]},
]

MAX_PAGES_PER_BOARD = 2
DATE_RE = re.compile(r"\d{4}[-.]\d{2}[-.]\d{2}")
# 결과발표성 게시물은 리스트 단계에서 바로 탈락(요청 절약)
NOISE_RE = re.compile(r"합격자|발표|면접|서류전형|입후보자|결정 및")


def _iso(d: str) -> str:
    return d.replace(".", "-")


class LocalGovCrawler(BaseCrawler):
    source = "지자체"

    def crawl(self, keywords: list[str], since: date) -> list[JobPosting]:
        out: list[JobPosting] = []
        seen: set[str] = set()
        for site in SITES:
            try:
                got = self._crawl_site(site, since)
            except Exception as e:
                print(f"[지자체/{site['name']}] 수집 실패(무시): {type(e).__name__}: {e}", file=sys.stderr)
                continue
            print(f"[지자체/{site['name']}] 후보 {len(got)}건")
            for p in got:
                if p.ref not in seen:
                    seen.add(p.ref)
                    out.append(p)
        return out

    def _crawl_site(self, site: dict, since: date) -> list[JobPosting]:
        out: list[JobPosting] = []
        seen: set[str] = set()
        since_iso = since.isoformat()
        today_iso = date.today().isoformat()
        js_views = [(re.compile(p), t) for p, t in site.get("js_view", [])]
        for url_tpl in site["urls"]:
            base_url = url_tpl.split("{")[0]
            mid_m = re.search(r"mId=(\d+)", base_url)
            reached_old = False
            for page in range(1, MAX_PAGES_PER_BOARD + 1):
                html = self.get(url_tpl.format(page=page))
                items = self._items(html)
                if not items and page == 1 and js_views:
                    items = self._items_from_js(html, [p for p, _ in js_views])
                if not items:
                    break
                for title, href, dates, row_html in items:
                    posted = min(dates) if dates else ""
                    if posted and posted < since_iso:          # 게시일 내림차순 전제
                        reached_old = True
                        continue
                    if NOISE_RE.search(title):                  # 결과 발표류 제외
                        continue
                    if "ico_finish" in row_html:                # [접수마감] 배지 제외 (의정부)
                        continue
                    if not is_regular(title):                   # 임기제/기간제 제외
                        continue
                    full_url = self._view_url(base_url, site, href, mid_m.group(1) if mid_m else "")
                    if not full_url or full_url in seen:
                        continue
                    deadline = _iso(max(dates)) if len(dates) >= 2 else "미공개"
                    if deadline != "미공개" and deadline < today_iso:
                        continue
                    seen.add(full_url)
                    out.append(JobPosting(
                        source=self.source,
                        org=site["name"],
                        title=title,
                        url=full_url,
                        deadline=deadline,
                        headcount_text="", detail_text="",
                        ref=full_url, region=site["region"],
                    ))
                if reached_old:
                    break
        return out

    def fetch_detail(self, p: JobPosting) -> str:
        html = self.get(p.url)
        self._detail_cache = (p.url, html)
        return self.soup(html).get_text("\n", strip=True)[:4000]

    def fetch_attachment_text(self, p: JobPosting) -> str:
        # javascript 다운로드(gojobs식 gfn_fileDown)는 미지원 — 직접 링크만
        url, html = getattr(self, "_detail_cache", ("", ""))
        if url != p.url:
            html = self.get(p.url)
        links = []
        for a in self.soup(html).find_all("a", href=True):
            h = a["href"]
            if h.startswith(("javascript", "#")):
                continue
            label = a.get_text(" ", strip=True)
            if ATTACH_LINK_RE.search(h) or FILE_EXT_RE.search(label or h):
                links.append(requests.compat.urljoin(p.url, h.replace("&amp;", "&")))
            if len(links) >= MAX_ATTACHMENTS:
                break
        texts, total = [], 0
        for u in links:
            try:
                r = self.s.get(u, timeout=config.HTTP_TIMEOUT * 2, verify=False)
                if len(r.content) > MAX_ATTACH_BYTES:
                    continue
                t = attach.extract_text(u.rsplit("/", 1)[-1].split("?")[0], r.content)
            except Exception:
                continue
            if t:
                texts.append(t)
                total += len(t)
            if total >= attach.MAX_TEXT_CHARS:
                break
        return "\n".join(texts)[:attach.MAX_TEXT_CHARS]

    def _view_url(self, base_url: str, site: dict, href: str, mid: str) -> str:
        if href.startswith(("http", "/", "./")):
            return requests.compat.urljoin(base_url, href)
        for pat, tpl in site.get("js_view", []):
            m = re.search(pat, href)
            if m:
                gd = m.groupdict()
                return tpl.format(id=gd["id"], pt=gd.get("pt") or "", mid=gd.get("mid") or mid)
        return ""

    def _items(self, html: str) -> list[tuple]:
        """표 기반 게시판: th에 '제목' 포함 첫 표. 없으면 nttId 링크(div형, 광진)."""
        out: list[tuple] = []
        for t in self.soup(html).find_all("table"):
            th_texts = [th.get_text(strip=True) for th in t.find_all("th")]
            if any("제목" in x for x in th_texts):
                for tr in t.find_all("tr"):
                    anchors = [a for a in tr.find_all("a", href=True)
                               if a["href"].startswith(("/", "http", "./"))]
                    if not anchors:
                        continue
                    a = max(anchors, key=lambda x: len(x.get_text(strip=True)))
                    title = a.get_text(strip=True)
                    if len(title) < 8:
                        continue
                    dates = [_iso(x.group()) for x in DATE_RE.finditer(tr.get_text(" ", strip=True))]
                    out.append((title, a["href"], dates, str(tr)))
        if out:
            return out
        # div형 리스트 (광진): view 앵커 직접 수집
        soup = self.soup(html)
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if ("view.do?nttId=" in h or "BbsView" in h) and h.startswith(("/", "http")):
                title = a.get_text(strip=True)
                if len(title) < 8 or "더보기" in title:
                    continue
                container = a.find_parent(["tr", "li", "div"])
                text = container.get_text(" ", strip=True) if container else ""
                dates = [_iso(x.group()) for x in DATE_RE.finditer(text)]
                out.append((title, h, dates, ""))
        return out

    def _items_from_js(self, html: str, patterns: list) -> list[tuple]:
        """javascript 함수형 상세(노원/의정부): onclick 에서 id 뽑아 행 단위 재조립."""
        out: list[tuple] = []
        for tr in self.soup(html).find_all("tr"):
            row_html = str(tr)
            hit = next((p.search(row_html) for p in patterns if p.search(row_html)), None)
            if hit is None:
                continue
            title_el = tr.find(class_=re.compile("subject|taL|list_tit"))
            a = tr.find("a")
            node = title_el or a
            title = node.get_text(strip=True) if node is not None else ""
            title = re.sub(r"^(진행|마감)\s*", "", title)
            if len(title) < 8:
                continue
            dates = [_iso(x.group()) for x in DATE_RE.finditer(tr.get_text(" ", strip=True))]
            out.append((title, hit.group(0), dates, row_html))
        return out
