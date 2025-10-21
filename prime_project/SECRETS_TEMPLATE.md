# GitHub Secrets Template

## 🔐 **Complete List of Required GitHub Secrets**

Add these secrets to your GitHub repository at:
`https://github.com/arian-hadi/Custom-Events/settings/secrets/actions`

### **1. Server Access (3 secrets)**
```
HETZNER_HOST = 128.140.40.7
HETZNER_USERNAME = root
HETZNER_SSH_KEY = [Your SSH private key content]
```

### **2. Django Configuration (3 secrets)**
```
DJANGO_SECRET_KEY = [Generate a secure secret key]
ALLOWED_HOSTS = yourdomain.com,www.yourdomain.com,128.140.40.7,localhost
CSRF_TRUSTED_ORIGINS = https://yourdomain.com,https://www.yourdomain.com,http://128.140.40.7
```

### **3. Database Configuration (3 secrets)**
```
DB_NAME = postgres
DB_USER = postgres
DB_PASSWORD = [Your secure database password]
```

### **4. Email Configuration (5 secrets)**
```
EMAIL_BACKEND = django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST = smtp.gmail.com
EMAIL_HOST_USER = your-email@gmail.com
EMAIL_HOST_PASSWORD = [Your Gmail app password]
SUPPORT_EMAIL = support@yourdomain.com
```

## 🛠 **How to Get These Values**

### **Django Secret Key:**
```python
# Run this in Python to generate a secure key
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

### **SSH Private Key:**
```bash
# On your local machine
cat ~/.ssh/id_rsa
# Copy the entire content including -----BEGIN and -----END lines
```

### **Gmail App Password:**
1. Go to Google Account settings
2. Security → 2-Step Verification → App passwords
3. Generate a new app password for "Mail"
4. Use this password (not your regular Gmail password)

### **Domain Configuration:**
Replace `yourdomain.com` with your actual domain name.

## 📝 **Example Values (Replace with your actual values)**

```
HETZNER_HOST = 128.140.40.7
HETZNER_USERNAME = root
HETZNER_SSH_KEY = -----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAlwAAAAdzc2gtcn
...
-----END OPENSSH PRIVATE KEY-----

DJANGO_SECRET_KEY = djangosecretkey123456789abcdefghijklmnopqrstuvwxyz
ALLOWED_HOSTS = mydomain.com,www.mydomain.com,128.140.40.7,localhost
CSRF_TRUSTED_ORIGINS = https://mydomain.com,https://www.mydomain.com,http://128.140.40.7

DB_NAME = postgres
DB_USER = postgres
DB_PASSWORD = mySecureDBPassword123

EMAIL_BACKEND = django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST = smtp.gmail.com
EMAIL_HOST_USER = myemail@gmail.com
EMAIL_HOST_PASSWORD = mygmailapppassword123456
SUPPORT_EMAIL = support@mydomain.com
```

## ✅ **Security Best Practices**

1. **Never commit secrets to Git** - They're only stored in GitHub Secrets
2. **Use strong passwords** - At least 16 characters with mixed case, numbers, symbols
3. **Rotate secrets regularly** - Update them every 3-6 months
4. **Use app passwords** - Never use your main email password
5. **Limit access** - Only add team members who need deployment access

## 🔄 **How It Works**

1. **GitHub Actions** reads these secrets during deployment
2. **Creates .env.prod** file dynamically on your server
3. **Docker containers** use the environment variables
4. **Secrets are never logged** or exposed in the deployment process

## 🚨 **Important Notes**

- **Replace all placeholder values** with your actual credentials
- **Test with a non-production domain** first if possible
- **Keep your SSH key secure** - it provides full server access
- **Monitor deployment logs** to ensure secrets are working correctly

Your deployment will be completely secure with all credentials managed through GitHub Secrets! 🔐
