"""서류 합격 확률 점수화 (100점 만점, 프로필 2종 동시 계산).

  [A] 현재 프로필   : 4년제 학사 + 물리학과(비전산) + 자격증 없음
  [B] 시뮬레이션    : 위 프로필 + 정보처리기사 취득 가정

  배점
   - 학력/전공      : 대졸 요건 충족 +40 (단, '전산·관련 전공' 요건 공고는 전공 불일치로 +20)
                      석사 이상 요건 → 지원불가
   - 자격증         : 불필요 +30 / 가산점만 A:+20 B:+25 /
                      (정보처리기사 등 기사급)필수 → A:지원불가 B:+20 / 기타 자격 필수 → 양쪽 지원불가
   - 선발인원       : 1명 +10 / 2~4명 +20 / 5명 이상 +30 (미공개 +20)
  등급 : 80↑ 상 / 60~79 중 / 60↓ 하
"""
from __future__ import annotations

import re

import config
from models import JobPosting

_CERT_REQUIRED_IT = [
    r"자격증?\s*(?:필수|소지.{0,2}필수|보유.{0,2}필수)",
    r"(?:정보처리기사|전산?관련\s*기사급|전산?기사)\s*(?:이상)?\s*(?:필수|소지자|보유자)",
    r"(?:1급|2급)\s*(?:이상\s*)?자격증?\s*(?:필수|소지)",
]
_CERT_REQUIRED_OTHER = [
    r"(?:전기|소방|에너지|측량|건설|품질|위험물)\s*기사\s*(?:이상)?\s*(?:필수|소지자)",
    r"(?:승강기|발파|용접|특수)[^\n]{0,8}(?:기사|기능사)\s*(?:필수|소지자)",
]
_CERT_BONUS = [r"자격증?\s*우대", r"우대\s*(?:사항|항목)[^\n]{0,30}자격", r"가산점", r"정보처리기사\s*우대"]
_MAJOR_REQ = [r"(?:전산|컴퓨터(?:공학)?|정보(?:통신|보안)?|소프트웨어|SW)[^\n]{0,6}전공", r"관련\s*전공(?:자)?", r"\bit\s*관련\s*전공"]
_EDU_FAIL = [r"석사", r"박사"]
_HEADCOUNT_RE = re.compile(r"(\d+)\s*명")

_IRREGULAR = ["기간제", "계약직", "임기제", "촉탁", "시간선택제", "일용", "위촉", "인턴"]


def _has(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def _find(text: str, patterns: list[str]) -> str:
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0).strip()
    return ""


def parse_headcount(text: str) -> int | None:
    m = _HEADCOUNT_RE.search(text or "")
    return int(m.group(1)) if m else None


def is_regular(title_detail: str) -> bool:
    excl = getattr(config, "EXCLUDE_EMPLOYMENT", None)
    if excl is None:
        excl = _IRREGULAR
    return not any(k in (title_detail or "") for k in excl)


def deadline_open(deadline: str, today_iso: str) -> bool:
    dates = re.findall(r"20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}", deadline or "")
    if not dates:
        return True
    normed = [d.replace(".", "-").replace("/", "-") for d in dates]
    return any(d[:10] >= today_iso[:10] for d in normed)


def _base_points(text: str) -> tuple[int, str]:
    if _has(text, _EDU_FAIL):
        return 0, "석사 이상 요건 — 학사 프로필 지원불가"
    if _has(text, _MAJOR_REQ):
        return 20, "전산 관련 전공 요건 — 비전공(물리학) 감점"
    return 40, "대졸 요건 충족"


def _cert_category(text: str) -> str:
    if _has(text, _CERT_REQUIRED_OTHER):
        return "required_other"
    if _has(text, _CERT_REQUIRED_IT):
        return "required_it"
    if _has(text, _CERT_BONUS):
        return "bonus"
    return "none"


def _cert_points(cat: str, has_cert: bool) -> tuple[int, bool]:
    if cat == "required_other":
        return 0, False
    if cat == "required_it":
        return (20, True) if has_cert else (0, False)
    if cat == "bonus":
        return (25, True) if has_cert else (20, True)
    return 30, True


def _grade(score: int, eligible: bool) -> str:
    if not eligible:
        return "지원불가"
    return "상" if score >= 80 else ("중" if score >= 60 else "하")


