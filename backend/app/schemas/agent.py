from pydantic import BaseModel, Field


class AgentExecuteRequest(BaseModel):
    instruction: str = Field(
        ...,
        description="自然语言指令，例如：用BIT模型检测这两张图，阈值0.3",
        min_length=1,
        max_length=2000,
    )
    max_steps: int = Field(
        default=25,
        ge=5,
        le=100,
        description="Agent 最多执行的浏览器操作步数",
    )


