FROM python:3.11-slim

WORKDIR /app
ARG PIP_INDEX_URL=https://pypi.org/simple

COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" ".[recommendations]"

EXPOSE 50051
CMD ["python", "-m", "recsys.server"]
