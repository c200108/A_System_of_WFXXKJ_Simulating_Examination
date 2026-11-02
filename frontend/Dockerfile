# 见 backend/Dockerfile 里同名参数的说明
ARG REGISTRY=docker.io
FROM ${REGISTRY}/library/node:20-alpine AS build
WORKDIR /app
# 带上锁文件、用 npm ci：装的是测试过的那一套版本。只拷 package.json 的话 npm 会按范围取最新，
# 装上要 Node 22 的新包（EBADENGINE 警告），每次部署装到的版本还不一样。
# --loglevel=http 让每个下载都打一行，慢网下几分钟没输出时看得出不是卡死
COPY package.json package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com --loglevel=http --no-audit --no-fund
COPY . .
RUN npm run build

ARG REGISTRY=docker.io
FROM ${REGISTRY}/library/nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
