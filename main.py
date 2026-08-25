"""일일 파이프라인: 사이트 수집 → 중복제거 → 상세분석 → 필터 → 점수화 → Discord 알림."""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import config
from crawlers import CRAWLERS
from models import JobPosting, deduplicate
from notifier import send
from scorer import deadline_open, is_regular, parse_headcount, score_all

def _seen_path(prof: dict) -> Path:
    safe = "".join(c for c in prof["name"] if c.isalnum() or c in "_-") or "default"
    return Path(__file__).parent / f"recruit_seen_{safe}.json"


def _load_seen(path: Path) -> set:
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_seen(path: Path, keys: set) -> None:
    recent = sorted(keys)[-3000:]           # 무한 증가 방지
    path.write_text(json.dumps(recent, ensure_ascii=False), encoding="utf-8")


def enrich_headcount(text: str) -> str:
    m = (re.search(r"(?:모집|선발|채용)[^\n]{0,60}?(\d+)\s*명", text)
         or re.search(r"(\d+)\s*명", text))
    return f"{m.group(1)}명" if m else ""


def run_profile(prof: dict) -> None:
    # scorer/notifier/crawlers는 호출 시점에 config.* 를 읽으므로,
    # 실행 직전 config 전역을 이 프로필 값으로 교체하면 하위 모듈 수정 없이 사람별 설정이 적용된다.
    config.OWNER_NAME = prof["name"]
    config.KEYWORDS = prof["keywords"]
    config.REGIONS = prof["regions"]
    config.EXCLUDE_EMPLOYMENT = prof.get("exclude_employment") or []
    config.TITLE_EXCLUDE = prof.get("title_exclude") or []
    config.PROFILE = prof["profile"]

    print(f"\n===== 👤 [{prof['name']}] =====")
    today_iso = date.today().isoformat()
    since = date.today() - timedelta(days=config.SINCE_DAYS)
    postings: list[JobPosting] = []

    for cls in CRAWLERS:
        crawler = cls()
        try:
            got = crawler.crawl(config.KEYWORDS, since)
            print(f"[{crawler.source}] 신규 후보 {len(got)}건")
            postings += got
        except Exception as e:
            print(f"[{crawler.source}] 수집 실패(무시하고 계속): {type(e).__name__}: {e}", file=sys.stderr)

    postings = deduplicate(postings)
    print(f"중복 제거 후 {len(postings)}건")
    if len(postings) > config.DETAIL_LIMIT:
        print(f"상세 분석은 최신 {config.DETAIL_LIMIT}건만 진행", file=sys.stderr)

    crawlers = {c.source: c for c in (cls() for cls in CRAWLERS)}
    kept: list[JobPosting] = []
    for p in postings[:config.DETAIL_LIMIT]:
        crawler = crawlers.get(p.source)
        if crawler is None:
            continue
        try:
            p.detail_text = crawler.fetch_detail(p)
        except Exception as e:
            print(f"상세 실패 [{p.title[:24]}]: {e}", file=sys.stderr)
            continue

        blob = f"{p.title}\n{p.detail_text}"
        if not any(k.lower() in p.title.lower() for k in config.KEYWORDS):
            # 제목에 키워드 없을 때만 첨부 파싱(다운로드 비용 절약) — 본문/첨부에서 재매칭
            try:
                att = crawler.fetch_attachment_text(p)
            except Exception as e:
                print(f"첨부 파싱 실패 [{p.title[:20]}]: {e}", file=sys.stderr)
                att = ""
            if att:
                p.detail_text = f"{p.detail_text}\n[첨부] {att}".strip()[:8000]
                blob = f"{p.title}\n{p.detail_text}"
        if not any(k.lower() in blob.lower() for k in config.KEYWORDS):
            continue
        if any(x in p.title for x in getattr(config, "TITLE_EXCLUDE", [])):
            continue                       # 제목 블랙리스트 (설정 없으면 미적용)
        if not is_regular(blob):                       # 기간제/계약직 등 제외
            continue
        if not any(r in (p.region or blob) for r in config.REGIONS):   # 서울/경기만
            continue
        if not deadline_open(p.deadline, today_iso):   # 마감 제외 안전망
            continue
        if not p.headcount_text:
            p.headcount_text = enrich_headcount(p.detail_text)
        kept.append(p)

    score_all(kept)
    kept.sort(key=lambda x: (-(x.score or 0), -(x.sim_score or 0)))

    spath = _seen_path(prof)
    seen = _load_seen(spath)
    kept = [p for p in kept if p.dedup_key() not in seen]   # 이미 알림한 공고 재발송 방지

    print(f"[{prof['name']}] 최종 알림 대상 {len(kept)}건")
    try:
        send(kept)                                          # 빈 목록이면 '신규 없음' 하트비트 전송
        _save_seen(spath, seen | {p.dedup_key() for p in kept})
    except Exception as e:
        print(f"Discord 전송 실패: {type(e).__name__}: {e}", file=sys.stderr)


def main() -> None:
    for prof in config.PROFILES:
        try:
            run_profile(prof)
        except Exception as e:
            print(f"[{prof['name']}] 프로필 실행 실패(무시하고 계속): {type(e).__name__}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
