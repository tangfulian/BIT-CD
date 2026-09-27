import io, re

A = io.open(r'D:/A汤福连的比赛与实验/BIT_CD/.claude/tex_parts_backup/g6.tex', encoding='utf-8').read()
B = io.open(r'D:/A汤福连的比赛与实验/BIT_CD/.claude/tex_parts/g6.tex', encoding='utf-8').read()

def norm(s):
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = re.sub(r'\s+', '', s)
    return s

na, nb = norm(A), norm(B)

# paragraph-level containment
paras = [p for p in re.split(r'\n\s*\n', A) if p.strip()]
out = []
missing = []
for i, p in enumerate(paras):
    np_ = norm(p)
    if np_ in nb:
        out.append('OK   p%02d len=%d' % (i, len(np_)))
    else:
        # try sentence-level
        sents = [x for x in re.split(r'(?<=[\u3002\uff1b])', p) if norm(x)]
        miss = [x for x in sents if norm(x) not in nb]
        missing.append((i, len(np_), len(miss), len(sents)))
        out.append('MISS p%02d len=%d missing_sents=%d/%d' % (i, len(np_), len(miss), len(sents)))
        for m in miss:
            out.append('      -> ' + m[:110])

print('\n'.join(out))
print('---- paragraphs:', len(paras))
print('---- norm len A=%d B=%d' % (len(na), len(nb)))
print('---- ASCII DQ in A=%d B=%d' % (A.count('"'), B.count('"')))
print('---- placeholders A=%d B=%d' % (A.count('\u3010\u56fe\u7247\u7a7a\u4f4d'), B.count('\u3010\u56fe\u7247\u7a7a\u4f4d')))
print('---- figenv A=%d B=%d' % (len(re.findall(r'\\begin\{figure\}', A)), len(re.findall(r'\\begin\{figure\}', B))))
print('---- caption A:', re.findall(r'\\caption\{([^}]*)\}', A))
print('---- caption B:', re.findall(r'\\caption\{([^}]*)\}', B))
print('---- cn A=%d B=%d' % (len(re.findall(r'[\u4e00-\u9fff]', A)), len(re.findall(r'[\u4e00-\u9fff]', B))))
print('---- numbers in B:', re.findall(r'[0-9]+(?:\.[0-9]+)?%?', B))
print('---- numbers in A:', re.findall(r'[0-9]+(?:\.[0-9]+)?%?', A))
