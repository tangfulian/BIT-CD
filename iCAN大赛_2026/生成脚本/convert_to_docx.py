# -*- coding: utf-8 -*-
"""Convert report.html -> report.docx (editable Word) via bs4 + python-docx."""
import pathlib
from bs4 import BeautifulSoup, NavigableString, Tag
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD\.claude\iCAN_out")
ASSETS = BASE / "assets"
HTML_PATH = BASE / "report.html"
OUT_PATH = BASE / "report.docx"

GREEN = RGBColor(0x2D, 0x6A, 0x4F)
GREEN2 = RGBColor(0x40, 0x91, 0x6C)
DARK = RGBColor(0x1B, 0x43, 0x32)
TEXT = RGBColor(0x2B, 0x2B, 0x2B)
MUTED = RGBColor(0x6B, 0x72, 0x80)
RED = RGBColor(0xC1, 0x12, 0x1F)
CJK = "微软雅黑"
MONO = "Consolas"

# ---- helper: element text / inline render ----

def get_text_skipping(tag, skip):
    """Text of a tag, skipping a child subtree (used to drop .ch-num from h1)."""
    out = []
    for c in tag.children:
        if c is skip or (isinstance(c, Tag) and skip in c.parents and c is skip):
            continue
        if isinstance(c, NavigableString):
            out.append(str(c))
        elif isinstance(c, Tag):
            if c is skip:
                continue
            out.append(c.get_text())
    return "".join(out).strip()

def set_run_font(run, name=CJK, size=None, color=None, bold=None, italic=None):
    run.font.name = name
    r = run._element.get_or_add_rPr()
    rFonts = r.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts'); r.append(rFonts)
    rFonts.set(qn('w:eastAsia'), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic

def shade_run(run, fill):
    rPr = run._element.get_or_add_rPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), fill)
    rPr.append(shd)

def shade_cell(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), fill)
    tcPr.append(shd)

def para_spacing(p, before=0, after=0, line=1.3):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line

def render_inline(p, node, base_size=10.5, base_color=TEXT):
    """Recursively render inline markup into paragraph p."""
    for c in node.children:
        if isinstance(c, NavigableString):
            r = p.add_run(str(c)); set_run_font(r, size=base_size, color=base_color)
        elif isinstance(c, Tag):
            cls = c.get('class') or []
            if c.name in ('strong', 'b'):
                r = p.add_run(c.get_text()); set_run_font(r, size=base_size, bold=True, color=DARK)
            elif c.name == 'code':
                r = p.add_run(c.get_text()); set_run_font(r, name=MONO, size=base_size - 1.5, color=RGBColor(0x1F, 0x29, 0x37))
                shade_run(r, 'F3F4F6')
            elif c.name == 'span' and 'small' in cls:
                r = p.add_run(c.get_text()); set_run_font(r, size=base_size - 1.5, color=MUTED)
            elif c.name == 'br':
                p.add_run().add_break()
            elif c.name == 'span':
                render_inline(p, c, base_size, base_color)
            elif c.name in ('ul', 'ol'):
                # nested list inside a paragraph context -> keep as plain text
                render_inline(p, c, base_size, base_color)
            else:
                render_inline(p, c, base_size, base_color)

# ---- helper: tables ----

def grid_from_table(t):
    rows = t.find_all('tr')
    cells = [tr.find_all(['td', 'th']) for tr in rows]
    grid = {}
    maxcol = 0
    for r, tds in enumerate(cells):
        c = 0
        for td in tds:
            while (r, c) in grid:
                c += 1
            cs = int(td.get('colspan', 1) or 1)
            rs = int(td.get('rowspan', 1) or 1)
            for i in range(rs):
                for j in range(cs):
                    grid[(r + i, c + j)] = td
            c += cs
        maxcol = max(maxcol, c)
    return grid, len(cells), maxcol

def set_cell_margins(cell, top=40, start=80, bottom=40, end=80):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for name, val in (('top', top), ('start', start), ('bottom', bottom), ('end', end)):
        el = OxmlElement('w:' + name)
        el.set(qn('w:w'), str(val)); el.set(qn('w:type'), 'dxa')
        tcMar.append(el)
    tcPr.append(tcMar)

