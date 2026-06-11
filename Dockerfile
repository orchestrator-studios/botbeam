# Stage 1: build the React frontend (Vite, base '/app/' in production)
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: production image — FastAPI app serves the API, WS, and the built frontend
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=frontend-build /build/dist frontend/dist/
# main.py resolves the frontend at ../frontend/dist relative to backend/
WORKDIR /app/backend
EXPOSE 4888
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "4888"]
