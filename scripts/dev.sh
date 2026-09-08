#!/usr/bin/env bash
# Локальный запуск с автоперезагрузкой. Ключ и модель DeepSeek берутся из ~/stack/.env
# grep'ом (файл не исполняем), если переменные ещё не заданы в окружении.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="${STACK_ENV:-$HOME/stack/.env}"
if [ -f "$ENV_FILE" ]; then
  for k in DEEPSEEK_API_KEY DEEPSEEK_API_BASE DEEPSEEK_MODEL; do
    if [ -z "${!k:-}" ]; then
      v=$(grep -m1 "^$k=" "$ENV_FILE" | cut -d= -f2- || true)
      [ -n "$v" ] && export "$k=$v"
    fi
  done
fi
exec uv run uvicorn typst_deck.app:create_app --factory --reload --host 127.0.0.1 --port "${PORT:-8000}"