def render_table(t, header_fill='D8F3DC'):
    grid, nrows, ncols = grid_from_table(t)
    tbl = doc.add_table(rows=nrows, cols=ncols)
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = True
    seen = set()
    thead_rows = t.find('thead')
    thead_els = set()
    if thead_rows:
        for tr in thead_rows.find_all('tr'):
            for td in tr.find_all(['td', 'th']):
                thead_els.add(id(td))
    for r in range(nrows):
        for c in range(ncols):
            td = grid.get((r, c))
            if td is None:
                continue
            key = id(td)
            if key in seen:
                continue
            seen.add(key)
            cs = int(td.get('colspan', 1) or 1)
            rs = int(td.get('rowspan', 1) or 1)
            cell = tbl.cell(r, c)
            if rs > 1 or cs > 1:
                cell = cell.merge(tbl.cell(r + rs - 1, c + cs - 1))
            set_cell_margins(cell)
            para = cell.paragraphs[0]
            para_spacing(para, 1, 1, 1.25)
            if 'center' in (td.get('class') or []):
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            is_header = key in thead_els
            render_inline(para, td, base_size=9.5)
            if is_header:
                shade_cell(cell, header_fill)
                for run in para.runs:
                    run.bold = True
                    run.font.color.rgb = DARK
            if td.find('b') and not is_header:
                pass  # keep inner bold as rendered
    # widen the header row if single-char first column like #
    return tbl

# ---- helper: figures ----

def fig_size(ncols):
    page_w = 21.0 - 1.6 * 2  # 17.8 cm usable
    if ncols <= 1:
        return page_w
    gap = 0.25
    return (page_w - gap * (ncols - 1)) / ncols

def render_fig(fig, width_cm):
    img = fig.find('img')
    cap = fig.find(class_='cap')
    if not img:
        return
    src = img.get('src')
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para_spacing(p, 3, 0, 1.0)
    try:
        r = p.add_run()
        r.add_picture(str(ASSETS / pathlib.Path(src).name), width=Cm(width_cm))
    except Exception as e:
        r = p.add_run(f"[图片缺失: {src}]"); set_run_font(r, size=9, color=RED)
    if cap:
        cp = doc.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para_spacing(cp, 1, 6, 1.1)
        r = cp.add_run(cap.get_text()); set_run_font(r, size=8.5, color=MUTED)

# ---- helper: callout / note ----

CALLOUT_BG = {'callout': 'FDF6E3', 'note': 'EEF6FF', 'ok': 'E9F7EF', 'warn': 'FDF3F3'}
CALLOUT_BAR = {'callout': 'F48C06', 'note': '4A90E2', 'ok': '2D9D5F', 'warn': 'C1121F'}

def render_box(div):
    cls = div.get('class') or []
    fill = 'EEF6FF'
    for c in cls:
        if c in CALLOUT_BG:
            fill = CALLOUT_BG[c]
    tbl = doc.add_table(rows=1, cols=1)
    tbl.style = 'Table Grid'
    cell = tbl.cell(0, 0)
    shade_cell(cell, fill)
    set_cell_margins(cell, 100, 140, 100, 140)
    p = cell.paragraphs[0]
    para_spacing(p, 0, 0, 1.3)
    render_inline(p, div, base_size=9.5)
    # spacer after table
    sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(2); sp.paragraph_format.space_before = Pt(0)

# ---- helper: timeline ----

def render_timeline(tl):
    for item in tl.find_all(class_='tl-item'):
        date = item.find(class_='tl-date')
        title = item.find(class_='tl-title')
        body = item.find(class_='tl-body')
        is_ms = bool(item.find(class_='milestone'))
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.35)
        para_spacing(p, 4, 0, 1.25)
        bullet = "● " if is_ms else "○ "
        r = p.add_run(bullet)
        set_run_font(r, size=10, bold=True, color=RED if is_ms else GREEN)
        if date:
            r = p.add_run(date.get_text() + "  ")
            set_run_font(r, size=11.5, bold=True, color=GREEN)
        if title:
            r = p.add_run(title.get_text())
            set_run_font(r, size=11, bold=True, color=DARK)
        if body:
            bp = doc.add_paragraph()
            bp.paragraph_format.left_indent = Cm(0.7)
            para_spacing(bp, 1, 5, 1.3)
            render_inline(bp, body, base_size=10)

