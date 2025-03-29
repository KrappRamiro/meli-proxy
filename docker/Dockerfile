FROM python:3.12-slim

# Dependencias del sistema para watchdog
RUN apt-get update && apt-get install -y --no-install-recommends \
    libinotifytools0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copiar código fuente y configuración
COPY src/ ./src/

# Puerto expuesto
EXPOSE 8080

RUN ls -la

CMD ["uvicorn", "src.api_proxy.main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "debug"]
