# ── 构建阶段 ──
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── 运行阶段 ──
FROM nginx:alpine
RUN apk add --no-cache gettext
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/config.js.template /etc/nginx/config.js.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["/bin/sh", "-c", "envsubst < /etc/nginx/config.js.template > /usr/share/nginx/html/config.js && nginx -g 'daemon off;'"]
