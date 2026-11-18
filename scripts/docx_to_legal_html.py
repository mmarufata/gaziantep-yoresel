"""Word (.docx) yasal metinlerini HTML parçalarına dönüştürür."""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "templates" / "legal" / "content"

MAPPING = {
    "GİZLİLİK POLİTİKASI": "gizlilik.html",
    "KULLANIM KOŞULLARI": "kullanim_kosullari.html",
    "KVKK AYDINLATMA METNİ": "kvkk_aydinlatma.html",
    "MESAFELİ SATIŞ SÖZLEŞMESİ": "mesafeli_satis.html",
    "ÇEREZ POLİTİKASI": "cerez_politikasi.html",
    "ÖN BİLGİLENDİRME FORMU": "on_bilgilendirme.html",
}

REPLACEMENTS = [
    (r"\[siteadi\]\.com", "Gaziantep Yöresel internet sitesi"),
    (r"\[site adı\]", "Gaziantep Yöresel"),
    (r"\[mail adresi\]", "meksemes612@gmail.com"),
    (r"\[tarih\]", "Mayıs 2026"),
    (r"\[ALICI ADI/SOYADI\]", "…"),
    (r"\[ALICI ADRESİ\]", "…"),
    (r"\[ALICI TELEFON\]", "…"),
    (r"\[ALICI E-POSTA\]", "…"),
]


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.upper().replace(".DOCX", "").strip())


def paragraph_text(p_elem) -> str:
    parts = []
    for elem in p_elem.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "t" and elem.text:
            parts.append(elem.text)
        elif tag == "tab":
            parts.append(" ")
        elif tag == "br":
            parts.append("\n")
    return "".join(parts).strip()


def looks_like_heading(text: str) -> bool:
    if not text or len(text) > 120:
        return False
    if re.match(r"^(Madde\s+\d+|[0-9]+\.)", text, re.I):
        return True
    if re.match(r"^[0-9]+\.\s+[A-ZÇĞİÖŞÜ]", text):
        return True
    if text.isupper() and len(text) < 90:
        return True
    if re.match(r"^(SATICI|ALICI|VERİ SORUMLUSU)\s*:", text, re.I):
        return True
    return False


def format_block(text: str) -> str:
    for pat, repl in REPLACEMENTS:
        text = re.sub(pat, repl, text, flags=re.I)
    return text


def text_to_html(text: str) -> str:
    text = format_block(text)
    if not text:
        return '<p class="mb-4">&nbsp;</p>'

    if looks_like_heading(text.split("\n")[0]):
        first = text.split("\n")[0]
        rest = "\n".join(text.split("\n")[1:]).strip()
        html = f'<h2 class="text-xl font-semibold text-green-900 mb-3 mt-6">{_esc(first)}</h2>'
        if rest:
            html += "\n" + text_to_html(rest)
        return html

    if "•" in text or text.startswith("- "):
        items = re.split(r"\s*•\s*|\n\s*•\s*", text)
        items = [i.strip() for i in items if i.strip()]
        if len(items) > 1:
            lis = "".join(f'<li class="mb-2">{_esc(i)}</li>' for i in items)
            return f'<ul class="list-disc pl-6 mb-4 space-y-1">{lis}</ul>'

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) > 1 and all(len(ln) < 200 for ln in lines):
        return "\n".join(
            f'<p class="mb-2"><strong>{_esc(lines[0].split(":")[0])}:</strong> {_esc(":".join(lines[0].split(":")[1:]).strip()) if ":" in lines[0] else _esc(lines[0])}</p>'
            if i == 0 and ":" in lines[0]
            else f'<p class="mb-2">{_esc(ln)}</p>'
            for i, ln in enumerate(lines)
        )

  # Label: value on same line (Word merge)
    if ":" in text and len(text) < 500:
        chunks = re.split(r"(?<=[a-zğüşıöçA-ZÇĞİÖŞÜ])\s+(?=[A-ZÇĞİÖŞÜ][a-zğüşıöç]+:)", text)
        if len(chunks) > 1:
            return "\n".join(f'<p class="mb-2">{_esc(c)}</p>' for c in chunks)

    return f'<p class="mb-4">{_esc(text)}</p>'


def docx_to_html(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find("w:body", NS)
    html_parts = []

    for child in body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            text = paragraph_text(child)
            html_parts.append(text_to_html(text))
        elif tag == "tbl":
            html_parts.append(_table_to_html(child))

    return "\n".join(html_parts)


def _table_to_html(tbl) -> str:
    rows_html = []
    for tr in tbl.findall("w:tr", NS):
        cells = []
        for tc in tr.findall("w:tc", NS):
            cell_text = []
            for p in tc.findall(".//w:p", NS):
                t = paragraph_text(p)
                if t:
                    cell_text.append(t)
            cells.append(
                f'<td class="border border-gray-300 px-3 py-2 align-top">{_esc(" ".join(cell_text))}</td>'
            )
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    if not rows_html:
        return ""
    return (
        '<motion class="overflow-x-auto mb-6">'
        '<table class="w-full border-collapse text-left text-base">'
        + "".join(rows_html)
        + "</table></div>"
    ).replace("<motion", "<div").replace("</motion>", "</motion>")


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def match_output(docx: Path) -> str | None:
    stem = normalize_name(docx.stem)
    for k, v in MAPPING.items():
        if normalize_name(k) == stem:
            return v
    for k, v in MAPPING.items():
        if normalize_name(k)[:8] in stem or stem[:8] in normalize_name(k):
            return v
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for docx in sorted(BASE.glob("*.docx")):
        out_name = match_output(docx)
        if not out_name:
            print("SKIP:", docx.name)
            continue
        html_body = docx_to_html(docx)
        (OUT / out_name).write_text(html_body, encoding="utf-8")
        print("OK", docx.name, "->", out_name)


if __name__ == "__main__":
    main()
