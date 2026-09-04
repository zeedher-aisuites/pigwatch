FROM node:22.23.2-alpine AS build

RUN npm install --global npm@12.0.2 \
    && test "$(npm --version)" = "12.0.2"

WORKDIR /workspace

ARG VITE_PIGWATCH_API_BASE_URL=/api
ARG VITE_PIGWATCH_OBSERVATION_LIMIT=200
ARG VITE_PIGWATCH_POLL_INTERVAL_MS=10000
ARG VITE_PIGWATCH_STALE_AFTER_MS=60000
ENV VITE_PIGWATCH_API_BASE_URL=${VITE_PIGWATCH_API_BASE_URL} \
    VITE_PIGWATCH_OBSERVATION_LIMIT=${VITE_PIGWATCH_OBSERVATION_LIMIT} \
    VITE_PIGWATCH_POLL_INTERVAL_MS=${VITE_PIGWATCH_POLL_INTERVAL_MS} \
    VITE_PIGWATCH_STALE_AFTER_MS=${VITE_PIGWATCH_STALE_AFTER_MS}

COPY package.json package-lock.json ./
COPY apps/dashboard/package.json apps/dashboard/package.json
RUN npm ci

COPY apps/dashboard apps/dashboard
RUN npm run build --workspace @pigwatch/dashboard

FROM nginx:1.27-alpine

COPY apps/dashboard/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/apps/dashboard/dist /usr/share/nginx/html

EXPOSE 80
