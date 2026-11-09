FROM python:3.11-slim

WORKDIR /app

# Зеркала вынесены в аргументы сборки: по умолчанию те, что работают у нас,
# но собрать с официальных источников можно без правки файла:
#   docker build --build-arg APT_MIRROR=deb.debian.org \
#                --build-arg PIP_INDEX_URL=https://pypi.org/simple .
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# Системные зависимости для сборки C-расширений.
# Debian 13/trixie хранит источники в deb822-формате, отсюда два sed.
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list; \
    apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ ./src/

RUN pip config set global.index-url "${PIP_INDEX_URL}" \
    && pip install --upgrade pip \
    && pip install --no-cache-dir . \
    && rm -rf /app/build

# Миграции нужны в образе: контейнер накатывает их сам при старте.
COPY alembic.ini .
COPY migrations/ ./migrations/

# Схема приводится к последней ревизии до запуска сервера, иначе приложение
# поднимется на пустой базе. exec заменяет оболочку процессом uvicorn,
# чтобы сигналы остановки доходили до него напрямую.
#
# --proxy-headers: доверять заголовкам Nginx (X-Forwarded-Proto и X-Forwarded-For),
# иначе API будет считать, что запрос пришёл по http. Порт 8000 снаружи недоступен,
# так что "*" безопасно.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
