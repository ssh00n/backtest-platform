FROM python:3.12-slim

WORKDIR /app

# System dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    "fastapi>=0.100.0" \
    "uvicorn[standard]>=0.23.0" \
    "websockets>=11.0" \
    python-dotenv \
    pydantic \
    alpaca-py \
    pandas \
    pyarrow \
    numpy \
    requests \
    lxml \
    html5lib \
    pytz \
    "sqlalchemy>=2.0" \
    "psycopg[binary]>=3.1" \
    pytz \
    yfinance

# Copy app source
COPY api/ ./api/
COPY src/ ./src/

# Create data/cache directory (SP500 캐시 런타임 자동 생성)
RUN mkdir -p ./data/cache

EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
