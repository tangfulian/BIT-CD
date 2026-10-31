from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

from backend.app.models.database import Base


class PaperSummaryDB(Base):
    """arXiv 论文的中文摘要缓存。

    库里存而不是只在内存里存，是因为每次生成都是一次真实的 LLM 调用 ——
    服务重启、容器重建都不该让我们把同一篇论文再翻译一遍。
    """

    __tablename__ = "paper_summaries"
    arxiv_id = Column(String(64), primary_key=True)
    summary_zh = Column(Text, nullable=False)
    model = Column(String(64))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
