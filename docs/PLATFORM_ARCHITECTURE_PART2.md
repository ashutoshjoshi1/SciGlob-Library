# SciGlob Real-Time Platform
## Technical Architecture Document - Part 2

---

## 6. Security Architecture

### 6.1 Authentication

#### 6.1.1 User Authentication Flow

```
┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│  Browser │      │   API    │      │   Auth   │      │ Database │
│          │      │  Server  │      │ Service  │      │          │
└────┬─────┘      └────┬─────┘      └────┬─────┘      └────┬─────┘
     │                 │                 │                 │
     │ POST /auth/login                  │                 │
     │ {email, password}                 │                 │
     │────────────────►│                 │                 │
     │                 │                 │                 │
     │                 │ Validate        │                 │
     │                 │ credentials     │                 │
     │                 │────────────────►│                 │
     │                 │                 │                 │
     │                 │                 │ Query user      │
     │                 │                 │────────────────►│
     │                 │                 │                 │
     │                 │                 │◄────────────────│
     │                 │                 │  User data      │
     │                 │                 │                 │
     │                 │                 │ Verify password │
     │                 │                 │ (bcrypt)        │
     │                 │                 │                 │
     │                 │◄────────────────│                 │
     │                 │  Generate JWT   │                 │
     │                 │  + Refresh Token│                 │
     │                 │                 │                 │
     │◄────────────────│                 │                 │
     │ {access_token,  │                 │                 │
     │  refresh_token, │                 │                 │
     │  user}          │                 │                 │
     │                 │                 │                 │
```

#### 6.1.2 JWT Token Structure

```json
// Access Token (expires in 15 minutes)
{
  "header": {
    "alg": "RS256",
    "typ": "JWT"
  },
  "payload": {
    "sub": "user_uuid",
    "email": "user@example.com",
    "role": "network_operator",
    "networks": ["network_uuid_1", "network_uuid_2"],
    "stations": [],
    "iat": 1701619200,
    "exp": 1701620100,
    "jti": "unique_token_id"
  }
}

// Refresh Token (expires in 7 days)
{
  "sub": "user_uuid",
  "type": "refresh",
  "iat": 1701619200,
  "exp": 1702224000,
  "jti": "unique_refresh_id"
}
```

#### 6.1.3 Station Authentication

```
┌──────────┐      ┌──────────┐      ┌──────────┐
│ Station  │      │   API    │      │   Redis  │
│  Agent   │      │  Server  │      │  (Cache) │
└────┬─────┘      └────┬─────┘      └────┬─────┘
     │                 │                 │
     │ WebSocket Connect                 │
     │ + API Key Header                  │
     │────────────────►│                 │
     │                 │                 │
     │                 │ Validate API Key│
     │                 │────────────────►│
     │                 │                 │
     │                 │◄────────────────│
     │                 │  Station info   │
     │                 │                 │
     │◄────────────────│                 │
     │ Connection      │                 │
     │ Accepted        │                 │
     │                 │                 │
     │ Station Info    │                 │
     │────────────────►│                 │
     │                 │                 │
     │◄────────────────│                 │
     │ Configuration   │                 │
     │                 │                 │
```

### 6.2 Authorization (RBAC)

#### 6.2.1 Permission Definitions

```python
# Permission matrix
PERMISSIONS = {
    "admin": {
        "stations": ["read", "write", "delete", "control"],
        "users": ["read", "write", "delete"],
        "networks": ["read", "write", "delete"],
        "alerts": ["read", "write", "delete", "acknowledge"],
        "data": ["read", "export"],
        "settings": ["read", "write"],
        "audit": ["read"],
    },
    "network_operator": {
        "stations": ["read", "write", "control"],  # Own network only
        "users": ["read"],  # Own network only
        "networks": ["read"],  # Own network only
        "alerts": ["read", "write", "acknowledge"],  # Own network only
        "data": ["read", "export"],  # Own network only
        "settings": [],
        "audit": ["read"],  # Own network only
    },
    "local_operator": {
        "stations": ["read", "control"],  # Assigned stations only
        "users": [],
        "networks": [],
        "alerts": ["read", "acknowledge"],  # Assigned stations only
        "data": ["read"],  # Assigned stations only, limited history
        "settings": [],
        "audit": [],
    },
}
```

#### 6.2.2 Access Control Implementation

