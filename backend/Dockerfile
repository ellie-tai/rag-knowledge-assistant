# api 容器的「建置步驟」。
FROM python:3.12-slim

# 從 uv 官方 image 複製 uv 執行檔進來，不需要在電腦上另外安裝 uv。
COPY --from=ghcr.io/astral-sh/uv:0.8.0 /uv /usr/local/bin/uv

WORKDIR /app

# 先只複製套件清單再安裝：程式碼改動時，Docker 可以沿用已安裝好的套件那一層，重新 build 比較快。
# --frozen：嚴格照 uv.lock 的版本安裝，確保每台電腦裝到的都一樣。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# uv sync 會把套件裝進 /app/.venv，把它放到 PATH 最前面。
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
