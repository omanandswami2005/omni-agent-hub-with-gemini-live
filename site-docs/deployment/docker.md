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

## Docker Compose Configuration

See [deploy/docker-compose.yml](https://github.com/omni-docs/omni-docs.github.io/blob/main/deploy/docker-compose.yml) for the full multi-service configuration.
