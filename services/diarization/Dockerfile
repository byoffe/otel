FROM python:3.12-slim
WORKDIR /app
COPY otel_common/ ./otel_common/
COPY services/diarization/requirements.txt .
RUN pip install --no-cache-dir --pre -r requirements.txt
COPY services/diarization/main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
