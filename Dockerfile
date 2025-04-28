# Dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    xvfb libnss3 libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 \
    libxtst6 libxrandr2 libasound2 libpangocairo-1.0-0 libatk1.0-0 libcups2 \
    libdrm2 fonts-liberation libxss1 libgbm1 wget unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps
COPY src src
COPY entrypoint.sh .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Set the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]