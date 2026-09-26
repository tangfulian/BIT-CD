from pydantic import BaseModel


class DetectAIAnalysisRequest(BaseModel):
    change_area_ratio: float
    change_pixel: int
    total_pixel: int
    threshold: float
    change_type: str
    t1_time: str
    t2_time: str
    province: str
    city: str
    lat_lng: str
    area: str
    land_type: str
    crop_type: str
    data_source: str
    location: str


class ClassifyChangeRequest(BaseModel):
    mask_base64: str = ""
    t1_base64: str = ""
    t2_base64: str = ""
    change_ratio: float
    change_pixel: int
    total_pixel: int
    threshold: float
    location: str = ""
    lat_lng: str = ""
    land_type: str = ""
    crop_type: str = ""
    t1_time: str = ""
    t2_time: str = ""
    detection_id: int = 0


class UpdateChangeTypeRequest(BaseModel):
    detection_id: int
    change_type: str


class AnnotationSaveRequest(BaseModel):
    annotation_data: str  # base64 PNG of corrected mask
