# ETL Pipeline Local Development Container
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY etl/ /app/etl/
COPY config/ /app/config/
COPY tests/ /app/tests/
COPY sample_data/ /app/sample_data/

# Set Python path
ENV PYTHONPATH=/app

# Default environment variables
ENV ENVIRONMENT=local
ENV AWS_DEFAULT_REGION=us-east-1
ENV AWS_ACCESS_KEY_ID=test
ENV AWS_SECRET_ACCESS_KEY=test
ENV LOG_LEVEL=DEBUG

# Run tests by default
CMD ["python", "-m", "pytest", "tests/", "-v"]
