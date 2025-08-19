FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV PIP_DEFAULT_TIMEOUT=120

# OS deps + retries
RUN set -eux; \
    apt-get update -o Acquire::Retries=3; \
    apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates apt-transport-https \
      unixodbc unixodbc-dev libgssapi-krb5-2; \
    rm -rf /var/lib/apt/lists/*

# Microsoft repo zonder apt-key + retries
RUN set -eux; \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /usr/share/keyrings/ms-packages.gpg; \
    echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/ms-packages.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/microsoft-prod.list; \
    apt-get update -o Acquire::Retries=3; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Zorg dat requirements2.txt óók pyodbc bevat
COPY requirements2.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefer-binary -r requirements2.txt

COPY . .

EXPOSE 8080
CMD gunicorn psf_dashboard:server -b 0.0.0.0:${PORT:-8080} -w 2 -k gthread --threads 8 --timeout 120
