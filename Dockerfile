FROM python:3.12-slim

WORKDIR /app

# System dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from requirements.txt (확실한 방법)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY api/ ./api/
COPY src/ ./src/

# Create data/cache directory (SP500 캐시 런타임 자동 생성)
RUN mkdir -p ./data/cache

EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
# cache-bust: 1772991750
