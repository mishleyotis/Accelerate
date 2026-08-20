FROM node:20-slim AS build
WORKDIR /app
# The lockfile, and `ci` rather than `install`. The image copied package.json
# alone and resolved fresh on every build, so the dependency tree Cloud Run
# ran was never the tree the lockfile pins or CI tested, and two builds of the
# same commit could differ. `npm ci` installs the lockfile exactly and fails
# rather than silently rewriting it when the two drift apart.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY next.config.js ./
COPY scripts ./scripts
COPY lib ./lib
COPY proto ./proto
COPY public ./public
COPY app ./app
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production PORT=8080
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
CMD ["node", "server.js"]
