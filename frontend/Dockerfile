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
# nginx/ 下是拆开的规则和 HTTPS 切换脚本，nginx.conf 是默认的纯 http 配置。
# http.conf 留一份原样的，开 HTTPS 失败时脚本拿它退回去。
COPY nginx/base.conf nginx/static.conf nginx/backend.conf nginx/https.conf /etc/nginx/exam/
COPY nginx.conf /etc/nginx/exam/http.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
# 在 Windows 上检出、或者从 ZIP 解压的话执行位会丢，这里补上，不然 nginx 镜像会跳过它
COPY nginx/40-exam-https.sh /docker-entrypoint.d/40-exam-https.sh
RUN chmod +x /docker-entrypoint.d/40-exam-https.sh
# 443 只有配了证书（.env 的 HTTPS_PORT + SSL_CERT_DIR）才真的在听
EXPOSE 80 443
