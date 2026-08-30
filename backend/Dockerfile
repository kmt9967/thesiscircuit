FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend backend
COPY agents agents
COPY strategies strategies
COPY risk risk
COPY replay replay
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
