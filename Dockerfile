FROM python:3.11-slim

WORKDIR /app

# Системные зависимости для сборки C-расширений
# Зеркало Debian (Debian 13/trixie использует deb822-формат)
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list; \
    apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

COPY pyproject.toml .
COPY src/ ./src/

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --upgrade pip && pip install --no-cache-dir .

# --proxy-headers: доверять заголовкам Nginx (X-Forwarded-Proto и X-Forwarded-For),
# иначе API будет считать, что запрос пришёл по http. Порт 8000 снаружи недоступен,
# так что "*" безопасно.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]