def _head_points(p: JobPosting) -> tuple[int, str]:
    n = parse_headcount(p.headcount_text)
    if n is None:
        return 20, "선발인원 미공개(중립)"
    if n >= 5:
        return 30, f"{n}명 대량채용"
    if n >= 2:
        return 20, f"{n}명 채용"
    return 10, "1명 소수채용"


def score_posting(p: JobPosting) -> JobPosting:
    text = f"{p.title}\n{p.detail_text}"
    base_pts, base_note = _base_points(text)
    cat = _cert_category(text)
    p.cert_req = _find(text, _CERT_REQUIRED_OTHER) or _find(text, _CERT_REQUIRED_IT)
    head_pts, head_note = _head_points(p)

    has_cert_now = bool(config.PROFILE["certificates"])
    a_pts, a_ok = _cert_points(cat, has_cert_now)
    b_pts, b_ok = _cert_points(cat, True)

    p.score = max(base_pts, 0) + a_pts + head_pts
    p.grade = _grade(p.score, a_ok and base_pts > 0)
    if p.grade == "지원불가":
        p.score = 0                      # 지원불가 공고는 스펙대로 0점 처리

    sim_base = base_pts if base_pts > 0 else 20
    p.sim_score = max(sim_base, 0) + b_pts + head_pts
    p.sim_grade = _grade(p.sim_score, b_ok and base_pts > 0)
    if p.sim_grade == "지원불가":
        p.sim_score = 0

    tips = []
    if not a_ok and base_pts > 0:
        tips.append(f"{config.PROFILE['target_cert']} 취득 시 지원 가능해지는 공고")
    elif cat == "bonus":
        tips.append("자격증은 가산점일 뿐 필수 아님 — 서류/필기 승부 가능")
    if base_pts == 20:
        tips.append(f"전공 요건 공고 — {config.PROFILE.get('major', '')} 전공은 프로젝트·실무경력 기술로 보완 필요")
    if base_pts == 0:
        tips.append(base_note)
    if parse_headcount(p.headcount_text):
        tips.append(head_note)
    if "잡플러스" in p.source:
        tips.append("지방공공기관 통합 공고 특성상 자격증 가점 비중이 낮음")
    p.advice = ", ".join(tips) + "." if tips else "조건이 평이하니 마감 전 원서를 꼼꼼히 준비하세요."

    if p.sim_score > p.score:
        p.advice += f" ▸ {config.PROFILE['target_cert']} 취득 시 {p.score}점({p.grade})→{p.sim_score}점({p.sim_grade})"
    return p


def score_all(postings: list[JobPosting]) -> list[JobPosting]:
    return [score_posting(p) for p in postings]


if __name__ == "__main__":
    config.PROFILE = {"certificates": [], "target_cert": "정보처리기사", "major": "물리학과"}  # 단독 실행용 픽스처
    a = score_posting(JobPosting("잡플러스", "테스트재단", "[정보화팀] 전산직 정규직 채용", "u", "2026-09-08", "5명"))
    assert a.score == 100 and a.grade == "상" and a.sim_score == 100, (a.score, a.sim_score)
    b = score_posting(JobPosting("나라일터", "테스트청", "정보처리기사 필수 전산직 정규직 채용", "u", "~", "1명"))
    assert b.grade == "지원불가" and b.score == 0 and b.sim_grade != "지원불가", (b.score, b.sim_score)
    c = score_posting(JobPosting("알리오", "테스트공단", "컴퓨터공학 전공자 전산직 정규직 채용", "u", "~", ""))
    assert c.score == 70 and c.grade == "중", (c.score, c.grade)  # 전공감점20+불필요30+미공개20
    d = score_posting(JobPosting("알리오", "테스트공단", "발전소 계측제어 전산직 정규직 (전기기사 필수)", "u", "~", ""))
    assert d.grade == "지원불가" and d.score == 0 and d.sim_grade == "지원불가", (d.grade, d.sim_grade)
    assert b.score == 0 and b.sim_score == 70, (b.score, b.sim_score)
    assert "정보처리기사" in b.cert_req, b.cert_req          # 필수 자격증 문구 추출
    assert d.cert_req and "전기기사" in d.cert_req, d.cert_req
    assert not a.cert_req and not c.cert_req, (a.cert_req, c.cert_req)
    print(f"scorer OK: A={a.score}/{a.grade} | 기사없음={b.score}/{b.grade} → 기사있음={b.sim_score}/{b.sim_grade} | 전공감점={c.score}/{c.grade} | cert_req: b='{b.cert_req}' d='{d.cert_req}'")
