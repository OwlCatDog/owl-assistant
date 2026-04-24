FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py /app/main.py

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8080}"]
