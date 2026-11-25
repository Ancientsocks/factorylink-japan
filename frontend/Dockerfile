FROM node:22-alpine AS build
ARG VITE_FACTORYLINK_PUBLIC_REGISTRATION=false
ENV VITE_FACTORYLINK_PUBLIC_REGISTRATION=${VITE_FACTORYLINK_PUBLIC_REGISTRATION}
WORKDIR /web
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine
ENV BACKEND_HOST=backend:8000 NGINX_ENVSUBST_FILTER=BACKEND_HOST
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:10000/ || exit 1
