# --- Build stage ---
FROM python:3.12-slim AS builder

WORKDIR /app

COPY api/requirements.txt ./api/requirements.txt
COPY scrapers/requirements.txt ./scrapers/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        -r api/requirements.txt \
        -r scrapers/requirements.txt

# --- Runtime stage ---
FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema necesarias para Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chromium dependencies
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libpangocairo-1.0-0 libx11-6 libx11-xcb1 libxcb1 libxext6 \
    libxss1 libxtst6 libglib2.0-0 fonts-liberation ca-certificates \
    # Limpieza
    && rm -rf /var/lib/apt/lists/*

# Copiar paquetes Python instalados
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Instalar Chromium para Playwright (como root, antes de cambiar usuario)
RUN playwright install chromium

# Copiar código fuente
COPY scrapers/ ./scrapers/
COPY aggregator/ ./aggregator/
COPY api/ ./api/

ENV PYTHONPATH="/app/scrapers:/app/aggregator:/app/api"

# Non-root user
RUN adduser --disabled-password --gecos "" appuser

# Mover el cache de Playwright al home del usuario no-root
RUN mv /root/.cache /home/appuser/.cache && chown -R appuser:appuser /home/appuser/.cache

USER appuser

ENV PLAYWRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
