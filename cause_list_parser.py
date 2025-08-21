# cause_list_parser.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, sys, argparse
from pathlib import Path
import fitz  # PyMuPDF

# ---------- regex ----------
# ⬇️ allow 1–3 digits before the optional ".sub" part (so 101, 115.30, etc.)
SERIAL_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)\b")
COURT_NUM_RE = re.compile(r"COURT\s*NO\.?\s*[:\-]?\s*(\d+)", re.IGNORECASE)
CHIEF_JUSTICE_RE = re.compile(r"CHIEF\s+JUSTICE'?S\s+COURT", re.IGNORECASE)
VERSUS_RE = re.compile(r"^\s*versus\.?\s*$", re.IGNORECASE)

# ignore boilerplate
IGNORE_HEAD = re.compile(
    r"(SUPREME COURT OF INDIA|IT WILL BE APPRECIATED|LISTED BEFORE|DAILY CAUSE LIST|"
    r"NOTE|MISCELLANEOUS HEARING|PUBLIC INTEREST LITIGATIONS|SNo\.\s*Case No\.|Petitioner/Respondent)",
    re.IGNORECASE,
)

def smart_title(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    kept = {"U.P.", "NCT", "SLP", "S.L.P.", "IA", "I.A.", "Ltd.", "LTD.", "CBI", "GST", "W.P.(C)", "T.P.(C)", "T.P.(Crl.)"}
    lowers = {"and", "of", "the", "by", "on", "for", "to", "in", "vs", "vs.", "alias", "@"}
    out = []
    for i, w in enumerate(s.split()):
        if any(ch.isdigit() for ch in w) or ('.' in w and w.upper() == w) or w.upper() in kept:
            out.append(w)
        else:
            base = w.lower()
            out.append(base if (base in lowers and i != 0) else base.capitalize())
    return " ".join(out).strip(" ,.-")

def is_meta_line(line: str) -> bool:
    if IGNORE_HEAD.search(line):
        return True
    if re.search(r"\bNo\.", line):
        return True
    if re.fullmatch(r"[IVXLC]+(-[A-Z])?", line):
        return True
    if re.fullmatch(r"[\d/().-]+", line):
        return True
    if re.search(r"\bPIL(?:-W|\b)", line):
        return True
    if re.search(r"IA No\.|FOR ADMISSION|EXEMPTION FROM FILING|CONDONATION OF DELAY|O\.T\.", line, re.IGNORECASE):
        return True
    if re.fullmatch(r"Connected", line):
        return True
    return False

# ----- court detection -----
def detect_court_number(page) -> int | None:
    txt = page.get_text("text")
    if CHIEF_JUSTICE_RE.search(txt):
        return 1
    m = COURT_NUM_RE.search(txt)
    if m:
        return int(m.group(1))
    for (x0,y0,x1,y1,t,*_) in page.get_text("blocks"):
        if y1 > 180: break
        if CHIEF_JUSTICE_RE.search(t): return 1
        mm = COURT_NUM_RE.search(t)
        if mm: return int(mm.group(1))
    return None

def page_split_x(page) -> float:
    words = page.get_text("words")
    h = page.rect.height
    adv = [w for w in words if w[4].lower().startswith("advocate") and w[1] < h*0.35]
    if adv:
        return min(w[0] for w in adv)
    pr = [w for w in words if "petitioner/respondent" in w[4].lower() and w[1] < h*0.35]
    if pr:
        return max(w[2] for w in pr) + 10
    return page.rect.width * 0.70

# ----- main parse -----
def parse_pdf(pdf_path: str):
    doc = fitz.open(pdf_path)
    items, last_court = [], None

    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        court = detect_court_number(page) or last_court
        if court: last_court = court

        split_x = page_split_x(page)
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1],1), round(b[0],1)))

        current = None
        capture_resp = False

        for (x0,y0,x1,y1,text,*_) in blocks:
            is_left = x0 < split_x
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue

                if is_left:
                    m = SERIAL_RE.match(line)
                    if m:
                        current = {"court": court, "serial": m.group(1),
                                   "petitioner": None, "respondent": None, "page": pno+1}
                        items.append(current)
                        capture_resp = False
                        continue

                if is_meta_line(line):
                    continue

                if VERSUS_RE.match(line):
                    capture_resp = True
                    continue

                if is_left and current:
                    if current["petitioner"] is None and not capture_resp:
                        current["petitioner"] = smart_title(line)
                        continue
                    if capture_resp and current["respondent"] is None:
                        current["respondent"] = smart_title(line)
                        capture_resp = False
                        continue

    return [it for it in items if it.get("court") and it.get("petitioner") and it.get("respondent")]

def build_index(items):
    idx = {}
    for it in items:
        key = f"{it['court']}/{it['serial']}"
        if key not in idx:
            idx[key] = it
    return idx

def format_line(it):
    return f"{it['court']}/{it['serial']} - {it['petitioner']} Vs {it['respondent']}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--refs")
    ap.add_argument("--refs-file")
    ap.add_argument("--dump-all", action="store_true")
    args = ap.parse_args()

    items = parse_pdf(args.pdf)
    idx = build_index(items)

    if args.dump_all:
        def key_fn(k): c,s = k.split("/"); return (int(c), float(s))
        for k in sorted(idx.keys(), key=key_fn):
            print(format_line(idx[k]))
        return

    req = []
    if args.refs:
        req += [r.strip() for r in args.refs.split(",") if r.strip()]
    if args.refs_file:
        req += [ln.strip() for ln in Path(args.refs_file).read_text(encoding="utf-8").splitlines() if ln.strip()]

    if not req:
        print("Provide --refs or --refs-file or use --dump-all")
        sys.exit(1)

    for r in req:
        it = idx.get(r)
        print(format_line(it) if it else f"{r} - NOT FOUND")

if __name__ == "__main__":
    main()
