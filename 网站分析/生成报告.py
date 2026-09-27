# -*- coding: utf-8 -*-
"""由分析原始数据.json 生成可读的分析报告.md"""
import json, pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(__file__).parent
data = json.loads((BASE / "分析原始数据.json").read_text(encoding='utf-8'))['result']
dims, syn = data['dimensions'], data.get('synthesis', {})

L = []
A = L.append

A('# BIT_CD 网站系统分析报告\n')
A('> **分析对象**：BIT_CD 黑土地遥感变化检测系统（FastAPI + 原生 JS SPA）  ')
A('> **分析日期**：2026 年 9 月 26 日  ')
A('> **分析方法**：6 路并行代码审查（后端架构 / 前端质量 / 模型链路 / 安全性 / 文档一致性 / 部署运维）')
A('> + 1 轮交叉核对，共 **127 条发现**  ')
A('> **代码规模**：后端 38 文件 3075 行 · 前端 49 文件 15661 行 · 核心算法 11 文件 1469 行\n')
A('---\n')

A('## 总体评价\n')
A(syn.get('verdict', '') + '\n')
A('---\n')

A('## 一、必须优先处理的 5 个问题\n')
for x in syn.get('top5Priority', []):
    A(f"### {x.get('rank')}. {x.get('title', '')}\n")
    A(f"**为什么**：{x.get('why', '')}\n")
    A(f"**怎么办**：{x.get('action', '')}\n")

A('---\n')
A('## 二、技术亮点（答辩可展示）\n')
for x in syn.get('top5Strengths', []):
    A(f"### {x.get('title', '')}\n")
    A(f"**证据**：{x.get('evidence', '')}\n")
    if x.get('howToPresent'):
        A(f"**怎么讲**：{x['howToPresent']}\n")

A('---\n')
A('## 三、距命题要求的差距\n')
for x in syn.get('gapToTopic', []):
    A(f'- {x}')
A('')

A('---\n')
A('## 四、维度间的结论冲突\n')
for x in syn.get('conflicts', []):
    A(f"### {x.get('topic', '')}\n")
    A(f"- **分歧**：{x.get('views', '')}")
    A(f"- **结论**：{x.get('resolution', '')}\n")

A('---\n')
A('## 五、各维度详细发现\n')
for dim in dims:
    A(f"## {dim['dimension']}\n")
    A(dim['overview'] + '\n')
    if dim.get('metrics'):
        A('**量化指标**')
        for m in dim['metrics']:
            A(f'- {m}')
        A('')
    for f in dim['findings']:
        A(f"### ［{f['kind']}｜{f.get('severity', '—')}］{f['title']}")
        A(f"{f['detail']}\n")
        A(f"> 证据：`{f['evidence']}`")
        if f.get('suggestion'):
            A(f"> 建议：{f['suggestion']}")
        A('')

out = BASE / "分析报告.md"
out.write_text('\n'.join(L), encoding='utf-8')
print(f"已生成 {out.name}")
print(f"行数 {len(L)} | 字符 {len(chr(10).join(L))} | 大小 {out.stat().st_size//1024} KB")
