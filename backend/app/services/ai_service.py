import json
import logging
import re

import dashscope
from dashscope import Generation

from backend.app.core.config import DASHSCOPE_API_KEY

dashscope.api_key = DASHSCOPE_API_KEY
logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM_PROMPT = (
    "你是东北黑土地变化检测领域的专家。你的任务是分析遥感变化检测数据，"
    "判断该地块的核心变化类型。你必须从以下类别中选择最匹配的一个：\n"
    "1. 水蚀沟壑发育 - 线状/沟状侵蚀特征，沿坡面发育\n"
    "2. 风蚀沙化 - 片状/斑块状退化，地表沙化裸露\n"
    "3. 耕地撂荒 - 大面积植被减少、裸土增加，无耕作痕迹\n"
    "4. 耕地非农化（建房/建厂）- 规则几何形状的人造结构出现\n"
    "5. 耕地非粮化（种树/挖塘）- 植被类型改变，出现林地或水体斑块\n"
    "6. 黑土层变薄退化 - 渐进式、均匀的有机质流失，无明显沟蚀或沙化\n"
    "仅返回JSON格式，不要其他内容："
    '{"change_type": "类别名", "confidence": 0.0-1.0, "reasoning": "简短理由（50字内）"}'
)


def chat(user_input: str, history: list, system_prompt: str) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})
    response = Generation.call(
        model=Generation.Models.qwen_turbo,
        messages=messages,
        result_format="message",
        stream=False,
        temperature=0.3,
    )
    if response.status_code == 200:
        if response.output.choices:
            return response.output.choices[0].message.content
        raise Exception("AI返回了空响应")
    raise Exception(f"AI调用失败：{response.message}")


def classify_change(
    change_ratio: float,
    change_pixel: int,
    total_pixel: int,
    threshold: float,
    location: str = "",
    land_type: str = "",
    crop_type: str = "",
    t1_time: str = "",
    t2_time: str = "",
) -> dict:
    """调用 DashScope qwen_turbo 根据检测统计数据和元数据分类变化类型。"""
    user_prompt = (
        f"请根据以下检测数据判断变化类型：\n"
        f"- 地块位置：{location or '未知'}\n"
        f"- 耕地类型：{land_type or '未知'}\n"
        f"- 种植作物：{crop_type or '未知'}\n"
        f"- T1时相：{t1_time or '未知'}，T2时相：{t2_time or '未知'}\n"
        f"- 变化比例：{change_ratio}%（变化像素 {change_pixel}/{total_pixel}）\n"
        f"- 检测阈值：{threshold}\n"
        f"请基于上述数据推断最可能的变化类型，返回JSON。"
    )
    try:
        response = Generation.call(
            model=Generation.Models.qwen_turbo,
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            result_format="message",
            stream=False,
            temperature=0.1,
        )
        if response.status_code == 200:
            if not response.output.choices:
                raise Exception("AI返回了空响应")
            text = response.output.choices[0].message.content
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
        raise Exception(f"AI响应解析失败：{response.message if hasattr(response, 'message') else '未知错误'}")
    except json.JSONDecodeError:
        raise Exception("AI返回的JSON格式无效")
    except Exception:
        raise
