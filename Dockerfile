FROM python:3.12-slim
WORKDIR /app
# fonts-dejavu-core: a TTF for the Pillow-rendered /today card (slim has no fonts)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["python", "-m", "app.main"]
