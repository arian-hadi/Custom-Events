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

# Install system dependencies (for psycopg2, Pillow, etc.)
RUN apt-get update && apt-get install -y \
    libpq-dev gcc python3-dev musl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose port
EXPOSE 8000

# Start app with gunicorn
CMD ["gunicorn", "prime_project.wsgi:application", "--bind", "0.0.0.0:8000"]
