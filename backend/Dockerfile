# ZEN70 核心网关镜像（法典 1.1 彻底容器化）
# 从项目根构建: docker build -f backend/Dockerfile -t zen70-gateway .
ARG PYTHON=python:3.12-slim
FROM ${PYTHON}
WORKDIR /app
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend

# 法典：网关仅监听，不暴露端口映射，由编排注入 REDIS_HOST 等
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
