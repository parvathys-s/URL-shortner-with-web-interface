# Python slim base
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Create non-root user
RUN useradd -m appuser
USER appuser

EXPOSE 8000
ENV PORT=8000 BASE_URL=http://127.0.0.1:8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]