# 镜像仓库地址可换。国内有些加速站只能显式写前缀，当不了透明加速器，
# 那种情况下用 REGISTRY=docker.m.daocloud.io 之类即可，不必改这个文件。
ARG REGISTRY=docker.io
FROM ${REGISTRY}/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Shanghai

WORKDIR /app

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple \n    --trusted-host mirrors.aliyun.com -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh && mkdir -p data/uploads/images data/uploads/imports

EXPOSE 8000
CMD ["./entrypoint.sh"]
