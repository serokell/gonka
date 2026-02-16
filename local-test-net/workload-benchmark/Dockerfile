FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install system dependencies BEFORE pip install
RUN apt-get update && apt-get install -y \
    pkg-config \         
    libsecp256k1-dev \    
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*


# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py .
COPY *.json .
COPY run_experiment.sh .
RUN chmod +x *.sh

COPY templates/ ./templates/
RUN mkdir -p experimental_logs


# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "UI_server.py"]
