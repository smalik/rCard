FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --extra gcp --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --extra gcp --no-editable

FROM python:3.13-slim
RUN useradd --system --uid 10001 plytos
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" PLYTOS_MIGRATIONS_DIR=/app/migrations PYTHONUNBUFFERED=1
USER plytos
EXPOSE 8080
CMD ["uvicorn", "--factory", "plytos_api.main:create_app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
