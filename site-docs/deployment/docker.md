# Docker Deployment

## Using Docker Compose

```bash
cd deploy
docker-compose up -d
```

## Building Images

### Backend

```bash
cd backend
docker build -t omni-backend .
docker run -p 8000:8000 --env-file .env omni-backend
```

### Dashboard

```bash
cd dashboard
docker build -t omni-dashboard .
docker run -p 80:80 omni-dashboard
```
