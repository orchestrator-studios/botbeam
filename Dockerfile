# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Production image
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev
COPY VERSION ./
COPY server/ server/
COPY mcp/ mcp/
COPY public/ public/
COPY --from=frontend-build /build/dist frontend/dist/
EXPOSE 4888
CMD ["node", "server/index.js"]
