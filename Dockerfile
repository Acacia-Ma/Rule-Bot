FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    make \
    libffi-dev \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Clean up build dependencies to reduce image size
RUN apt-get purge -y gcc g++ make libffi-dev libsodium-dev && apt-get autoremove -y && apt-get clean

# Copy application code
COPY src/ ./src/
COPY start.sh .
RUN chmod +x start.sh

# Create necessary directories
RUN mkdir -p /app/data /app/logs

EXPOSE 8080

CMD ["./start.sh"] 