# ---- helper: cards ----

def render_cards(cards_div):
    cards = cards_div.find_all(class_='card')
    tbl = doc.add_table(rows=1, cols=len(cards))
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, card in enumerate(cards):
        cell = tbl.cell(0, i)
        shade_cell(cell, 'F8FAF8')
        set_cell_margins(cell, 80, 80, 80, 80)
        num = card.find(class_='num')
        lbl = card.find(class_='lbl')
        p1 = cell.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para_spacing(p1, 0, 0, 1.1)
        if num:
            r = p1.add_run(num.get_text()); set_run_font(r, size=15, bold=True, color=GREEN)
        p2 = cell.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para_spacing(p2, 2, 0, 1.1)
        if lbl:
            r = p2.add_run(lbl.get_text()); set_run_font(r, size=8.5, color=MUTED)
    sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(2)

# ---- render chapters / cover / toc ----

def add_heading(text, level, color=GREEN, size=None, page_break=False):
    if page_break:
        bp = doc.add_paragraph(); bp.add_run().add_break(WD_BREAK.PAGE)
    p = doc.add_paragraph()
    para_spacing(p, 10 if level == 1 else 8, 6, 1.25)
    r = p.add_run(text)
    sz = size or (16 if level == 1 else 12.5)
    set_run_font(r, size=sz, bold=True, color=color)
    if level == 1:
        # bottom border under chapter heading
        pPr = p._element.get_or_add_pPr()
        pbdr = OxmlElement('w:pBdr')
        bottom = OxmlElement('w:bottom')
        bottom.set(qn('w:val'), 'single'); bottom.set(qn('w:sz'), '12')
        bottom.set(qn('w:space'), '4'); bottom.set(qn('w:color'), '2D6A4F')
        pbdr.append(bottom)
        pPr.append(pbdr)
    return p

def render_cover(div, closing=False):
    if closing:
        sp = doc.add_paragraph(); sp.add_run().add_break(WD_BREAK.PAGE)
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para_spacing(p, 60, 10, 1.3)
        r = p.add_run("感谢聆听 · 敬请指正")
        set_run_font(r, size=24, bold=True, color=GREEN)
        sub = doc.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = sub.add_run("BIT_CD 黑土地遥感变化检测系统\niCAN 大学生创新创业大赛 · 项目开发全流程时间线报告")
        set_run_font(r, size=12, color=MUTED)
        return
    tag = div.find(class_='contest-tag')
    if tag:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para_spacing(p, 20, 14, 1.2)
        r = p.add_run(tag.get_text()); set_run_font(r, size=11, color=GREEN2)
        # top+bottom border like a pill
        pPr = p._element.get_or_add_pPr()
        pbdr = OxmlElement('w:pBdr')
        for edge in ('top', 'bottom'):
            e = OxmlElement('w:' + edge)
            e.set(qn('w:val'), 'single'); e.set(qn('w:sz'), '4')
            e.set(qn('w:space'), '3'); e.set(qn('w:color'), '40916C')
            pbdr.append(e)
        pPr.append(pbdr)
    h1 = div.find('h1')
    if h1:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para_spacing(p, 16, 8, 1.4)
        for line in h1.get_text().split('\n'):
            if line:
                r = p.add_run(line); set_run_font(r, size=22, bold=True, color=DARK)
                r.add_break()
    sub = div.find(class_='subtitle')
    if sub:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para_spacing(p, 4, 10, 1.5)
        for line in sub.get_text().split('\n'):
            r = p.add_run(line); set_run_font(r, size=11.5, color=MUTED)
            r.add_break()
    meta = div.find(class_='meta')
    if meta:
        mtable = meta.find('table')
        if mtable:
            mtbl = doc.add_table(rows=0, cols=2)
            for tr in mtable.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) < 2:
                    continue
                row = mtbl.add_row()
                p0 = row.cells[0].paragraphs[0]; p1 = row.cells[1].paragraphs[0]
                para_spacing(p0, 1, 1, 1.3); para_spacing(p1, 1, 1, 1.3)
                r0 = p0.add_run(tds[0].get_text()); set_run_font(r0, size=10.5, color=MUTED)
                r1 = p1.add_run(tds[1].get_text()); set_run_font(r1, size=10.5, bold=True, color=DARK)
    sp = doc.add_paragraph(); sp.add_run().add_break(WD_BREAK.PAGE)

