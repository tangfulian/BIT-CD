from sqlalchemy import Column, Integer, String, text

from backend.app.models.database import Base


class GuestUsageDB(Base):
    """游客免费额度的服务端计数，按 (IP, 日期) 一行。

    此前这份额度只存在浏览器 localStorage 里 —— 清一下缓存就归零，直接打
    接口更是完全不受约束。服务端计数之后，前端显示的数字由接口返回，
    不再自己维护一份。

    按天而不是按生命周期：一间教室、一个办公室常常共用出口 IP，
    永久计数会让后来的人一次都试不了。
    """

    __tablename__ = "guest_usage"
    ip = Column(String(64), primary_key=True)
    day = Column(String(10), primary_key=True)
    used = Column(Integer, nullable=False, default=0, server_default=text("0"))
