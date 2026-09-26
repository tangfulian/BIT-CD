import httpx
from fastapi import HTTPException

from backend.app.core.config import AMAP_API_BASE, AMAP_WEB_KEY


async def reverse_geocode(longitude: float, latitude: float) -> dict:
    if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
        raise HTTPException(status_code=400, detail="经纬度错误")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{AMAP_API_BASE}/geocode/regeo",
            params={
                "key": AMAP_WEB_KEY,
                "location": f"{longitude},{latitude}",
                "extensions": "base",
                "output": "json",
            },
        )
        result = r.json()
        if result.get("status") != "1":
            raise HTTPException(status_code=500, detail=f"地址解析失败：{result.get('info', '')}")

        addr = result["regeocode"]["addressComponent"]
        return {
            "province": addr.get("province", ""),
            "city": addr.get("city", addr.get("district", "")),
            "district": addr.get("district", ""),
            "formatted_address": result["regeocode"].get("formatted_address", ""),
        }


async def ip_geocode(client_ip: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{AMAP_API_BASE}/ip",
            params={"key": AMAP_WEB_KEY, "ip": client_ip, "output": "json"},
        )
        result = r.json()
        if result.get("status") != "1":
            raise HTTPException(status_code=500, detail=f"IP定位失败：{result.get('info', '')}")

        rectangle = result.get("rectangle", "")
        lng, lat = None, None
        if rectangle and ";" in rectangle:
            parts = rectangle.split(";")
            if len(parts) == 2:
                try:
                    leftBottom = [float(x) for x in parts[0].split(",")]
                    rightTop = [float(x) for x in parts[1].split(",")]
                    lng = round((leftBottom[0] + rightTop[0]) / 2, 6)
                    lat = round((leftBottom[1] + rightTop[1]) / 2, 6)
                except (ValueError, IndexError):
                    pass

        return {
            "province": result.get("province", ""),
            "city": result.get("city", ""),
            "adcode": result.get("adcode", ""),
            "longitude": lng,
            "latitude": lat,
            "rectangle": rectangle,
        }