def render_toc(toc_div):
    h1 = toc_div.find('h1')
    if h1:
        add_heading(h1.get_text(), 1, page_break=False)
    toc = toc_div.find(class_='toc')
    if toc:
        for a in toc.find_all('a'):
            p = doc.add_paragraph()
            para_spacing(p, 2, 2, 1.35)
            b = a.find('b')
            if b:
                r = p.add_run(b.get_text() + "  "); set_run_font(r, size=10.5, bold=True, color=GREEN)
            # remove <b> subtree, render rest
            rest = a.get_text().replace(b.get_text(), "", 1).strip() if b else a.get_text()
            r = p.add_run(rest); set_run_font(r, size=10.5, color=TEXT)
    bp = doc.add_paragraph(); bp.add_run().add_break(WD_BREAK.PAGE)

def render_page(page):
    for node in page.children:
        if not isinstance(node, Tag):
            continue
        cls = node.get('class') or []
        if node.name == 'h1' and 'chapter' in cls:
            chnum = node.find(class_='ch-num')
            text = get_text_skipping(node, chnum) if chnum else node.get_text()
            full = f"{chnum.get_text().strip()}  {text}" if chnum else text
            add_heading(full, 1, page_break=True)
        elif node.name == 'h2':
            add_heading(node.get_text(), 2)
        elif node.name == 'h3':
            add_heading(node.get_text(), 3, color=DARK, size=11.5)
        elif node.name == 'p':
            p = doc.add_paragraph()
            para_spacing(p, 2, 2, 1.3)
            render_inline(p, node)
        elif node.name in ('ul', 'ol'):
            for li in node.find_all('li', recursive=False) or node.find_all('li'):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.5)
                para_spacing(p, 1, 1, 1.3)
                r = p.add_run("• " if node.name == 'ul' else "1. ")
                set_run_font(r, size=10.5, color=GREEN)
                render_inline(p, li)
        elif node.name == 'table':
            render_table(node)
            sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(2)
        elif node.name == 'div':
            if 'timeline' in cls:
                render_timeline(node)
            elif 'cards' in cls:
                render_cards(node)
            elif 'fig-row' in cls:
                figs = node.find_all(class_='fig')
                for i, fig in enumerate(figs):
                    render_fig(fig, fig_size(len(figs)))
            elif 'fig' in cls:
                render_fig(node, fig_size(1))
            elif any(c in CALLOUT_BG for c in cls):
                render_box(node)
            elif 'code' in cls:
                p = doc.add_paragraph()
                para_spacing(p, 2, 2, 1.25)
                r = p.add_run(node.get_text()); set_run_font(r, name=MONO, size=9, color=RGBColor(0x1F, 0x29, 0x37))
                shade_run(r, 'F3F4F6')
            elif 'ref' in cls:
                pass  # handled as ol below

# ---- main ----

soup = BeautifulSoup(HTML_PATH.read_text(encoding='utf-8'), 'html.parser')
body = soup.body
doc = Document()
# default font
style = doc.styles['Normal']
style.font.name = CJK
style.font.size = Pt(10.5)
style._element.rPr.rFonts.set(qn('w:eastAsia'), CJK)

for node in body.children:
    if not isinstance(node, Tag):
        continue
    cls = node.get('class') or []
    if node.name == 'div' and 'cover' in cls:
        # last cover (closing) vs first cover (opening)
        is_first = node is body.find(class_='cover')
        render_cover(node, closing=not is_first)
    elif node.name == 'div' and 'toc' in cls:
        render_toc(node)
    elif node.name == 'div' and ('page' in cls or 'page-break' in cls):
        render_page(node)

doc.save(OUT_PATH)
print(f"DOCX saved: {OUT_PATH}")
print(f"Size: {OUT_PATH.stat().st_size / 1024:.1f} KB")
