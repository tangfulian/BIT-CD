"""首屏与分享卡片。

这里只测后端那一段：`/` 不再由 StaticFiles 直接吐文件，而是先读进来把
`__OG_BASE__` 换成绝对地址再返回。换的理由是分享卡片只认绝对 URL，而把
域名写死在 HTML 里等于把服务器地址提交进仓库。
"""


class TestIndexRoute:
    def test_og_base_is_replaced(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "__OG_BASE__" not in resp.text
        assert 'content="http://testserver/images/og-card.jpg"' in resp.text
        assert 'content="http://testserver/"' in resp.text

    def test_index_html_uses_same_route(self, client):
        """SW 预缓存的是 ./index.html，它也必须拿到替换后的版本。"""
        resp = client.get("/index.html")
        assert resp.status_code == 200
        assert "__OG_BASE__" not in resp.text

    def test_landing_markup_present(self, client):
        body = client.get("/").text
        assert 'id="landingPage"' in body
        assert "images/samples/sample-t1.jpg" not in body  # 影像在 JS 里按需取
        assert 'id="detectSampleBtn"' in body

    def test_static_assets_still_served(self, client):
        """加了 / 路由之后，其余静态文件不能被它挡住。"""
        for path in ("/css/styles.css", "/js/landing.js", "/images/og-card.jpg"):
            assert client.get(path).status_code == 200, path
