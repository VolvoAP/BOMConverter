# Gebruik officiële Python 3.11 slim image
FROM python:3.11-slim

# OS dependencies die we nodig hebben
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg apt-transport-https ca-certificates \
    unixodbc unixodbc-dev libgssapi-krb5-2 \
 && rm -rf /var/lib/apt/lists/*

# Microsoft repo registreren + SQL Server ODBC driver 18 installeren
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/12/prod.list \
      -o /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && rm -rf /var/lib/apt/lists/*

# Werkdirectory
WORKDIR /app

# Python dependencies
COPY requirements2.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements2.txt

# App code
COPY . .

# Luisterpoort (Render geeft $PORT mee)
EXPOSE 8080

# Start de app via Gunicorn; target is jouw Flask server object in psf_dashboard.py
# Gebruik threads voor wat meer concurrency met Dash callbacks
CMD gunicorn psf_dashboard:server -b 0.0.0.0:${PORT:-8080} -w 2 -k gthread --threads 8 --timeout 120
