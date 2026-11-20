"""Read units / amount / month from a bill photo using RapidOCR (pip-only, no external app).
Always confirm the extracted values with the user."""
import io, re

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as e:
            raise RuntimeError(f"OCR package problem: {e}")
        _engine = RapidOCR()
    return _engine


def ocr_image(data: bytes) -> str:
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if img.width > 2000:                       # keep large phone photos fast
        img = img.resize((2000, int(img.height * 2000 / img.width)))
    result, _ = _get_engine()(np.array(img))
    if not result:
        return ""
    # rebuild text lines: group boxes whose vertical centres are close, then order left to right
    items = [(sum(p[1] for p in box) / 4, box[0][0], txt, max(abs(box[2][1] - box[0][1]), 1))
             for box, txt, _ in result]
    items.sort()
    heights = sorted(i[3] for i in items)
    tol = heights[len(heights) // 2] * 0.6
    lines, cur, cy = [], [], None
    for y, x, txt, _ in items:
        if cy is None or abs(y - cy) <= tol:
            cur.append((x, txt)); cy = y if cy is None else (cy + y) / 2
        else:
            lines.append(cur); cur, cy = [(x, txt)], y
    if cur:
        lines.append(cur)
    return "\n".join(" ".join(t for _, t in sorted(l)) for l in lines)


def extract_bill_fields(text: str) -> dict:
    t = text.replace(",", "")
    units = amount = month = None
    for pat in [r"(?:units?\s*consumed|consumption|total\s*units|net\s*units)\D{0,25}(\d{1,5}(?:\.\d+)?)",
                r"(\d{1,5}(?:\.\d+)?)\s*(?:units|kwh)\b"]:
        m = re.search(pat, t, re.I)
        if m:
            units = float(m.group(1)); break
    m = re.search(r"(?:net\s*payable|amount\s*payable|total\s*amount|amount\s*due|bill\s*amount|net\s*amount)\D{0,25}(\d{2,7}(?:\.\d{1,2})?)", t, re.I)
    if m:
        amount = float(m.group(1))
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,'\-/]*(\d{4})", t, re.I)
    if m:
        month = f"{m.group(2)}-{MONTHS[m.group(1).lower()[:3]]:02d}"
    else:
        m = re.search(r"\b(0?[1-9]|1[0-2])[/\-](20\d{2})\b", t)
        if m:
            month = f"{m.group(2)}-{int(m.group(1)):02d}"
    return {"units": units, "amount": amount, "month": month, "raw_text": text[:1500]}