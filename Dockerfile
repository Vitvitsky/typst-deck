FROM python:3.12-slim
ARG TYPST_VERSION=0.15.1
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils ca-certificates fonts-dejavu-core \
 && curl -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-x86_64-unknown-linux-musl.tar.xz" \
    | tar -xJ -C /tmp \
 && install -m755 /tmp/typst-x86_64-unknown-linux-musl/typst /usr/local/bin/typst \
 && rm -rf /tmp/typst-* /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY template ./template
COPY templates ./templates
RUN uv sync --frozen --no-dev
ENV TYPST_DECK_DATA_DIR=/data TYPST_DECK_TEMPLATE_DIR=/app/template TYPST_DECK_TEMPLATES_DIR=/app/templates PATH="/app/.venv/bin:$PATH"
# Встроенные шаблоны (default, dark) проверяются по контракту при сборке. Корпоративные
# в образ не попадают: их монтируют при запуске, и сервис проверяет их при старте.
RUN python -m typst_deck.templates
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "typst_deck.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
