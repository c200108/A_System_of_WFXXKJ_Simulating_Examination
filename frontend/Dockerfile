# 见 backend/Dockerfile 里同名参数的说明
ARG REGISTRY=docker.io
FROM ${REGISTRY}/library/node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

ARG REGISTRY=docker.io
FROM ${REGISTRY}/library/nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
