#!/bin/bash

# Deployment script for Custom-Events Django app
echo "Starting deployment process..."

# Stop existing containers
echo "Stopping existing containers..."
docker compose down

# Remove old volumes (optional - uncomment if you want fresh database)
# docker volume rm prime_project_postgres_data

# Build and start containers
echo "Building and starting containers..."
docker compose -f docker-compose.yml --env-file .env.prod up -d --build

# Wait for database to be ready
echo "Waiting for database to be ready..."
sleep 10

# Run migrations
echo "Running database migrations..."
docker compose exec web python manage.py migrate

# Create superuser (optional - uncomment if needed)
# echo "Creating superuser..."
# docker compose exec web python manage.py createsuperuser

# Collect static files
echo "Collecting static files..."
docker compose exec web python manage.py collectstatic --noinput

# Show container status
echo "Container status:"
docker compose ps

echo "Deployment completed!"
echo "Your app should be available at: http://128.140.40.7"
echo "Check logs with: docker compose logs -f"
