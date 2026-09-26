import base64
import io
import random
import string
import time
import uuid
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter


_store: Dict[str, Tuple[str, float]] = {}  # captcha_id -> (answer, expires_at)
TTL = 300  # 5 分钟有效


def _clean_expired() -> None:
    now = time.time()
    expired = [kid for kid, (_, exp) in _store.items() if now > exp]
    for kid in expired:
        del _store[kid]


def _random_text(length: int = 4) -> str:
    chars = string.ascii_uppercase + string.digits
    # 去掉容易混淆的字符
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "").replace("L", "")
    return "".join(random.choices(chars, k=length))


def _random_color(min_val: int = 0, max_val: int = 120) -> Tuple[int, int, int]:
    return (random.randint(min_val, max_val),
            random.randint(min_val, max_val),
            random.randint(min_val, max_val))


def _generate_image(text: str) -> bytes:
    width, height = 160, 56
    img = Image.new("RGB", (width, height), color=(245, 248, 250))
    draw = ImageDraw.Draw(img)

    # 背景干扰点
    for _ in range(40):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=_random_color(180, 230))

    # 干扰线
    for _ in range(1):
        x1 = random.randint(0, width // 3)
        y1 = random.randint(0, height)
        x2 = random.randint(width * 2 // 3, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=_random_color(150, 220), width=1)

    # 文字
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        except (IOError, OSError):
            font = ImageFont.load_default()

    for i, ch in enumerate(text):
        x = 10 + i * 34 + random.randint(-3, 3)
        y = random.randint(4, 10)
        color = _random_color(10, 80)
        char_img = Image.new("RGBA", (40, 44), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((2, 2), ch, fill=color, font=font)
        char_img = char_img.rotate(random.randint(-15, 15), expand=False,
                                   fillcolor=(0, 0, 0, 0))
        img.paste(char_img, (x, y), char_img)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_captcha() -> dict:
    _clean_expired()
    captcha_id = uuid.uuid4().hex
    text = _random_text(4)
    img_bytes = _generate_image(text)
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    _store[captcha_id] = (text, time.time() + TTL)
    return {
        "captcha_id": captcha_id,
        "captcha_image": f"data:image/png;base64,{b64}",
    }


def verify_captcha(captcha_id: str, answer: str) -> bool:
    _clean_expired()
    entry = _store.get(captcha_id)
    if entry is None:
        return False
    stored_answer, expires = entry
    if time.time() > expires:
        del _store[captcha_id]
        return False
    # 验证后立即删除，防止重复使用
    del _store[captcha_id]
    return answer.upper().strip() == stored_answer.upper()
