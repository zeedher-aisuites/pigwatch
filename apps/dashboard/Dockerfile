FROM node:22-alpine AS build

WORKDIR /workspace

COPY package.json package-lock.json ./
COPY apps/dashboard/package.json apps/dashboard/package.json
RUN npm ci

COPY apps/dashboard apps/dashboard
RUN npm run build --workspace @pigwatch/dashboard

FROM nginx:1.27-alpine

COPY apps/dashboard/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/apps/dashboard/dist /usr/share/nginx/html

EXPOSE 80