```python
# Dependency injection for permission checking
from fastapi import Depends, HTTPException, status
from typing import List

class PermissionChecker:
    def __init__(self, required_permissions: List[str]):
        self.required = required_permissions
    
    async def __call__(
        self, 
        current_user: User = Depends(get_current_user),
        station_id: UUID = None,
        network_id: UUID = None,
    ) -> User:
        user_role = current_user.role
        
        # Admin has all permissions
        if user_role == "admin":
            return current_user
        
        # Check network access for network operators
        if user_role == "network_operator":
            if network_id and network_id not in current_user.network_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this network"
                )
            if station_id:
                station = await get_station(station_id)
                if station.network_id not in current_user.network_ids:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied to this station"
                    )
        
        # Check station access for local operators
        if user_role == "local_operator":
            if station_id and station_id not in current_user.station_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this station"
                )
        
        return current_user

# Usage in endpoints
@router.get("/stations/{station_id}")
async def get_station(
    station_id: UUID,
    user: User = Depends(PermissionChecker(["stations:read"]))
):
    ...

@router.post("/stations/{station_id}/command")
async def send_command(
    station_id: UUID,
    command: Command,
    user: User = Depends(PermissionChecker(["stations:control"]))
):
    ...
```

### 6.3 Data Security

#### 6.3.1 Encryption

| Data Type | At Rest | In Transit |
|-----------|---------|------------|
| Passwords | bcrypt (cost 12) | TLS 1.3 |
| API Keys | SHA-256 hash | TLS 1.3 |
| Measurement Data | Database encryption | TLS 1.3 |
| Session Data | Redis encryption | TLS 1.3 |
| Backups | AES-256 | TLS 1.3 |

#### 6.3.2 API Security

```python
# Rate limiting configuration
RATE_LIMITS = {
    "default": "100/minute",
    "auth/login": "5/minute",
    "auth/register": "3/hour",
    "data/export": "10/hour",
    "commands": "30/minute",
}

# CORS configuration
CORS_CONFIG = {
    "allow_origins": [
        "https://dashboard.sciglob.example.com",
    ],
    "allow_methods": ["GET", "POST", "PUT", "DELETE"],
    "allow_headers": ["Authorization", "Content-Type"],
    "allow_credentials": True,
}

# Security headers
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
}
```

---

## 7. API Specifications

### 7.1 REST API Endpoints

