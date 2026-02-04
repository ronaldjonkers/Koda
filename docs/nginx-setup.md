# Nginx Reverse Proxy Setup for Koda

This guide explains how to securely expose Koda to the internet using Nginx as a reverse proxy with SSL.

## Why Use a Reverse Proxy?

By default, Koda only listens on `localhost` for security. To access it remotely:
- ✅ Use Nginx as a reverse proxy (recommended)
- ✅ Handle SSL/TLS termination
- ✅ Add rate limiting and security headers
- ✅ Serve multiple services on one server

## Quick Setup

### 1. Install Nginx

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install nginx certbot python3-certbot-nginx

# macOS
brew install nginx
```

### 2. Create Nginx Configuration

Create `/etc/nginx/sites-available/koda`:

```nginx
# Koda Dashboard and Gateway
server {
    listen 80;
    server_name koda.yourdomain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name koda.yourdomain.com;

    # SSL Configuration (Certbot will add these)
    ssl_certificate /etc/letsencrypt/live/koda.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/koda.yourdomain.com/privkey.pem;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Dashboard (port 8081)
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Gateway API (port 18790)
    location /api/gateway/ {
        proxy_pass http://127.0.0.1:18790/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Webhook API (if using reminder webhooks)
    location /api/webhook/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=koda:10m rate=10r/s;
    limit_req zone=koda burst=20 nodelay;
}
```

### 3. Enable the Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/koda /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### 4. Get SSL Certificate

```bash
sudo certbot --nginx -d koda.yourdomain.com
```

### 5. Start Koda as Daemon

```bash
# Install Koda as a system service
koda daemon install

# Start the service
koda daemon start

# Check status
koda daemon status
```

## Alternative: Simple Setup (Development Only)

For local development without SSL:

```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Security Considerations

### Basic Authentication (Optional)

Add password protection to the dashboard:

```bash
# Create password file
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

Add to Nginx config:
```nginx
location / {
    auth_basic "Koda Dashboard";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    proxy_pass http://127.0.0.1:8081;
    # ... rest of config
}
```

### IP Whitelisting

Restrict access to specific IPs:

```nginx
location / {
    allow 192.168.1.0/24;  # Local network
    allow 1.2.3.4;          # Your IP
    deny all;
    
    proxy_pass http://127.0.0.1:8081;
}
```

### Firewall Setup

```bash
# Ubuntu with UFW
sudo ufw allow 'Nginx Full'
sudo ufw enable

# Check status
sudo ufw status
```

## Troubleshooting

### Check Nginx Logs

```bash
# Error log
sudo tail -f /var/log/nginx/error.log

# Access log
sudo tail -f /var/log/nginx/access.log
```

### Check Koda Status

```bash
# Service status
koda daemon status

# Koda logs
koda daemon logs -n 100
```

### Common Issues

1. **502 Bad Gateway**: Koda service not running
   ```bash
   koda daemon start
   ```

2. **Connection refused**: Wrong port or service down
   ```bash
   curl http://127.0.0.1:8081/api/status
   ```

3. **SSL certificate issues**: Renew certificate
   ```bash
   sudo certbot renew
   ```

## Docker Compose (Alternative)

For Docker deployments, see `docker-compose.yml`:

```yaml
version: '3.8'
services:
  koda:
    build: .
    ports:
      - "127.0.0.1:8081:8081"
      - "127.0.0.1:18790:18790"
    volumes:
      - ~/.koda:/root/.koda
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - koda
    restart: unless-stopped
```

## Next Steps

1. Configure DNS to point to your server
2. Set up SSL with Certbot
3. Enable Koda daemon for auto-start
4. Configure firewall rules
5. Set up monitoring (optional)

For more help, see the main [README.md](../README.md) or ask Koda via WhatsApp!
