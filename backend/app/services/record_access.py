"""检测记录与序列的共享访问层。

收敛两样此前各写多份的东西：

  1. 结果 URL 的约定（磁盘路径 / 绝对 URL / 过期 URL 重写）
  2. 「这条记录归不归这个用户」的判定

为什么值得收敛：第 2 条漏掉一次 user_id 过滤就是一次越权，而它此前靠人肉记住；
第 1 条已经开始不一致 —— history.py 重写 URL、series.py 不重写，于是同一份数据
在历史页显示正常、在时序页整片裂图。这种「一半好一半坏」最耗排查时间。

刻意**只收敛判定与构造，不收敛文案**：错误消息各接口本来就不一样（定损说
「缺少概率图」、重调阈值说「无掩膜」、查记录说「记录不存在」），把它们统一会
破坏既有契约与锁死这些文案的测试。所以本模块的函数返回 None 或 Query，
由调用方决定抛什么、说什么。
"""
from sqlalchemy.orm import Session

from backend.app.models.detection import DetectionResultDB
from backend.app.models.series import ImageSeriesDB

RESULTS_DIR = "results"


# ---- 结果 URL 的约定 ----

def result_url(base_url: str, filename: str) -> str:
    """把结果文件名拼成绝对地址。base_url 由调用方传入 —— 进程内调用没有 Request。"""
    return f"{base_url.rstrip('/')}/{RESULTS_DIR}/{filename}"


def rewrite_url(base_url: str, url: str | None) -> str:
    """把库里可能存着旧域名的 URL 重写为当前地址。

    数据库里存的是**检测当时**的绝对地址。服务器换过域名/IP、或曾经用
    127.0.0.1 访问过，旧记录里就是过期主机名 —— 不重写就会裂图。
    """
    if not url:
        return ""
    filename = url.rsplit("/", 1)[-1]
    if not filename:
        return url
    return result_url(base_url, filename)


def url_to_path(url: str) -> str:
    """从结果 URL 提取磁盘相对路径。"""
    return f"{RESULTS_DIR}/{url.rsplit('/', 1)[-1]}"


# ---- 归属判定 ----

def find_owned_detection(
    db: Session, user_id: int, detection_id: int
) -> DetectionResultDB | None:
    """按 id + 所属用户取检测记录，取不到返回 None。

    谓词里同时带 id 与 user_id 是刻意的：分两步（先取出再在 Python 里比）
    很容易在某个分支漏掉比较，而这里漏一次就是一次越权。
    """
    return (
        db.query(DetectionResultDB)
        .filter(
            DetectionResultDB.id == detection_id,
            DetectionResultDB.user_id == user_id,
        )
        .first()
    )


def find_owned_series(db: Session, user_id: int, series_id: int) -> ImageSeriesDB | None:
    """按 id + 所属用户取序列，取不到返回 None。"""
    return (
        db.query(ImageSeriesDB)
        .filter(
            ImageSeriesDB.id == series_id,
            ImageSeriesDB.user_id == user_id,
        )
        .first()
    )


def query_owned_records(
    db: Session, user_id: int, *, is_admin: bool = False, model: str | None = None
):
    """构造「该用户可见的检测记录」查询，调用方自行 order_by / 分页。

    is_admin 显式传入且**默认 False**：管理员旁路由此从「查询的隐藏属性」
    变成「调用方的一次明确表态」。

    这一点在本项目里不是洁癖：Agent 通道历史上正是以 admin 身份运行的，
    只要有一条查询默认放行，模型就能拿到全库所有用户的数据。工具层一律
    传 False（它连这个参数都不暴露），HTTP 侧才传真实角色。
    """
    query = db.query(DetectionResultDB)
    if not is_admin:
        query = query.filter(DetectionResultDB.user_id == user_id)
    if model:
        query = query.filter(DetectionResultDB.model == model)
    return query
