"""Discord Webhook 알림 발송 (의존성 최소화: requests만 사용)."""
from __future__ import annotations

import requests

import config
from models import JobPosting

# Discord 제한: 요청당 최대 10개 embed
_BATCH = 10


def _embed(p: JobPosting) -> dict:
    fields = [
        {"name": "📅 접수 마감 / 선발인원", "value": f"{p.deadline} / {p.headcount_text or '미공개'}", "inline": False},
        {"name": "📊 합격 확률 분석", "value": (
            f"현재 프로필: {p.score}점 / 100점 (등급: {p.grade})\n"
            f"{config.PROFILE['target_cert']} 취득 시: {p.sim_score}점 / 100점 (등급: {p.sim_grade})"
        ), "inline": False},
    ]
    if p.cert_req:
        fields.append({"name": "📜 요구 자격증", "value": p.cert_req, "inline": False})
    fields.append({"name": "💡 추천 전략", "value": p.advice or "-", "inline": False})
    return {
        "title": f"👤 [{config.OWNER_NAME}] 📌 [{p.source} / {p.org}] {p.title}",
        "url": p.url,
        "color": 0x2ECC71 if p.grade == "상" else (0xF1C40F if p.grade == "중" else 0xE74C3C),
        "fields": fields,
    }


def send(postings: list[JobPosting]) -> None:
    """공고 목록을 Discord로 전송. WEBHOOK_URL 미설정 시 스킵(드라이런)."""
    url = config.DISCORD_WEBHOOK_URL
    if not url:
        print("[notifier] DISCORD_WEBHOOK_URL 미설정 → 콘솔 출력으로 대체")
        for p in postings:
            req = f"\n   📜 요구 자격증: {p.cert_req}" if p.cert_req else ""
            print(f"📌 [{p.source} / {p.org}] {p.title}\n   🔗 {p.url}\n"
                  f"   📅 {p.deadline} / {p.headcount_text or '미공개'}{req}\n"
                  f"   📊 현재 {p.score}점({p.grade}) · 기사취득시 {p.sim_score}점({p.sim_grade})\n   💡 {p.advice}")
        return

    username = f"공공기관 채용 알리미 ({config.OWNER_NAME})"
    if not postings:
        requests.post(url, json={"username": username,
                                 "content": f"👤 [{config.OWNER_NAME}] ☀️ 오늘 조건에 맞는 신규 공고가 없습니다."},
                      timeout=15).raise_for_status()
        return

    for i in range(0, len(postings), _BATCH):
        payload = {
            "username": username,
            "embeds": [_embed(p) for p in postings[i:i + _BATCH]],
        }
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
