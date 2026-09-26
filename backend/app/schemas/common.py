from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_input: str
    history: list = []


class RegeoRequest(BaseModel):
    longitude: float
    latitude: float
