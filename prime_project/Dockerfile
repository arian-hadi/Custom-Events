# # Dockerfile

# FROM python:3.12-slim

# # Set environment variables
# ENV PYTHONDONTWRITEBYTECODE=1
# ENV PYTHONUNBUFFERED=1

# # Set working directory
# WORKDIR /app

# # Install system dependencies
# RUN apt-get update && apt-get install -y libpq-dev gcc

# # Install Python dependencies
# COPY requirements.txt /app/
# RUN pip install --no-cache-dir -r requirements.txt

# # Copy the rest of the project
# COPY . /app/

# # Expose port
# EXPOSE 8000

# # Command to run the app
# CMD ["gunicorn", "prime_project.wsgi:application", "--bind", "0.0.0.0:8000"]

# Use Python 3.11 slim image
FROM python:3.11-slim

# Environment settings
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /app

# Install system dependencies (for psycopg2, Pillow, Playwright, etc.)
RUN apt-get update && apt-get install -y \
    libpq-dev gcc python3-dev musl-dev \
    # Playwright browser dependencies (package names may vary by Debian version)
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcb1 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libcairo2 \
    libpango-1.0-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium || true

# Copy project files
COPY . .

# Expose port
EXPOSE 8000

# Start app with gunicorn
CMD ["gunicorn", "prime_project.wsgi:application", "--bind", "0.0.0.0:8000"]
