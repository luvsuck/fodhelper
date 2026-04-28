# 基础镜像使用轻量 Python 3
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 拷贝项目文件到容器
COPY requirements.txt .
COPY app ./app
COPY run.py .
COPY web ./web

# 安装依赖
RUN pip install --no-cache-dir --upgrade pip -i https://mirrors.aliyun.com/pypi/simple \
    && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple

# 暴露端口
EXPOSE 8787

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
