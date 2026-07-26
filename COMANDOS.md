# ComparaSupers — Comandos de referencia

## Desarrollo local (Docker Compose)

```bash
# Levantar todo (API + Redis)
docker compose up --build

# Ver logs en tiempo real
docker compose logs -f api

# Parar todo
docker compose down

# Levantar con UI de Redis para inspeccionar la cache
docker compose --profile debug up --build
```

La API queda disponible en: http://localhost:8000
Documentación Swagger:     http://localhost:8000/docs
Redis UI (con --profile debug): http://localhost:8081

---

## Probar la API (PowerShell)

```powershell
# Health check
Invoke-RestMethod -Uri http://localhost:8000/health

# Comparar precios de una lista de la compra
$body = '{"items": ["leche entera", "pan de molde", "huevos L", "aceite de oliva"]}'
Invoke-RestMethod -Uri http://localhost:8000/compare `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

O abre http://localhost:8000/docs y pruébalo desde el navegador con Swagger UI.

---

## Kubernetes

### 1. Construir y cargar la imagen en el cluster local

```bash
# Construir imagen
docker build -t comparasupers-api:latest -f api/Dockerfile .

# Con kind (Docker Desktop) la imagen ya está disponible automáticamente
# si usas imagePullPolicy: Never en los manifiestos
```

### 2. Desplegar en Kubernetes

```bash
# Aplicar todos los manifiestos de una vez
kubectl apply -f k8s/

# Ver que todo está corriendo
kubectl get all -n comparasupers

# Ver logs de la API
kubectl logs -f deployment/comparasupers-api -n comparasupers

# Ver logs de Redis
kubectl logs -f deployment/redis -n comparasupers
```

### 3. Acceder a la API en Kubernetes

La API está expuesta en NodePort 30800:
http://localhost:30800/docs

### 4. Comandos útiles de Kubernetes

```bash
# Ver todos los recursos del namespace
kubectl get all -n comparasupers

# Describir un pod (útil para debugging)
kubectl describe pod <nombre-del-pod> -n comparasupers

# Ver eventos del cluster (errores, scheduling, etc.)
kubectl get events -n comparasupers --sort-by='.lastTimestamp'

# Entrar dentro de un pod (como SSH)
kubectl exec -it deployment/comparasupers-api -n comparasupers -- /bin/sh

# Escalar la API a 3 réplicas
kubectl scale deployment comparasupers-api --replicas=3 -n comparasupers

# Borrar TODO el proyecto de Kubernetes
kubectl delete namespace comparasupers
```

### 5. Lanzar un Job de scraping manual

```bash
kubectl apply -f k8s/scraper-job.yaml -n comparasupers

# Ver estado del job
kubectl get jobs -n comparasupers

# Ver logs del job
kubectl logs job/scraper-test-job -n comparasupers
```

---

## Estructura del proyecto

```
ComparaSupers/
├── scrapers/
│   ├── base_scraper.py      # clase base abstracta
│   ├── mercadona.py         # scraper Mercadona (API JSON)
│   ├── carrefour.py         # scraper Carrefour (API JSON)
│   ├── Dockerfile           # imagen standalone para Jobs
│   └── requirements.txt
├── api/
│   ├── main.py              # FastAPI — /health y /compare
│   ├── Dockerfile           # imagen principal (incluye scrapers + aggregator)
│   └── requirements.txt
├── aggregator/
│   └── main.py              # lógica de comparación y ranking
├── k8s/
│   ├── namespace.yaml       # namespace "comparasupers"
│   ├── configmap.yaml       # configuración externalizada
│   ├── redis-deployment.yaml
│   ├── api-deployment.yaml
│   └── scraper-job.yaml     # Job y CronJob de ejemplo
├── docker-compose.yaml      # desarrollo local
└── COMANDOS.md              # este archivo
```
