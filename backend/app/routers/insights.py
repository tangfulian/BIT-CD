"""前沿资讯：arXiv 上的农业遥感新论文。

为什么只有 arXiv：国内没有一个农业遥感站点提供稳定的开放接口。实测
农科院 caas.cn 直接返回 418 拦爬虫，国家遥感中心 nrscc.most.cn 连不上，
遥感学报 jors.cn 没有订阅源，农业信息网的 /rss 是 404。抓门户 HTML 也能做，
但结构一改就坏，还有版权问题。arXiv 是唯一能拿到结构化「最新」数据、
且明确提供 API 的来源。

两处缓存，作用不同：
- 列表缓存在内存里（6 小时）。arXiv 不该被每次翻页都打一下。
- 中文摘要缓存在数据库里。每次生成都是一次真实的 LLM 调用，重启不该重花。
"""

import logging
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.core.limiter import limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.paper import PaperSummaryDB
from backend.app.models.user import UserDB
from backend.app.services.ai_service import chat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/insights", tags=["前沿资讯"])

ARXIV_API = "https://export.arxiv.org/api/query"
# arXiv 的 abs: 字段上做布尔组合。别加太多词 —— 每多一个 OR 就多一批
# 只沾边的论文，「土壤湿度传感器」这种也会混进来。
SEARCH_QUERY = (
    'abs:"remote sensing" AND '
    "(abs:agriculture OR abs:crop OR abs:cropland OR abs:farmland OR abs:soil)"
)
MAX_RESULTS = 24
CACHE_TTL = 6 * 3600

_NS = {"a": "http://www.w3.org/2005/Atom"}
_cache: dict = {"at": 0.0, "items": [], "stale": False}
_lock = threading.Lock()

SUMMARY_SYSTEM_PROMPT = (
    "你是一位遥感领域的论文导读助手，要把一篇英文论文的摘要压缩成"
    "2 到 3 句中文。约束：\n"
    "1. 只使用给定的标题与摘要里出现的信息，禁止补充你没看到的结论、"
    "数据集名称、数字或作者观点。\n"
    "2. 摘要里没写清楚的，就说「摘要未说明」，不要猜。\n"
    "3. 不要评价论文好坏，不要写「本文具有重要意义」这类空话。\n"
    "4. 只输出纯文本中文，不要 Markdown、不要标题、不要分点，150 字以内。"
)


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _parse_atom(xml_text: str) -> list:
    root = ET.fromstring(xml_text)
    items = []
    for entry in root.findall("a:entry", _NS):
        raw_id = entry.findtext("a:id", "", _NS) or ""
        # http://arxiv.org/abs/2410.01234v1 -> 2410.01234v1
        arxiv_id = raw_id.rsplit("/abs/", 1)[-1].strip()
        if not arxiv_id:
            continue
        pdf = ""
        for link in entry.findall("a:link", _NS):
            if link.get("title") == "pdf":
                pdf = link.get("href", "")
                break
        items.append(
            {
                "id": arxiv_id,
                "title": _clean(entry.findtext("a:title", "", _NS)),
                "abstract": _clean(entry.findtext("a:summary", "", _NS)),
                "published": (entry.findtext("a:published", "", _NS) or "")[:10],
                "authors": [
                    _clean(a.findtext("a:name", "", _NS))
                    for a in entry.findall("a:author", _NS)[:4]
                ],
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf": pdf or f"https://arxiv.org/pdf/{arxiv_id}",
            }
        )
    return items


def _fetch_arxiv() -> list:
    params = {
        "search_query": SEARCH_QUERY,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(MAX_RESULTS),
    }
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        resp = client.get(ARXIV_API, params=params)
    if resp.status_code != 200:
        raise RuntimeError(f"arXiv 返回 {resp.status_code}")
    return _parse_atom(resp.text)


def _get_items(force: bool = False) -> dict:
    """返回 {items, fetched_at, stale}。任何失败都退回上一次的缓存。"""
    now = time.time()
    with _lock:
        fresh = _cache["items"] and (now - _cache["at"] < CACHE_TTL)
        if fresh and not force:
            return _cache
        try:
            items = _fetch_arxiv()
        except Exception as e:  # noqa: BLE001
            logger.warning("拉取 arXiv 失败: %s", e)
            # 拿不到就用旧的，别让页面变空；一次都没成功过才返回空列表
            return {**_cache, "stale": True}
        _cache.update({"at": now, "items": items, "stale": False})
        return _cache


@router.get("/papers")
@limiter.limit("20/minute")
def list_papers(request: Request, refresh: bool = False):
    data = _get_items(force=refresh)
    return {
        "code": 200,
        "data": {
            "items": data["items"],
            "stale": data["stale"],
            "source": "arXiv",
            "fetched_at": (
                datetime.fromtimestamp(data["at"], timezone.utc).isoformat()
                if data["at"]
                else None
            ),
        },
    }


@router.post("/papers/{arxiv_id}/summary")
@limiter.limit("10/minute")
def summarize(
    request: Request,
    arxiv_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    """生成（或取回）一篇论文的中文摘要。

    要登录：这是一次真实付费的 LLM 调用，游客可以免费用 3 次检测，
    但不应无限次消耗 LLM 额度。
    """
    arxiv_id = arxiv_id.strip()[:64]
    if not arxiv_id or "/" in arxiv_id:
        raise HTTPException(status_code=400, detail="论文标识不合法")

    cached = db.query(PaperSummaryDB).filter(PaperSummaryDB.arxiv_id == arxiv_id).first()
    if cached:
        return {"code": 200, "data": {"summary": cached.summary_zh, "cached": True}}

    paper = next((p for p in _get_items()["items"] if p["id"] == arxiv_id), None)
    if not paper:
        raise HTTPException(status_code=404, detail="缓存里没有这篇论文，请刷新列表后重试")

    prompt = f"标题：{paper['title']}\n\n摘要原文：\n{paper['abstract']}"
    try:
        text = chat(prompt, [], SUMMARY_SYSTEM_PROMPT).strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("生成中文摘要失败: %s", e)
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后再试")
    if not text:
        raise HTTPException(status_code=503, detail="AI 返回为空，请稍后再试")

    db.add(PaperSummaryDB(arxiv_id=arxiv_id, summary_zh=text, model="llm"))
    db.commit()
    logger.info("生成论文摘要: %s (%s)", arxiv_id, current_user.username)
    return {"code": 200, "data": {"summary": text, "cached": False}}
