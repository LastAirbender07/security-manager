FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including Docker CLI for sibling container support)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    docker.io \
    libpq-dev \
    gcc \
    wget \
    apt-transport-https \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install Trivy
RUN curl -fsSL https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor -o /usr/share/keyrings/trivy.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb bookworm main" | tee -a /etc/apt/sources.list.d/trivy.list \
    && apt-get update \
    && apt-get install -y trivy

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Keep container alive
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
