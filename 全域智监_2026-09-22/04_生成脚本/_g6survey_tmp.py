import io, re, glob

for f in sorted(glob.glob(r'D:/A汤福连的比赛与实验/BIT_CD/.claude/tex_parts/*.tex')):
    s = io.open(f, encoding='utf-8').read()
    print(f)
    print('   fig=', len(re.findall(r'\\begin\{figure\}', s)),
          'tab=', len(re.findall(r'\\begin\{table\}', s)),
          'labels=', re.findall(r'\\label\{([^}]*)\}', s))
    print('   refs=', re.findall(r'\\(?:ref|eqref)\{([^}]*)\}', s))
    print('   asciiDQ=', s.count('"'))
print('=== BIT mentions ===')
for f in sorted(glob.glob(r'D:/A汤福连的比赛与实验/BIT_CD/.claude/tex_parts/*.tex')):
    s = io.open(f, encoding='utf-8').read()
    for m in re.finditer(r'Bipartite|Bitemporal', s):
        print(f, '|', s[max(0, m.start()-40):m.start()+40].replace('\n', ' '))
print('=== 表N / 图N hard references ===')
for f in sorted(glob.glob(r'D:/A汤福连的比赛与实验/BIT_CD/.claude/tex_parts/*.tex')):
    s = io.open(f, encoding='utf-8').read()
    hits = re.findall(r'.{0,12}[图表]\s?\d+.{0,12}', s)
    if hits:
        print(f, hits[:20])
