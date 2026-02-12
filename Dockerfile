# ---------- build frontend ----------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- build backend ----------
FROM python:3.12-slim AS backend

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libcairo2 \
    libpango-1.0-0 \
    libasound2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libx11-6 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory - this is where Railway copies files to
WORKDIR /app

# Copy requirements first for better caching
COPY agent/requirements.txt /app/agent/
RUN pip install --no-cache-dir -r /app/agent/requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy the application code into an 'agent' subdirectory
# This way 'agent.main' import works correctly
COPY agent/ /app/agent/

# Copy compiled frontend into backend folder
COPY --from=frontend-build /app/frontend/dist /app/agent/dist

# Expose port (Railway uses PORT env var)
EXPOSE 8000

# Run the application with uvicorn
# Railway sets PORT env var, so we use that
CMD ["sh", "-c", "cd /app && uvicorn agent.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
