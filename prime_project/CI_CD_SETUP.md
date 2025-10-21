# CI/CD Setup Guide

## GitHub Actions Workflow

The CI/CD pipeline is now configured with the following features:

### 🔄 **Pipeline Stages:**

1. **Test Stage** - Runs on every push/PR
   - Sets up Python 3.11
   - Installs dependencies
   - Runs Django tests with PostgreSQL
   - Tests both `master` and `develop` branches

2. **Build Stage** - Runs only on `master` branch
   - Builds Docker image
   - Validates container build

3. **Deploy Stage** - Runs only on `master` branch after tests pass
   - Deploys to Hetzner VPS
   - Pulls latest code
   - Rebuilds and restarts containers
   - Runs migrations
   - Collects static files

## 🔐 **Required GitHub Secrets**

You need to add these secrets to your GitHub repository:

### 1. Go to GitHub Repository Settings
- Navigate to: `https://github.com/arian-hadi/Custom-Events/settings/secrets/actions`
- Click "New repository secret"

### 2. Add These Secrets:

#### **Server Access:**
| Secret Name | Value | Description |
|-------------|-------|-------------|
| `HETZNER_HOST` | `128.140.40.7` | Your Hetzner VPS IP address |
| `HETZNER_USERNAME` | `root` | SSH username for your VPS |
| `HETZNER_SSH_KEY` | `[Your SSH Private Key]` | Private key for SSH access |

#### **Django Configuration:**
| Secret Name | Value | Description |
|-------------|-------|-------------|
| `DJANGO_SECRET_KEY` | `[Your Django Secret Key]` | Django secret key for production |
| `ALLOWED_HOSTS` | `yourdomain.com,www.yourdomain.com,128.140.40.7` | Comma-separated list of allowed hosts |
| `CSRF_TRUSTED_ORIGINS` | `https://yourdomain.com,https://www.yourdomain.com` | Comma-separated CSRF trusted origins |

#### **Database Configuration:**
| Secret Name | Value | Description |
|-------------|-------|-------------|
| `DB_NAME` | `postgres` | PostgreSQL database name |
| `DB_USER` | `postgres` | PostgreSQL username |
| `DB_PASSWORD` | `[Your DB Password]` | PostgreSQL password |

#### **Email Configuration:**
| Secret Name | Value | Description |
|-------------|-------|-------------|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | Email backend |
| `EMAIL_HOST` | `smtp.gmail.com` | SMTP host |
| `EMAIL_HOST_USER` | `your-email@gmail.com` | Your email address |
| `EMAIL_HOST_PASSWORD` | `[Your App Password]` | Gmail app password |
| `SUPPORT_EMAIL` | `support@yourdomain.com` | Support email address |

### 3. Get Your SSH Private Key

On your local machine, find your SSH private key:
```bash
# If you used the default location
cat ~/.ssh/id_rsa

# Or if you created a specific key for this project
cat ~/.ssh/hetzner_key
```

Copy the entire private key content (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`) and paste it as the value for `HETZNER_SSH_KEY`.

## 🚀 **How It Works**

### Automatic Deployment:
- **Push to `master`** → Tests run → If tests pass → Auto-deploy to production
- **Push to `develop`** → Tests run only (no deployment)
- **Pull Request to `master`** → Tests run only (no deployment)

### Manual Deployment:
You can also trigger deployment manually:
1. Go to Actions tab in GitHub
2. Select "CI/CD Pipeline"
3. Click "Run workflow"
4. Choose branch and run

## 🔧 **Workflow Features**

### ✅ **Safety Features:**
- Tests must pass before deployment
- Only deploys from `master` branch
- Runs migrations automatically
- Collects static files automatically
- Checks container status after deployment

### 📊 **Monitoring:**
- View deployment logs in GitHub Actions
- Check container status after each deployment
- Automatic rollback if deployment fails

## 🛠 **Troubleshooting**

### If deployment fails:
1. Check GitHub Actions logs
2. SSH into your server and check:
   ```bash
   docker compose logs
   docker compose ps
   ```

### If tests fail:
1. Check the test logs in GitHub Actions
2. Run tests locally:
   ```bash
   python manage.py test
   ```

### If SSH connection fails:
1. Verify SSH key is correct
2. Test SSH connection manually:
   ```bash
   ssh root@128.140.40.7
   ```

## 📝 **Next Steps**

1. **Add the GitHub secrets** (most important!)
2. **Push a test commit** to trigger the pipeline
3. **Monitor the deployment** in GitHub Actions
4. **Verify your app** is working at `http://128.140.40.7`

## 🎯 **Benefits**

- **Automated testing** on every push
- **Zero-downtime deployments**
- **Automatic database migrations**
- **Static file collection**
- **Rollback capability**
- **Deployment history and logs**

Your Django app now has a professional CI/CD pipeline! 🚀
