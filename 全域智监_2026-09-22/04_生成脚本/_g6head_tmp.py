import io, re, glob
for f in sorted(glob.glob(r'D:/A汤福连的比赛与实验/BIT_CD/.claude/tex_parts/g*.tex')):
    s = io.open(f, encoding='utf-8').read()
    print(f, re.findall(r'\\(?:sub)?section\{[^}]*\}', s))
