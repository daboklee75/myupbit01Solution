# Use official Python image (slim version for smaller size)
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (basic tools + build essentials)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry using pip (simplest for Docker)
RUN pip install poetry

# Copy dependency definition
COPY pyproject.toml poetry.lock ./

# Install dependencies (no dev dependencies, no interaction)
# We disable virtualenvs because Docker itself is the isolation
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Copy the rest of the application
COPY src ./src
COPY .env.template ./.env.template

# Create directories for data (mounted via volume)
RUN mkdir -p /app/data /app/logs

# Set env vars for dynamic data paths (default)
ENV MYUPBIT_DATA_DIR=/app/data
ENV LOG_DIR=/app/data/logs

# Expose Streamlit port
EXPOSE 8501

# Entrypoint script to handle arguments
COPY run_docker.sh /app/run_docker.sh
RUN chmod +x /app/run_docker.sh

ENTRYPOINT ["/app/run_docker.sh"]
