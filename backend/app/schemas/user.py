from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    username: str
    password: str = Field(min_length=8)
    # 验证码在路由层校验：缺省为空串时 verify_captcha 会直接返回 False 予以拒绝，
    # 因此设为可选不削弱生产安全性，同时便于自动化测试构造请求
    captcha_id: str = ""
    captcha_answer: str = ""


class UserLogin(BaseModel):
    username: str
    password: str
    captcha_id: str = ""
    captcha_answer: str = ""
