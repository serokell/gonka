FROM golang:1.24.2-alpine3.20
# Set working directory
WORKDIR /app

COPY requirements.txt .

# Install system dependencies BEFORE pip install
RUN apk add --no-cache \
    pkgconf \
    libsecp256k1-dev \
    gcc \
    g++ \
    make \
    libffi-dev \
    openssl-dev

RUN apk add --no-cache \
    python3 \
    py3-pip

RUN python3 -m venv /venv
RUN /venv/bin/pip install --no-cache-dir -r requirements.txt
