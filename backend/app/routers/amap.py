import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from backend.app.core.limiter import limiter
from backend.app.schemas.common import RegeoRequest
from backend.app.services.amap_service import ip_geocode, reverse_geocode

router = APIRouter(prefix="/amap", tags=["高德地图"])
logger = logging.getLogger(__name__)


@router.post("/regeo")
@limiter.limit("20/minute")
async def amap_regeo(request: Request, regeo_req: RegeoRequest):
    try:
        data = await reverse_geocode(regeo_req.longitude, regeo_req.latitude)
        return {"code": 200, "data": data}
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="高德API超时")
    except Exception as e:
        logger.exception("高德API调用失败")
        raise HTTPException(status_code=500, detail=f"地址解析异常：{str(e)}")


@router.get("/ip-locate")
@limiter.limit("10/minute")
async def amap_ip_locate(request: Request):
    # Docker 环境下优先取 X-Forwarded-For / X-Real-IP
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP", "")
    )
    if not client_ip:
        client_ip = request.client.host if request.client else ""
    # 过滤非公网 IP（Docker 内部 IP 等），让高德自行判断
    if not client_ip or client_ip.startswith(("172.", "10.", "192.168.", "127.", "0.")):
        client_ip = ""

    try:
        data = await ip_geocode(client_ip)
        return {"code": 200, "data": data}
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="高德API超时")
    except Exception as e:
        logger.exception("IP定位失败")
        raise HTTPException(status_code=500, detail=f"IP定位异常：{str(e)}")
