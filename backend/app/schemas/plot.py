from typing import Optional

from pydantic import BaseModel


class PlotCreate(BaseModel):
    name: str
    province: str = ""
    city: str = ""
    lat_lng: str = ""
    area: float = 0
    land_type: str = ""
    crop_type: str = ""
    data_source: str = ""
    change_type: str = "黑土层变薄退化"
    t1_time: str = ""
    t2_time: str = ""


class PlotUpdate(BaseModel):
    name: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    lat_lng: Optional[str] = None
    area: Optional[float] = None
    land_type: Optional[str] = None
    crop_type: Optional[str] = None
    data_source: Optional[str] = None
    change_type: Optional[str] = None
    t1_time: Optional[str] = None
    t2_time: Optional[str] = None


class PlotOut(BaseModel):
    id: int
    name: str
    province: str
    city: str
    lat_lng: str
    area: float
    land_type: str
    crop_type: str
    data_source: str
    change_type: str
    t1_time: str
    t2_time: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True
