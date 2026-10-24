"""API 進入點。階段 1 只提供 /health，用來確認 api 與資料庫都正常。"""

import logging
import os

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# 統一 log 格式：時間、等級、來源、訊息。輸出到終端機，由 Docker 收集（docker compose logs api）。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

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
        # 把失敗原因寫進 log，事後才查得到；只回 503 給使用者的話，原因就不見了。
        logger.error("健康檢查失敗：無法連線資料庫：%s", e)
        # 503 = 服務暫時無法使用。讓監控工具或使用者一看就知道是資料庫出問題。
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unreachable", "detail": str(e)},
        )

    if row is None:
        logger.warning("健康檢查：資料庫可連線，但 pgvector 未啟用")

    return {
        "status": "ok",
        "database": "ok",
        # 沒抓到版本代表 pgvector 沒啟用（例如 db/init 沒被執行）。
        "pgvector": row[0] if row else None,
    }
