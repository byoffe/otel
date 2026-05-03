FROM python:3.12-slim
WORKDIR /app
COPY otel_common/ ./otel_common/
COPY services/mcp_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/mcp_server/ ./mcp_server/
CMD ["python", "-m", "mcp_server"]
