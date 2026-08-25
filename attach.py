"""첨부파일(pdf/hwpx/hwp) 텍스트 추출 — 키워드 매칭 보조용.

hwp: HWP5(레코드 walk) 우선, 실패/짧으면 HWP3의 PrvText(미리보기)로 폴백.
ponytail: HWP3 원본 본문은 암호화되어 파싱 불가 → PrvText ~1KB 만 매칭 대상.
"""
from __future__ import annotations

import io
import re
import struct
import zipfile
import zlib

MAX_TEXT_CHARS = 6000

_CTRL_RE = re.compile(r"[\x00-\x11\x200b\ufeff]")


def extract_text(filename: str, data: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext not in ("pdf", "hwp", "hwpx"):
        ext = _sniff(data)                          # URL에 확장자 없는 경우
    try:
        if ext == "pdf":
            text = _pdf(data)
        elif ext == "hwpx":
            text = _hwpx(data)
        elif ext == "hwp":
            text = _hwp(data)
        else:
            return ""
    except Exception:
        return ""
    return _clean(text)[:MAX_TEXT_CHARS]


def _sniff(data: bytes) -> str:
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        return "hwpx"
    if data[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):
        return "hwp"
    return ""


def _clean(text: str) -> str:
    return re.sub(r"[ \t\r]+", " ", _CTRL_RE.sub(" ", text))


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:15]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def _hwpx(data: bytes) -> str:
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if not name.lower().endswith(".xml"):
                continue
            xml = z.read(name).decode("utf-8", errors="ignore")
            txt = re.sub(r"<[^>]+>", " ", xml)
            txt = re.sub(r"\s+", " ", txt).strip()
            if len(txt) > 50:                       # 본문 xml만 (매니페스트 제외)
                out.append(txt)
    return "\n".join(out)


def _hwp(data: bytes) -> str:
    import olefile
    ole = olefile.OleFileIO(io.BytesIO(data))
    text = _hwp5_body(ole)
    if len(text.strip()) < 80:                      # HWP5 파싱 실패 → HWP3 PrvText
        text += "\n" + _prvtext(ole)
    return text


def _hwp5_body(ole) -> str:
    out = []
    for name in ole.listdir():
        if len(name) == 2 and name[0] == "BodyText" and name[1].startswith("Section"):
            plain = _decode_section(ole.openstream(name).read())
            out.append(_walk_para_text(plain))
    return "".join(out)


def _decode_section(raw: bytes) -> bytes:
    if len(raw) > 34:
        size = struct.unpack_from("<I", raw)[0] & 0x3FF
        try:
            return zlib.decompress(raw[4 + size:], -15)
        except zlib.error:
            pass
    return raw                                      # 무압축 문서


def _walk_para_text(plain: bytes) -> str:
    """HWP5 레코드 순회, PARA_TEXT(tag=67)만 수집."""
    out, pos = [], 0
    while pos + 4 <= len(plain):
        hdr = struct.unpack_from("<I", plain, pos)[0]
        size, tag = hdr & 0x3FF, (hdr >> 10) & 0x3FF
        pos += 4
        chunk = plain[pos:pos + size]
        pos += size
        if tag == 67 and chunk:
            out.append(chunk.decode("utf-16-le", errors="ignore"))
    return "".join(out)


def _prvtext(ole) -> str:
    try:
        return ole.openstream("PrvText").read().decode("utf-16-le", errors="ignore")
    except Exception:
        return ""
