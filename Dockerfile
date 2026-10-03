FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    DASHBOARD_PORT=8123 \
    CHECK_INTERVAL=30

WORKDIR /srv

# Xray как в референсе VLESS-to-HTTP
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl unzip ca-certificates \
 && curl -L -o /tmp/xray.zip https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip \
 && mkdir -p /tmp/xray \
 && unzip /tmp/xray.zip -d /tmp/xray \
 && install -m755 /tmp/xray/xray /usr/local/bin/Xray \
 && mkdir -p /usr/local/share/xray \
 && mv /tmp/xray/geoip.dat /tmp/xray/geosite.dat /usr/local/share/xray/ \
 && rm -rf /tmp/xray /tmp/xray.zip \
 && apt-get purge -y unzip \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

VOLUME ["/data"]
EXPOSE 8123

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${DASHBOARD_PORT:-8123}"]
