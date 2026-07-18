# Multi-stage build: compile the React console, then serve everything from Flask.
# The result is a single container: Flask serves the API, the landing page (/),
# and the built console (/app).

# --- Stage 1: build the frontend ---
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime ---
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt waitress

COPY backend/ ./backend/
COPY landing/ ./landing/
COPY --from=frontend /fe/dist ./frontend/dist

WORKDIR /app/backend
ENV PORT=8080
EXPOSE 8080
CMD ["python", "wsgi.py"]
