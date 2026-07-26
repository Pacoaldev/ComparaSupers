# Dockerfile del scraper — imagen standalone para k8s Jobs
# Se usa cuando queremos correr un scraper como Job independiente
# sin levantar toda la API

FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias
COPY scrapers/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY scrapers/ ./scrapers/
COPY aggregator/ ./aggregator/

ENV PYTHONPATH="/app/scrapers:/app/aggregator"

# Non-root user
RUN adduser --disabled-password --gecos "" scraper
USER scraper

# Por defecto no hace nada — el k8s Job sobreescribe el command
# Ejemplo: command: ["python", "scrapers/mercadona.py"]
CMD ["python", "-c", "print('Scraper container ready. Specify command in k8s Job.')"]
