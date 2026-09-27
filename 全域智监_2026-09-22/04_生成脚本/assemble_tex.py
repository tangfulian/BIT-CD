# -*- coding: utf-8 -*-
"""Assemble tex_parts/*.tex into a single self-contained 项目计划书.tex"""
import pathlib

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
PARTS = BASE / ".claude" / "tex_parts"
OUT = BASE / "项目计划书.tex"

PREAMBLE = r"""% ============================================================
%  基于人工智能的黑土地遥感动态变化监测系统 —— 项目计划书
%  编译方式：xelatex 项目计划书.tex（建议连续编译两次以生成目录）
%
%  图片说明：正文中原图片位置一律以「图片空位」占位，共 27 处，
%            分别对应原文档 image1–image28（image8.emf 原文未引用）。
%  已导出的图片文件位于 ./项目计划书图片/ 目录下。
%
%  替换为真实图片：把整块占位
%      \fbox{\parbox[c][4.5cm][c]{0.8\textwidth}{\centering 【图片空位：imageN.ext】…}}
%      换成
%      \includegraphics[width=0.8\textwidth]{项目计划书图片/imageN.ext}
%  （表格内的占位为 \fbox{\parbox[c][2.2cm][c]{2.6cm}{…}}，
%    换成 \includegraphics[width=2.4cm]{项目计划书图片/imageN.ext}）
%  若需重新排版图号，删除 \setcounter{secnumdepth}{-1} 并保留本节说明即可。
% ============================================================
\documentclass[12pt, a4paper]{ctexart}

\usepackage[top=2.5cm, bottom=2.5cm, left=2.8cm, right=2.8cm, headheight=15pt]{geometry}
\usepackage{graphicx}
\usepackage{float}
\usepackage{array}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{caption}
\usepackage{fancyhdr}
\usepackage{eso-pic}
\usepackage{pdfpages}
\usepackage[hidelinks]{hyperref}

\captionsetup{font=small, labelsep=quad}
\setcounter{secnumdepth}{-1}   % 章节目录编号由正文手写（一、二、…），关闭 LaTeX 自动编号
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{\small 黑土地遥感动态变化监测系统 · 项目计划书}
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0.4pt}

\title{\vspace{-1.2cm}
  {\large\heiti 中国国际大学生创新大赛（2026）}\\[0.5em]
  {\normalsize 赛道：国家级产业赛道　组别：成果转化组}\\[1.4em]
  {\heiti 基于人工智能的黑土地遥感动态变化监测系统}\\[0.4em]
  {\large\heiti 项目计划书（创意策划方案）}}
\author{汤福连 \quad 刘芮仲 \quad 于欣欣 \quad 张珏枫}
\date{\today}

\begin{document}

% ===== 封面（整页一张）：设计稿 + 大赛信息 + 团队成员，与扉页合并为一页 =====
% fitpaper 使该页尺寸与封面 PDF 完全一致；更换封面后请重新运行 .claude/make_cover.py
\includepdf[pages=1, fitpaper=true]{项目计划书图片/封面.pdf}

% ===== 自封面之后的所有页面统一铺淡色背景 =====
% 换浓度只需改文件名：背景淡07.png（最淡）/ 背景淡12.png / 背景淡18.png（纹理最明显）
\AddToShipoutPictureBG{%
  \includegraphics[width=\paperwidth,height=\paperheight]{项目计划书图片/背景淡12.png}%
}

\tableofcontents
\newpage

%%BODY%%

\end{document}
"""

ORDER = ['g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7', 'g8', 'team', 'refs',
         'appendix', 'appendix_b', 'appendix_c']

parts, missing = [], []
for key in ORDER:
    f = PARTS / f"{key}.tex"
    if f.exists() and f.stat().st_size > 0:
        txt = f.read_text(encoding='utf-8').strip()
        parts.append(f"% ==================== 片段 {key} ====================\n{txt}")
    else:
        missing.append(key)

tex = PREAMBLE.replace('%%BODY%%', '\n\n'.join(parts))
OUT.write_text(tex, encoding='utf-8')

print(f"输出: {OUT}")
print(f"大小: {OUT.stat().st_size / 1024:.1f} KB")
print(f"字符数: {len(tex)}")
print(f"已合并片段: {[k for k in ORDER if k not in missing]}")
if missing:
    print(f"缺失片段: {missing}")
