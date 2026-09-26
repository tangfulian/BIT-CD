"""
原始 api.py 兼容入口
请使用: python api.py
或:     uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backend.app.main  # noqa: F401  # ensure module is importable

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000)
