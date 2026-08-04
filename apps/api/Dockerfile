FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dma_api ./dma_api
ENV PORT=8080
CMD ["sh", "-c", "uvicorn dma_api.main:app --host 0.0.0.0 --port ${PORT}"]
