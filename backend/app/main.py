"""API 進入點。階段 1 只提供 /health，用來確認 api 與資料庫都正常。"""

import os

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="rag-knowledge-assistant")


@app.get("/health")
def health():
    try:
        # connect_timeout：資料庫沒回應時 3 秒就放棄，不讓請求一直卡住。
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
            row = conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
    except psycopg.Error as e:
        # 503 = 服務暫時無法使用。讓監控工具或使用者一看就知道是資料庫出問題。
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unreachable", "detail": str(e)},
        )

    return {
        "status": "ok",
        "database": "ok",
        # 沒抓到版本代表 pgvector 沒啟用（例如 db/init 沒被執行）。
        "pgvector": row[0] if row else None,
    }
