FROM node:22-slim AS base

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:${PATH}"

WORKDIR /app/frontend

RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./


FROM base AS deps

RUN pnpm install --frozen-lockfile


FROM deps AS dev

COPY frontend/ ./

EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]


FROM deps AS build

COPY frontend/ ./
RUN pnpm build


FROM nginx:1.27-alpine AS prod

COPY docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
