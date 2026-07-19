# Single-container deploy: Flask app (dashboard + single Agents SDK agent)
# served by waitress. All data is synthetic; the only secret is the OpenRouter
# API key, injected at runtime as an env var (never baked into the image).
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt waitress

COPY . .

ENV PORT=8080
EXPOSE 8080
CMD ["python", "wsgi.py"]
