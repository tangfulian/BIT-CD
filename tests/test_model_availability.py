"""模型可用性、NDVI 近似标注、融合图重建三处修复的回归测试。

这三条都源自同一类问题：系统对外呈现的能力与它实际能做的事不一致。
"""
import os
import tempfile

import numpy as np
import pytest
from PIL import Image

from backend.app.services.detect_service import (
    calc_ndvi,
    is_model_available,
    model_availability,
    rebuild_fusion_from_score,
    save_score_map,
)

# 注册表里登记、但仓库不随附权重的模型。它们必须被如实报成不可用，
# 否则前端会把跑不出结果的选项摆给用户。
UNSHIPPED = ["FC_SIAM_DIFF", "SNUNET", "CHANGEFORMER"]
SHIPPED = ["BIT", "DIFF", "AFCF3D", "BIT_LuojiaSET"]


def _fake_image(size=(32, 32), mode="RGB"):
    arr = (np.random.default_rng(0).random((size[1], size[0], 3)) * 255).astype(np.uint8)
    if mode == "RGBA":
        arr = np.dstack([arr, np.full(size[::-1], 255, np.uint8)])
    img = Image.fromarray(arr, mode)
    buf = tempfile.SpooledTemporaryFile()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


class TestModelAvailability:
    def test_shipped_models_are_available(self):
        for m in SHIPPED:
            assert is_model_available(m) is True, f"{m} 有权重却报不可用"

    def test_unshipped_models_report_unavailable(self):
        for m in UNSHIPPED:
            assert is_model_available(m) is False, f"{m} 无权重却报可用"

    def test_unknown_model_is_unavailable(self):
        assert is_model_available("NO_SUCH_MODEL") is False

    def test_availability_covers_whole_registry(self):
        from backend.app.core.config import MODEL_CONFIGS

        assert set(model_availability()) == set(MODEL_CONFIGS)

    def test_endpoint_lists_available(self, client):
        resp = client.get("/detect/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert set(data["available"]) == set(SHIPPED)
        # 每个模型都要给出可用性与原因，前端才能如实渲染
        for entry in data["models"]:
            assert set(entry) == {"name", "available", "reason"}

    def test_error_message_names_alternatives(self):
        from backend.app.services.detect_service import ModelNotAvailableError

        exc = ModelNotAvailableError("SNUNET", "/tmp/nope.pt")
        assert "BIT" in str(exc), "503 提示应告诉用户当前能用什么"


class TestNDVIAcceptsBands:
    def test_rgb_is_flagged_approximate(self):
        result = calc_ndvi(Image.fromarray(
            (np.random.default_rng(0).random((16, 16, 3)) * 255).astype(np.uint8)
        ))
        assert result["approximate"] is True
        assert result["nir_source"] == "blue_proxy"
        assert result["n_bands"] == 3
        assert result["note"]

    def test_alpha_channel_is_not_mistaken_for_nir(self):
        """RGBA 的第 4 通道是透明度，不是近红外——不能据此宣称真 NDVI。"""
        base = (np.random.default_rng(0).random((16, 16, 3)) * 255).astype(np.uint8)
        rgba = np.dstack([base, np.full((16, 16), 255, np.uint8)])
        result = calc_ndvi(Image.fromarray(rgba, "RGBA"))
        assert result["approximate"] is True
        assert result["nir_source"] == "blue_proxy"

    def test_endpoint_reports_approximate(self, client):
        resp = client.post(
            "/detect/ndvi",
            files=[("img", ("a.png", _fake_image(), "image/png"))],
        )
        assert resp.status_code == 200
        ndvi = resp.json()["ndvi"]
        assert ndvi["approximate"] is True
        assert "classification" in ndvi

    def test_grayscale_does_not_crash(self, client):
        """单波段输入不足 3 波，应回退为 RGB 而不是索引越界。"""
        img = Image.fromarray((np.random.default_rng(0).random((16, 16)) * 255).astype(np.uint8), "L")
        buf = tempfile.SpooledTemporaryFile()
        img.save(buf, format="PNG")
        buf.seek(0)
        resp = client.post("/detect/ndvi", files=[("img", ("g.png", buf.read(), "image/png"))])
        assert resp.status_code == 200
        assert resp.json()["ndvi"]["approximate"] is True


class TestFusionRebuild:
    def test_rebuilds_when_t2_present(self):
        d = tempfile.mkdtemp()
        score_path = os.path.join(d, "abc_score.png")
        save_score_map(np.random.default_rng(0).random((64, 64)).astype(np.float32), score_path)
        Image.fromarray(
            (np.random.default_rng(1).random((64, 64, 3)) * 255).astype(np.uint8)
        ).save(os.path.join(d, "abc_t2.png"))

        mask = (np.random.default_rng(2).random((64, 64)) > 0.7).astype(np.uint8) * 255
        fusion = rebuild_fusion_from_score(score_path, mask)
        assert fusion is not None
        assert fusion.shape == (64, 64, 3)

    def test_returns_none_without_t2(self):
        """早期记录没存 T2。此时必须返回 None，绝不能回退到旧融合图——
        那会与新生成的掩膜自相矛盾。"""
        d = tempfile.mkdtemp()
        score_path = os.path.join(d, "abc_score.png")
        save_score_map(np.random.default_rng(0).random((64, 64)).astype(np.float32), score_path)
        mask = np.zeros((64, 64), np.uint8)
        assert rebuild_fusion_from_score(score_path, mask) is None

    def test_detect_persists_t2(self, client, auth_headers):
        """新检测必须留下 T2，否则重调阈值时融合图永远重建不出来。

        T2 与 score/mask 共用 {uid} 前缀，rebuild_fusion_from_score 正是
        靠这个命名约定从 score_url 推出 T2 路径，所以这里断言的是文件名。
        """
        resp = client.post(
            "/detect",
            files=[
                ("img1", ("t1.png", _fake_image(), "image/png")),
                ("img2", ("t2.png", _fake_image(), "image/png")),
            ],
            data={"model": "DIFF", "threshold": 0.5},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        results = resp.json()
        uid = os.path.basename(results["mask"]).split("_mask")[0]
        assert os.path.exists(os.path.join("results", f"{uid}_t2.png")), \
            "检测未保存 T2，重调阈值的融合图将无法重建"
        os.remove(os.path.join("results", f"{uid}_t2.png"))


class TestRethresholdFusion:
    """重调阈值后融合图必须跟着更新。

    此前 _make_fusion_for_detection 是个 return None 的空桩，于是调完阈值
    掩膜变了、融合图还是旧的，两张图并列展示却互相矛盾。
    """

    def _detect(self, client, auth_headers):
        """跑一次检测，返回 (detection_id, uid)。uid 是结果文件名的公共前缀。"""
        resp = client.post(
            "/detect",
            files=[
                ("img1", ("t1.png", _fake_image(), "image/png")),
                ("img2", ("t2.png", _fake_image(), "image/png")),
            ],
            data={"model": "DIFF", "threshold": 0.5},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        return body["detection_id"], os.path.basename(body["mask"]).split("_mask")[0]

    def _rethreshold(self, client, auth_headers, detection_id, threshold):
        return client.post(
            "/detect/rethreshold",
            data={"detection_id": detection_id, "threshold": threshold},
            headers=auth_headers,
        )

    def test_rethreshold_returns_fresh_fusion(self, client, auth_headers):
        detection_id, _ = self._detect(client, auth_headers)
        body = self._rethreshold(client, auth_headers, detection_id, 0.8).json()
        assert body["code"] == 200
        assert body["fusion"], "重调阈值后融合图仍为空——空桩问题回归了"
        assert "rethresh_" in body["fusion"]

    def test_rethreshold_nulls_fusion_when_t2_missing(self, client, auth_headers):
        """旧记录没有 T2。此时应把融合图置空，而不是留着过期的旧图。"""
        detection_id, uid = self._detect(client, auth_headers)
        self._rethreshold(client, auth_headers, detection_id, 0.5)
        # 只删本次检测自己留下的那份 T2，不动 results/ 里的其他文件
        os.remove(os.path.join("results", f"{uid}_t2.png"))
        body = self._rethreshold(client, auth_headers, detection_id, 0.7).json()
        assert body["code"] == 200
        assert body["fusion"] in (None, ""), \
            "T2 缺失时不应继续返回过期的融合图"
