# Debian 12 (bookworm) + Python 3.11
FROM python:3.11-slim

# OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates apt-transport-https \
    unixodbc unixodbc-dev libgssapi-krb5-2 \
 && rm -rf /var/lib/apt/lists/*

# Microsoft repo + key (zonder apt-key)
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/ms-packages.gpg && \
    echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/ms-packages.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/microsoft-prod.list && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements2.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements2.txt

# App code
COPY . .

EXPOSE 8080

# Start via Gunicorn (jouw bestandsnaam: psf_dashboard.py -> server)
CMD gunicorn psf_dashboard:server -b 0.0.0.0:${PORT:-8080} -w 2 -k gthread --threads 8 --timeout 120
