FROM python:3.12-slim

WORKDIR /app

# Install dependencies
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
    lxml

# Copy app
COPY api/ ./api/
COPY src/ ./src/
COPY data/cache/sp500_constituents.parquet ./data/cache/sp500_constituents.parquet

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
