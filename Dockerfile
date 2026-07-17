# Docker 构建阶段
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── 运行阶段 ───
FROM python:3.11-slim

WORKDIR /app

# 从构建阶段复制依赖
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制项目代码
COPY . .

# 创建非 root 用户
RUN useradd -m -u 1000 retrivault && chown -R retrivault:retrivault /app
USER retrivault

EXPOSE 8000

ENV NO_PROXY=localhost,127.0.0.1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
