# ---- build stage: install production dependencies ----
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS build

WORKDIR /app
ENV PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

COPY totalrecall ./totalrecall
COPY migrations ./migrations
COPY skills ./skills
COPY workers ./workers
COPY ui ./ui

RUN uv sync --no-dev --frozen

# ---- runtime stage: hardened production image ----
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS runtime

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY --from=build /app /app

ENV PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["sh", "-c", "uv run python -m totalrecall.storage.migrations && uv run uvicorn totalrecall.main:app --host 0.0.0.0 --port 8000"]

# ---- test stage: adds dev dependencies and test source ----
FROM build AS test-stage

RUN uv sync --dev --frozen

COPY tests ./tests

CMD ["sh", "-c", "uv run python -m totalrecall.storage.migrations && uv run pytest"]
