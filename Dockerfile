# Gebruik officiële Python 3.11 slim image
FROM python:3.11-slim

# Werkdirectory in de container
WORKDIR /app

# Kopieer requirements naar container
COPY requirements2.txt .

# Installeer dependencies (pip update + requirements)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements2.txt

# Kopieer alle bestanden naar container
COPY . .

# Exposeer poort 8050 (Dash default)
EXPOSE 8050

# Command om app te starten
CMD ["gunicorn", "psf_dashboard:server", "--bind", "0.0.0.0:8050", "--workers", "1"]