#### 7.1.1 Authentication

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/v1/auth/login` | User login | No |
| POST | `/api/v1/auth/refresh` | Refresh token | Refresh |
| POST | `/api/v1/auth/logout` | Logout | Yes |
| POST | `/api/v1/auth/password/reset` | Request reset | No |
| POST | `/api/v1/auth/password/change` | Change password | Yes |

#### 7.1.2 Stations

| Method | Endpoint | Description | Access |
|--------|----------|-------------|--------|
| GET | `/api/v1/stations` | List stations | All |
| GET | `/api/v1/stations/{id}` | Get station | All |
| POST | `/api/v1/stations` | Create station | Admin |
| PUT | `/api/v1/stations/{id}` | Update station | Admin, NetOp |
| DELETE | `/api/v1/stations/{id}` | Delete station | Admin |
| GET | `/api/v1/stations/{id}/status` | Get live status | All |
| POST | `/api/v1/stations/{id}/command` | Send command | All (own) |
| GET | `/api/v1/stations/{id}/commands` | Command history | All (own) |

#### 7.1.3 Data

| Method | Endpoint | Description | Access |
|--------|----------|-------------|--------|
| GET | `/api/v1/data/stations/{id}` | Get measurements | All (own) |
| GET | `/api/v1/data/stations/{id}/latest` | Latest reading | All (own) |
| GET | `/api/v1/data/export` | Export data | Admin, NetOp |
| GET | `/api/v1/data/aggregates` | Aggregated data | All |

#### 7.1.4 Users

| Method | Endpoint | Description | Access |
|--------|----------|-------------|--------|
| GET | `/api/v1/users` | List users | Admin |
| GET | `/api/v1/users/{id}` | Get user | Admin, Self |
| POST | `/api/v1/users` | Create user | Admin |
| PUT | `/api/v1/users/{id}` | Update user | Admin, Self |
| DELETE | `/api/v1/users/{id}` | Delete user | Admin |
| PUT | `/api/v1/users/{id}/assignments` | Update assignments | Admin |

#### 7.1.5 Networks

| Method | Endpoint | Description | Access |
|--------|----------|-------------|--------|
| GET | `/api/v1/networks` | List networks | All |
| GET | `/api/v1/networks/{id}` | Get network | All (own) |
| POST | `/api/v1/networks` | Create network | Admin |
| PUT | `/api/v1/networks/{id}` | Update network | Admin |
| DELETE | `/api/v1/networks/{id}` | Delete network | Admin |
| GET | `/api/v1/networks/{id}/stations` | Get stations | All (own) |

#### 7.1.6 Alerts

| Method | Endpoint | Description | Access |
|--------|----------|-------------|--------|
| GET | `/api/v1/alerts` | List alerts | All (own) |
| GET | `/api/v1/alerts/{id}` | Get alert | All (own) |
| PUT | `/api/v1/alerts/{id}/acknowledge` | Acknowledge | All (own) |
| GET | `/api/v1/alerts/rules` | List rules | Admin, NetOp |
| POST | `/api/v1/alerts/rules` | Create rule | Admin, NetOp |
| PUT | `/api/v1/alerts/rules/{id}` | Update rule | Admin, NetOp |
| DELETE | `/api/v1/alerts/rules/{id}` | Delete rule | Admin, NetOp |

### 7.2 WebSocket Events

#### 7.2.1 Station → Server

| Event | Payload | Description |
|-------|---------|-------------|
| `data` | MessagePack batch | Measurement data |
| `status` | JSON | Station status update |
| `command_response` | JSON | Response to command |
| `error` | JSON | Error report |

#### 7.2.2 Server → Station

| Event | Payload | Description |
|-------|---------|-------------|
| `command` | JSON | Command to execute |
| `config_update` | JSON | Configuration change |
| `ping` | - | Keep-alive ping |

#### 7.2.3 Server → Dashboard

| Event | Payload | Description |
|-------|---------|-------------|
| `station:data` | JSON | Real-time station data |
| `station:status` | JSON | Station status change |
| `station:connected` | JSON | Station came online |
| `station:disconnected` | JSON | Station went offline |
| `alert:new` | JSON | New alert triggered |
| `alert:resolved` | JSON | Alert resolved |

#### 7.2.4 Dashboard → Server

| Event | Payload | Description |
|-------|---------|-------------|
| `subscribe` | JSON | Subscribe to stations |
| `unsubscribe` | JSON | Unsubscribe from stations |

### 7.3 API Response Formats

#### 7.3.1 Success Response

```json
{
  "success": true,
  "data": {
    // Response data
  },
  "meta": {
    "timestamp": "2024-12-03T12:00:00Z",
    "request_id": "req_abc123"
  }
}
```

#### 7.3.2 Paginated Response

```json
{
  "success": true,
  "data": [
    // Array of items
  ],
  "meta": {
    "total": 300,
    "page": 1,
    "per_page": 50,
    "total_pages": 6
  }
}
```

#### 7.3.3 Error Response

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": [
      {
        "field": "email",
        "message": "Invalid email format"
      }
    ]
  },
  "meta": {
    "timestamp": "2024-12-03T12:00:00Z",
    "request_id": "req_abc123"
  }
}
```

---

## 8. Deployment Architecture

### 8.1 Infrastructure Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD PROVIDER                                  │
│                         (AWS / GCP / Azure)                                 │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         KUBERNETES CLUSTER                             │ │
│  │                                                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                    INGRESS CONTROLLER                           │  │ │
│  │  │                  (NGINX Ingress + Cert Manager)                 │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  │                               │                                        │ │
│  │          ┌────────────────────┼────────────────────┐                  │ │
│  │          ▼                    ▼                    ▼                  │ │
│  │  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐           │ │
│  │  │ API Service │      │ API Service │      │ API Service │           │ │
│  │  │  (Pod x3)   │      │  (Pod x3)   │      │  (Pod x3)   │           │ │
│  │  │             │      │             │      │             │           │ │
│  │  │ ┌─────────┐ │      │ ┌─────────┐ │      │ ┌─────────┐ │           │ │
│  │  │ │ FastAPI │ │      │ │ FastAPI │ │      │ │ FastAPI │ │           │ │
│  │  │ └─────────┘ │      │ └─────────┘ │      │ └─────────┘ │           │ │
│  │  └─────────────┘      └─────────────┘      └─────────────┘           │ │
│  │                               │                                        │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                    WORKER DEPLOYMENTS                           │  │ │
│  │  │                                                                  │  │ │
│  │  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │  │ │
│  │  │  │ Ingestion  │  │   Alert    │  │   Email    │                │  │ │
│  │  │  │  Workers   │  │  Workers   │  │  Workers   │                │  │ │
│  │  │  │  (x5)      │  │  (x2)      │  │  (x2)      │                │  │ │
│  │  │  └────────────┘  └────────────┘  └────────────┘                │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       MANAGED SERVICES                                 │ │
│  │                                                                         │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐       │ │
│  │  │   Redis    │  │ TimescaleDB│  │ PostgreSQL │  │    S3      │       │ │
│  │  │  Cluster   │  │  (Managed) │  │  (Managed) │  │  Backups   │       │ │
│  │  │            │  │            │  │            │  │            │       │ │
│  │  │  6 nodes   │  │  2TB SSD   │  │  100GB     │  │  Archive   │       │ │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘       │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

              │                                              │
              │ HTTPS                                        │ WSS
              ▼                                              ▼
     ┌─────────────────┐                          ┌─────────────────┐
     │  Web Dashboard  │                          │  Station Agents │
     │   (Browsers)    │                          │   (300+ PCs)    │
     └─────────────────┘                          └─────────────────┘
