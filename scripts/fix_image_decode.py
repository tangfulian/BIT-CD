# -*- coding: utf-8 -*-
"""给 detect.py 加统一的图片解码入口，非法图片返回 400 而非裸 500"""
import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")

p = ROOT / 'backend/app/routers/detect.py'
t = p.read_text(encoding='utf-8')

HELPER = '''def _decode_image(data: bytes, name: str = "影像", mode="RGB", size: int = 256):
    """把上传的字节解码为模型输入。

    非法图片此前会抛 UnidentifiedImageError 一路冒到外层，变成客户端无法解析的
    裸 500 文本；这里统一拦截为 400 并给出可读原因。顺带收敛了原先散落在十余处的
    重复解码代码。
    """
    try:
        img = Image.open(BytesIO(data))
        if mode:
            img = img.convert(mode)
        if size:
            img = img.resize((size, size), Image.BILINEAR)
        return img
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{name} 不是有效的图片文件") from exc


'''

anchor = 'def _imwrite(path, img):'
if '_decode_image' not in t:
    t = t.replace(anchor, HELPER + anchor, 1)
    print("✓ 已插入 _decode_image 辅助函数")
else:
    print("· 辅助函数已存在，跳过插入")

SUBS = [
    ('Image.open(BytesIO(img1_bytes)).convert("RGB").resize((256, 256), Image.BILINEAR)',
     '_decode_image(img1_bytes, "T1 影像")'),
    ('Image.open(BytesIO(img2_bytes)).convert("RGB").resize((256, 256), Image.BILINEAR)',
     '_decode_image(img2_bytes, "T2 影像")'),
    ('Image.open(BytesIO(img1_bytes)).convert("L").resize((256, 256))',
     '_decode_image(img1_bytes, "T1 影像", mode="L")'),
    ('Image.open(BytesIO(img2_bytes)).convert("L").resize((256, 256))',
     '_decode_image(img2_bytes, "T2 影像", mode="L")'),
    ('Image.open(BytesIO(img_bytes)).convert("RGB")',
     '_decode_image(img_bytes, "影像", size=0)'),
    ('Image.open(BytesIO(img1_bytes)).convert("RGB")',
     '_decode_image(img1_bytes, "T1 影像", size=0)'),
    ('Image.open(BytesIO(img2_bytes)).convert("RGB")',
     '_decode_image(img2_bytes, "T2 影像", size=0)'),
    ('Image.open(BytesIO(label_bytes)).resize((256, 256), Image.BILINEAR)',
     '_decode_image(label_bytes, "标签影像", mode=None)'),
]
total = 0
for a, b in SUBS:
    n = t.count(a)
    if n:
        t = t.replace(a, b)
        total += n
        print(f"  {n} 处 → {b}")

p.write_text(t, encoding='utf-8')
print(f"共替换 {total} 处")
print(f"残留的裸 Image.open：{t.count('Image.open')}")
