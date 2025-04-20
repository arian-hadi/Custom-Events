# Dockerfile

# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory inside container
WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js and npm for TailwindCSS builds
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs

# Install Python dependencies
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /code/

# Build Tailwind CSS if you have npm scripts
# (You can trigger `npm install` and `npm run build` in your entrypoint if needed)

# Expose port (gunicorn will listen on 8000)
EXPOSE 8000

# Default command (overridden by docker-compose)
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000"]
