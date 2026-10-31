"""前沿资讯：arXiv 论文列表 + 中文摘要缓存。

不联网：`_fetch_arxiv` 和 `chat` 都被替换掉。真正被测的是解析、缓存、
鉴权与「同一篇只花一次 LLM 调用」这几条逻辑。
"""

import pytest

from backend.app.routers import insights

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2410.00001v2</id>
    <published>2026-10-14T00:00:00Z</published>
    <title>Mapping  Cropland
      with Satellites</title>
    <summary>We   study cropland mapping.</summary>
    <author><name>Alice A</name></author>
    <author><name>Bob B</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2410.00001v2"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2410.00002v1</id>
    <published>2026-10-10T00:00:00Z</published>
    <title>Soil Carbon</title>
    <summary>Soil carbon estimation.</summary>
    <author><name>Carol C</name></author>
  </entry>
</feed>
"""


@pytest.fixture(autouse=True)
def fresh_cache():
    """模块级缓存会跨用例串味，每条用例前清掉。"""
    insights._cache.update({"at": 0.0, "items": [], "stale": False})
    yield
    insights._cache.update({"at": 0.0, "items": [], "stale": False})


@pytest.fixture
def fake_arxiv(monkeypatch):
    monkeypatch.setattr(insights, "_fetch_arxiv", lambda: insights._parse_atom(ATOM))


class TestPaperList:
    def test_returns_parsed_items(self, client, fake_arxiv):
        body = client.get("/insights/papers").json()
        items = body["data"]["items"]
        assert len(items) == 2
        first = items[0]
        assert first["id"] == "2410.00001v2"
        # 多行 / 多空白要被压成一行
        assert first["title"] == "Mapping Cropland with Satellites"
        assert first["abstract"] == "We study cropland mapping."
        assert first["published"] == "2026-10-14"
        assert first["authors"] == ["Alice A", "Bob B"]
        assert first["url"].endswith("/abs/2410.00001v2")
        assert first["pdf"].endswith("/pdf/2410.00001v2")

    def test_pdf_falls_back_when_link_missing(self, client, fake_arxiv):
        items = client.get("/insights/papers").json()["data"]["items"]
        assert items[1]["pdf"].endswith("/pdf/2410.00002v1")

    def test_cache_serves_second_call(self, client, monkeypatch):
        calls = {"n": 0}

        def _count():
            calls["n"] += 1
            return insights._parse_atom(ATOM)

        monkeypatch.setattr(insights, "_fetch_arxiv", _count)
        client.get("/insights/papers")
        client.get("/insights/papers")
        assert calls["n"] == 1

    def test_failure_falls_back_to_stale_cache(self, client, monkeypatch):
        monkeypatch.setattr(insights, "_fetch_arxiv", lambda: insights._parse_atom(ATOM))
        client.get("/insights/papers")

        def _boom():
            raise RuntimeError("arXiv 不可达")

        monkeypatch.setattr(insights, "_fetch_arxiv", _boom)
        body = client.get("/insights/papers?refresh=1").json()["data"]
        # 拿不到新的就退回旧的，页面不该突然变空
        assert len(body["items"]) == 2
        assert body["stale"] is True

    def test_failure_without_cache_returns_empty(self, client, monkeypatch):
        def _boom():
            raise RuntimeError("arXiv 不可达")

        monkeypatch.setattr(insights, "_fetch_arxiv", _boom)
        body = client.get("/insights/papers").json()["data"]
        assert body["items"] == []
        assert body["stale"] is True


class TestSummary:
    def test_requires_login(self, client, fake_arxiv):
        resp = client.post("/insights/papers/2410.00001v2/summary")
        assert resp.status_code == 401

    def test_generates_and_caches(self, client, fake_arxiv, auth_headers, monkeypatch):
        calls = {"n": 0}

        def _fake_chat(prompt, history, system_prompt):
            calls["n"] += 1
            return "这是一段中文摘要。"

        monkeypatch.setattr(insights, "chat", _fake_chat)

        first = client.post("/insights/papers/2410.00001v2/summary", headers=auth_headers)
        assert first.status_code == 200
        assert first.json()["data"]["summary"] == "这是一段中文摘要。"
        assert first.json()["data"]["cached"] is False

        second = client.post("/insights/papers/2410.00001v2/summary", headers=auth_headers)
        assert second.json()["data"]["cached"] is True
        # 关键：第二次不能再花钱
        assert calls["n"] == 1

    def test_unknown_paper_is_404(self, client, fake_arxiv, auth_headers):
        resp = client.post("/insights/papers/9999.99999/summary", headers=auth_headers)
        assert resp.status_code == 404

    def test_bad_id_rejected(self, client, fake_arxiv, auth_headers, monkeypatch):
        """带斜杠的 id 连路由都匹配不上（路径参数不含 /），返回 404/405 即可。"""
        monkeypatch.setattr(insights, "chat", lambda *a, **k: "x")
        resp = client.post("/insights/papers/a/b/summary", headers=auth_headers)
        assert resp.status_code in (400, 404, 405)

    def test_llm_failure_is_503(self, client, fake_arxiv, auth_headers, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("LLM 挂了")

        monkeypatch.setattr(insights, "chat", _boom)
        resp = client.post("/insights/papers/2410.00001v2/summary", headers=auth_headers)
        assert resp.status_code == 503
