FROM python:3.11-slim-bookworm

WORKDIR /app

# System libs for Pillow / PyTorch CPU
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt build.sh ./
RUN chmod +x build.sh && bash build.sh

# App code + committed model weights
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
