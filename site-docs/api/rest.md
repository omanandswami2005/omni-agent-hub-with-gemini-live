# REST API Reference

!!! info "Interactive docs"
    The full interactive Swagger UI is available at `http://localhost:8000/docs` when running the backend.

## Endpoints

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Cloud Run healthcheck |

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/verify` | Firebase token verification |

### Personas

| Method | Path | Description |
|---|---|---|
| `GET` | `/personas` | List all personas |
| `POST` | `/personas` | Create a persona |
| `PUT` | `/personas/{id}` | Update a persona |
| `DELETE` | `/personas/{id}` | Delete a persona |

### Sessions

| Method | Path | Description |
|---|---|---|
| `GET` | `/sessions` | List session history |
| `DELETE` | `/sessions/{id}` | Delete a session |

### Plugins

| Method | Path | Description |
|---|---|---|
| `GET` | `/plugins` | Plugin catalog (all available) |
| `POST` | `/plugins` | Toggle plugin on/off |
| `POST` | `/plugins/{id}/secrets` | Set plugin secrets |
| `GET` | `/plugins/{id}/tools` | List tools for a plugin |
| `POST` | `/plugins/{id}/oauth/start` | Start OAuth flow |
| `GET` | `/plugins/oauth/callback` | OAuth callback |
| `POST` | `/plugins/{id}/oauth/disconnect` | Revoke OAuth |

### Clients

| Method | Path | Description |
|---|---|---|
| `GET` | `/clients` | List connected devices |

### Tasks

| Method | Path | Description |
|---|---|---|
| `POST` | `/tasks/desktop/upload` | Upload file to E2B desktop |
