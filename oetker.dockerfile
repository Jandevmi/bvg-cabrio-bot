FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oetker_monitor.py .

# config.json is mounted from the k8s Secret "oetker-monitor-config"
ENV CONFIG_PATH=/config/config.json

CMD ["python", "-u", "oetker_monitor.py"]
