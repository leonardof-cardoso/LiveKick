FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instala apenas dependencias minimas e remove caches em seguida
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && rm -rf /root/.cache /tmp/* /var/tmp/*

COPY . .

# Garante diretorios usados em runtime
RUN mkdir -p /app/cache /app/logs

# Roda como usuario nao-root
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "main.py"]
