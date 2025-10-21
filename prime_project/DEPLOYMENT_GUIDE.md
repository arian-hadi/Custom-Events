# Custom-Events Deployment Guide

## Issues Fixed

### 1. Static Files Issue
- **Problem**: Tailwind CSS styles not loading in production
- **Solution**: Added Nginx container to serve static files properly
- **Changes**: Updated `docker-compose.yml` with Nginx service and volume mounts

### 2. Database Issue  
- **Problem**: Events page showing internal server error due to missing database tables
- **Solution**: Added `python manage.py migrate` to Docker startup command
- **Changes**: Updated Docker command to run migrations before starting the app

## Deployment Steps

### 1. Update Your Server

SSH into your Hetzner VPS:
```bash
ssh root@128.140.40.7
cd /root/Custom-Events/prime_project
```

### 2. Update Docker Configuration

The following files have been updated:

#### docker-compose.yml
- Added Nginx service for static file serving
- Added volume mounts for static and media files
- Added database migration to startup command

#### nginx.conf
- Created Nginx configuration for static file serving
- Proper routing for static files, media files, and Django app

### 3. Create Environment File

Create `.env.prod` file with your production settings:
```bash
nano .env.prod
```

Add this content (update with your actual values):
```env
DEBUG=False
SECRET_KEY=your_secret_key_here_change_this_in_production
ALLOWED_HOSTS=128.140.40.7,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://128.140.40.7,http://localhost

# Database
DB_ENGINE=django.db.backends.postgresql
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=db
DB_PORT=5432

# Email settings (configure these for production)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
SUPPORT_EMAIL=support@yourdomain.com
```

### 4. Deploy the Application

```bash
# Stop existing containers
docker compose down

# Remove old Nginx container if it exists
docker stop nginx 2>/dev/null || true
docker rm nginx 2>/dev/null || true

# Build and start with new configuration
docker compose -f docker-compose.yml --env-file .env.prod up -d --build

# Wait for database to be ready
sleep 10

# Run migrations (if not already done by startup command)
docker compose exec web python manage.py migrate

# Collect static files
docker compose exec web python manage.py collectstatic --noinput

# Check container status
docker compose ps
```

### 5. Verify Deployment

1. **Check if containers are running:**
   ```bash
   docker compose ps
   ```

2. **Check logs for any errors:**
   ```bash
   docker compose logs -f
   ```

3. **Test the application:**
   - Visit: http://128.140.40.7
   - Check if CSS styles are loading
   - Test the events page

### 6. Create Admin User (Optional)

If you need an admin user:
```bash
docker compose exec web python manage.py createsuperuser
```

## Troubleshooting

### If static files still don't load:
1. Check if static files are collected:
   ```bash
   docker compose exec web ls -la /app/staticfiles/
   ```

2. Check Nginx logs:
   ```bash
   docker compose logs nginx
   ```

### If database errors persist:
1. Check if migrations ran:
   ```bash
   docker compose exec web python manage.py showmigrations
   ```

2. Check database connection:
   ```bash
   docker compose exec web python manage.py dbshell
   ```

### If containers won't start:
1. Check logs:
   ```bash
   docker compose logs
   ```

2. Rebuild from scratch:
   ```bash
   docker compose down -v
   docker compose up -d --build
   ```

## File Structure After Deployment

```
/root/Custom-Events/prime_project/
├── docker-compose.yml          # Updated with Nginx service
├── nginx.conf                  # Nginx configuration
├── .env.prod                   # Production environment variables
├── deploy.sh                   # Deployment script
└── DEPLOYMENT_GUIDE.md         # This guide
```

## What's Fixed

✅ **Static Files**: Nginx now serves CSS/JS files directly  
✅ **Database**: Migrations run automatically on startup  
✅ **Events Page**: Database tables created, no more internal server error  
✅ **Production Ready**: Proper environment configuration  

Your Django app should now work perfectly in production with all styles loading correctly!
