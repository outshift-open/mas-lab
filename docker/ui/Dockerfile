#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# MAS Lab UI — static Vite build served by nginx on port 8080.
FROM node:22-bookworm AS builder

ARG VITE_API_BASE_URL=
WORKDIR /app

RUN corepack enable

COPY ui/package.json ui/yarn.lock ui/.yarnrc.yml ./
COPY ui/.yarn ./.yarn

RUN yarn install --immutable

COPY ui/ ./

RUN if [ -n "$VITE_API_BASE_URL" ]; then echo "VITE_API_BASE_URL=$VITE_API_BASE_URL" > .env; fi
RUN yarn build

FROM nginx:alpine

COPY docker/ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/ui/entrypoint-ui.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
