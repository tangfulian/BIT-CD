import json
import logging
import re

import httpx

from backend.app.core import llm_budget
from backend.app.core.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

# 走服务商的 OpenAI 兼容端点，不绑定任何专有 SDK。
#
# 此前走原生 dashscope SDK 的 Generation.call，它把请求固定发往
# /api/v1/services/aigc/text-generation/generation 这个 legacy 路径。
# 实测该路径只服务 qwen-turbo / qwen-plus 这类老模型：换成 Qwen3.7 系列后
# 一律返回 400 "url error"。而 qwen-turbo 本身就在 2026-10-10 的下线名单上，
# 也就是说这条路径没有未来。改走兼容端点，与 agent_service 统一 ——
# 这个决定现在有了第二个好处：换服务商只是改 .env。
#
# 服务商、密钥、模型全部来自 config（默认 DeepSeek）。
_LLM_CHAT_URL = LLM_BASE_URL.rstrip("/") + "/chat/completions"

_AI_MODEL = LLM_MODEL
_AI_TIMEOUT = 90.0
_AI_MAX_TOKENS = 2048

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


def _chat_completion(messages: list, temperature: float, max_tokens: int = _AI_MAX_TOKENS) -> str:
    """调用兼容端点，返回首个 choice 的文本内容。

    原本由 dashscope SDK 兜的三种失败——未配置 key、非 200、空响应——
    在这里显式处理，错误信息保持可读。
    """
    if not LLM_API_KEY:
        raise Exception("未配置 LLM_API_KEY，AI 功能不可用")
    # 日预算闸。放在发请求之前 —— 超预算的那一次不该被发出去。
    llm_budget.spend()

    try:
        resp = httpx.post(
            _LLM_CHAT_URL,
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": _AI_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=_AI_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise Exception(f"AI调用失败：{type(exc).__name__}: {exc}") from exc

    if resp.status_code != 200:
        # 截断响应体：模型下线后报的是 403 access_denied，且文案里不含
        # 「已下线」字样，把原始报文带出来才有可能定位。
        raise Exception(f"AI调用失败：HTTP {resp.status_code} {resp.text[:200]}")

    try:
        choices = resp.json().get("choices") or []
    except ValueError as exc:
        raise Exception("AI返回的不是合法 JSON") from exc
    if not choices:
        raise Exception("AI返回了空响应")

    content = (choices[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise Exception("AI返回了空响应")
    return content


def chat(user_input: str, history: list, system_prompt: str) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})
    return _chat_completion(messages, temperature=0.3)


DISASTER_DRAFT_SYSTEM_PROMPT = (
    "你是农业保险遥感定损的辅助写作助手，负责把一份已算好的定损参数表改写成"
    "《定损说明（草稿）》。以下约束任何一条都不得违反：\n"
    "1. 只能使用用户给出的数值，禁止引入任何未给出的数字、地名、机构或政策条款。\n"
    "2. 你没有收到任何影像，也不具备看图能力。禁止出现"
    "“从影像可见”“图中显示”“目视判读”之类暗示你看过影像的表述。\n"
    "3. 不要给出确定性结论或赔付结论；涉及金额与等级一律写成“按当前参数测算”。\n"
    "4. 减产比例、亩产、单价均为假设参数，必须说明是假设而非实测。\n"
    "5. 结尾必须独立成行输出：【AI 草稿，需人工复核；不作为理赔依据。】\n"
    "6. 只输出纯文本，不要 Markdown 标题符号、表格、代码块或 JSON，字数 300 以内。"
)


def draft_disaster_note(payload: str) -> str:
    """生成定损说明草稿。

    刻意走本模块的 chat() 而不是自己再写一遍 Generation.call：
    一来复用它的空响应/非 200 处理，二来模块内按全局名调用 chat，
    测试对 ai_service.chat 的 monkeypatch 才能生效，否则测试会真的打网络。
    """
    return chat(payload, [], DISASTER_DRAFT_SYSTEM_PROMPT)


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
    """根据检测统计数据和元数据分类变化类型。模型见 _AI_MODEL。"""
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
        text = _chat_completion(
            [
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise Exception(f"AI响应解析失败：模型未按要求返回 JSON，原文片段 {text[:120]}")
        return json.loads(match.group())
    except json.JSONDecodeError:
        raise Exception("AI返回的JSON格式无效")