```

### 8.2 Kubernetes Manifests

#### 8.2.1 API Server Deployment

```yaml
# kubernetes/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sciglob-api
  namespace: sciglob
spec:
  replicas: 3
  selector:
    matchLabels:
      app: sciglob-api
  template:
    metadata:
      labels:
        app: sciglob-api
    spec:
      containers:
      - name: api
        image: sciglob/api:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: sciglob-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: sciglob-secrets
              key: redis-url
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: sciglob-secrets
              key: jwt-secret
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2000m"
            memory: "2Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: sciglob-api
  namespace: sciglob
spec:
  selector:
    app: sciglob-api
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
```

### 8.3 Docker Configuration

#### 8.3.1 API Server Dockerfile

```dockerfile
# server/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 8.3.2 Station Agent Dockerfile

```dockerfile
# station-agent/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for serial communication
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent/ ./agent/
COPY config.yaml .

# Run agent
CMD ["python", "-m", "agent.main"]
```

### 8.4 Cost Estimation (Monthly)

| Resource | Specification | AWS | GCP | Azure |
|----------|--------------|-----|-----|-------|
| **Kubernetes Cluster** | 3 nodes, c5.xlarge | $350 | $320 | $340 |
| **API Pods** | 9 pods | (included) | (included) | (included) |
| **Worker Pods** | 9 pods | (included) | (included) | (included) |
| **TimescaleDB** | 2TB, High Memory | $500 | $480 | $520 |
| **PostgreSQL** | 100GB, Standard | $80 | $75 | $85 |
| **Redis Cluster** | 6 nodes, r5.large | $450 | $420 | $460 |
| **Load Balancer** | Application LB | $50 | $45 | $55 |
| **Data Transfer** | ~500 GB/month | $45 | $40 | $50 |
| **S3 Storage** | 1TB backups | $25 | $20 | $25 |
| **Monitoring** | CloudWatch/Stackdriver | $50 | $45 | $50 |
| **Email (SendGrid)** | 100K emails | $15 | $15 | $15 |
| **SSL Certificates** | Wildcard | $0 (Let's Encrypt) | $0 | $0 |
| **TOTAL** | | **~$1,565** | **~$1,460** | **~$1,600** |

---

## 9. Development Roadmap

### 9.1 Phase Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEVELOPMENT TIMELINE                                 │
│                                                                              │
│  Week 1-2          Week 3-4          Week 5           Week 6                │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐     ┌──────────┐         │
│  │ PHASE 1  │      │ PHASE 2  │      │ PHASE 3  │     │ PHASE 4  │         │
│  │Foundation│─────►│ Scale &  │─────►│   User   │────►│ Control  │         │
│  │          │      │Reliability│      │Management│     │& Commands│         │
│  └──────────┘      └──────────┘      └──────────┘     └──────────┘         │
│                                                                              │
│  Week 7            Week 8            Week 9-10                               │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐                           │
│  │ PHASE 5  │      │ PHASE 6  │      │ PHASE 7  │                           │
│  │Historical│─────►│ Alerts & │─────►│Production│                           │
│  │   Data   │      │  Email   │      │  Ready   │                           │
│  └──────────┘      └──────────┘      └──────────┘                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Detailed Phase Breakdown

#### Phase 1: Foundation (Week 1-2)

| Task | Priority | Estimate |
|------|----------|----------|
| Project setup (repos, CI/CD) | Critical | 4h |
| Database schema implementation | Critical | 8h |
| Station agent core (collector) | Critical | 16h |
| Server WebSocket handler | Critical | 16h |
| Basic data pipeline | Critical | 8h |
| Simple dashboard (stations list) | High | 16h |
| Unit tests | High | 8h |

**Deliverable:** Single station sending data to server, visible on dashboard.

#### Phase 2: Scale & Reliability (Week 3-4)

| Task | Priority | Estimate |
|------|----------|----------|
| Redis pub/sub integration | Critical | 12h |
| Multiple server instances | Critical | 8h |
| Load balancer configuration | Critical | 4h |
| Station reconnection handling | Critical | 8h |
| Data batching optimization | High | 8h |
| MessagePack integration | High | 4h |
| Ingestion workers | High | 12h |
| Performance testing (100 stations) | High | 8h |

**Deliverable:** System handling 100+ concurrent stations.

#### Phase 3: User Management (Week 5)

| Task | Priority | Estimate |
|------|----------|----------|
| User authentication (JWT) | Critical | 12h |
| Role-based access control | Critical | 16h |
| User management UI | Critical | 16h |
| Network/station assignments | High | 8h |
| Password reset flow | Medium | 4h |

**Deliverable:** Complete user management with 3 roles.

#### Phase 4: Control & Commands (Week 6)

| Task | Priority | Estimate |
|------|----------|----------|
| Command infrastructure | Critical | 12h |
| Tracker control UI | Critical | 8h |
| Filter wheel control UI | Critical | 4h |
| Command acknowledgment | Critical | 8h |
| Command history | High | 4h |
| Command queue (offline) | Medium | 8h |

**Deliverable:** Remote control of all station hardware.

#### Phase 5: Historical Data (Week 7)

| Task | Priority | Estimate |
|------|----------|----------|
| TimescaleDB integration | Critical | 12h |
| Historical data queries API | Critical | 8h |
| Time-series charts | Critical | 16h |
| Data export (CSV, JSON) | High | 8h |
| Continuous aggregates | High | 4h |
| Data retention policies | Medium | 4h |

**Deliverable:** Historical data viewing and export.

#### Phase 6: Alerts & Email (Week 8)

| Task | Priority | Estimate |
|------|----------|----------|
| Alert rule engine | Critical | 16h |
| Email worker (Celery) | Critical | 8h |
| SendGrid/SES integration | Critical | 4h |
| Alert dashboard UI | Critical | 12h |
| Alert rule configuration UI | High | 8h |
| Alert history | High | 4h |

**Deliverable:** Automated alerting with email notifications.

#### Phase 7: Production (Week 9-10)

| Task | Priority | Estimate |
|------|----------|----------|
| Docker containerization | Critical | 8h |
| Kubernetes deployment | Critical | 16h |
| SSL/TLS configuration | Critical | 4h |
| Monitoring setup (Prometheus) | Critical | 8h |
| Grafana dashboards | High | 8h |
| Load testing (300+ stations) | Critical | 16h |
| Security audit | Critical | 8h |
| Documentation | Critical | 16h |
| Deployment runbook | High | 8h |

**Deliverable:** Production-ready system deployed.

### 9.3 Total Effort Estimate

| Phase | Hours | Team Size | Duration |
|-------|-------|-----------|----------|
| Phase 1 | 76h | 2 devs | 1 week |
| Phase 2 | 64h | 2 devs | 1 week |
| Phase 3 | 56h | 2 devs | 1 week |
| Phase 4 | 44h | 2 devs | 1 week |
| Phase 5 | 52h | 2 devs | 1 week |
| Phase 6 | 52h | 2 devs | 1 week |
| Phase 7 | 92h | 2 devs | 2 weeks |
| **TOTAL** | **436h** | | **10 weeks** |

---

## 10. Appendices

### 10.1 Glossary

| Term | Definition |
|------|------------|
| Station | A measurement site with SciGlob hardware |
| Agent | Software running on station PC |
| Network | A group of related stations |
| Tracker | Pan/tilt motor controller |
| Filter Wheel | Rotatable filter holder |
| Hypertable | TimescaleDB partitioned table |
| RBAC | Role-Based Access Control |
| WSS | WebSocket Secure (TLS) |

### 10.2 Reference Documents

| Document | Location |
|----------|----------|
| SciGlob Library API | `docs/API_REFERENCE.md` |
| SciGlob Quick Reference | `docs/QUICK_REFERENCE.md` |
| Command Reference | `SCIGLOB_COMMAND_REFERENCE.md` |
| Library Specification | `SCIGLOB_LIBRARY_SPEC.md` |

### 10.3 External Resources

| Resource | URL |
|----------|-----|
| FastAPI Documentation | https://fastapi.tiangolo.com |
| TimescaleDB Documentation | https://docs.timescale.com |
| Socket.IO Documentation | https://socket.io/docs |
| Kubernetes Documentation | https://kubernetes.io/docs |

### 10.4 Contact Information

| Role | Contact |
|------|---------|
| Project Lead | TBD |
| Technical Lead | TBD |
| DevOps Lead | TBD |

---

*Document Version: 1.0*  
*Last Updated: December 2024*  
*Status: Draft*

