FROM ghcr.io/astral-sh/uv:0.13.6 AS uv
FROM python:3.13-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src/aight_api ./src/aight_api
COPY scripts/run_worker.py ./scripts/run_worker.py
RUN useradd --uid 10001 --create-home aight && mkdir -p /data && chown aight:aight /data && chmod 700 /data
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AIGHT_DATA_DIR=/data
USER aight
CMD ["uvicorn", "aight_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
