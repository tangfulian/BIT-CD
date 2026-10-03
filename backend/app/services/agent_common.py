"""两条 Agent 通道共用的部分。

浏览器通道（agent_service）与工具通道（tool_agent_service）都用自然语言
驱动系统，提示词里都要列附件清单，响应体也是同一套字段。这些**机械**部分
放这里，各通道**有意不同**的部分（工具名、无附件时的措辞、权限口径、
是否驱动浏览器）留在各自文件里。

判断标准：只抽「改一处就必须同步改另一处、否则会静默漂移」的东西。
措辞不同但结构相同的不算 —— 合并它们只会把两条通道的差异磨平。
"""
import os


def attachment_lines(file_paths: list[str]) -> list[str]:
    """把附件清单拼成提示词里的每行。

    ★ 行格式是**对外契约**：tests/test_agent_tools.py 用正则
      `^\\s{2}(\\S+)\\s+（文件名` 从系统提示里把路径取回来做断言。
      改格式必须同步改那条正则，否则测试会静默失效（取不到路径而崩在
      别处，或者更糟：断言空集合也通过）。

    只给「路径 + 文件名 + 大小」，**不替模型判断哪个是前期、哪个是后期** ——
    那属于用户指令该交代的事，系统替他猜反而会猜错且无从发现。
    """
    lines = []
    for p in file_paths:
        try:
            size = f"{os.path.getsize(p) / 1024:.1f} KB"
        except OSError:
            size = "大小未知"
        lines.append(f"  {p}   （文件名 {os.path.basename(p)}，{size}）")
    return lines
