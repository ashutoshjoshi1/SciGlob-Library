# SciGlob Real-Time Platform
## Technical Architecture Document

**Version:** 1.0  
**Date:** December 2024  
**Author:** SciGlob Engineering Team

---

## Document Information

| Field | Value |
|-------|-------|
| Document Type | Technical Architecture Specification |
| Status | Draft |
| Confidentiality | Internal |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Requirements](#2-system-requirements)
3. [Architecture Overview](#3-architecture-overview)
4. [Component Specifications](#4-component-specifications)
5. [Data Architecture](#5-data-architecture)
6. [Security Architecture](#6-security-architecture)
7. [API Specifications](#7-api-specifications)
8. [Deployment Architecture](#8-deployment-architecture)
9. [Development Roadmap](#9-development-roadmap)
10. [Appendices](#10-appendices)

---

## 1. Executive Summary

### 1.1 Purpose

This document provides the complete technical architecture for the SciGlob Real-Time Platform, a distributed system designed to:

- Connect and monitor 300+ remote measurement stations
- Collect high-frequency scientific instrument data in real-time
- Provide a centralized web dashboard for monitoring and control
- Store historical data for analysis and reporting
- Alert operators via email when anomalies occur

### 1.2 Scope

The platform encompasses:

- **Station Agents**: Software running on each measurement station PC
- **Central Server**: Cloud-based infrastructure for data processing
- **Web Dashboard**: Browser-based user interface
- **Data Storage**: Time-series and relational databases
- **Alert System**: Automated monitoring and email notifications

### 1.3 Key Metrics

| Metric | Target |
|--------|--------|
| Concurrent Stations | 300+ |
| Data Frequency | 50-100 Hz per station |
| End-to-End Latency | < 200ms |
| Data Throughput | 15,000+ readings/second |
| System Uptime | 99.9% |
| Data Retention | 1 year minimum |

---

## 2. System Requirements

### 2.1 Functional Requirements

#### 2.1.1 Station Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-SM-001 | System shall support 300+ simultaneous station connections | Critical |
| FR-SM-002 | System shall auto-detect station connection/disconnection | Critical |
| FR-SM-003 | System shall display station status (online/offline/error) | Critical |
| FR-SM-004 | System shall support station configuration via web interface | High |
| FR-SM-005 | System shall group stations by network/region | High |
| FR-SM-006 | System shall display station geographic location on map | Medium |

#### 2.1.2 Data Collection

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-DC-001 | System shall collect tracker position data at 50+ Hz | Critical |
| FR-DC-002 | System shall collect sensor data (temp, humidity, pressure) | Critical |
| FR-DC-003 | System shall collect filter wheel position | Critical |
| FR-DC-004 | System shall buffer data during network interruptions | Critical |
| FR-DC-005 | System shall timestamp all readings with microsecond precision | Critical |
| FR-DC-006 | System shall validate incoming data format | High |

#### 2.1.3 Remote Control

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-RC-001 | System shall allow remote tracker movement commands | Critical |
| FR-RC-002 | System shall allow remote filter wheel changes | Critical |
| FR-RC-003 | System shall provide command acknowledgment | Critical |
| FR-RC-004 | System shall queue commands during station offline | High |
| FR-RC-005 | System shall support command timeout and retry | High |

#### 2.1.4 User Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-UM-001 | System shall support Admin role with full access | Critical |
| FR-UM-002 | System shall support Network Operator role | Critical |
| FR-UM-003 | System shall support Local Operator role | Critical |
| FR-UM-004 | System shall enforce role-based access control | Critical |
| FR-UM-005 | System shall support password reset via email | High |
| FR-UM-006 | System shall log all user actions for audit | High |

#### 2.1.5 Alerting

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-AL-001 | System shall send email alerts for critical events | Critical |
| FR-AL-002 | System shall allow configurable alert rules | High |
| FR-AL-003 | System shall prevent alert flooding (rate limiting) | High |
| FR-AL-004 | System shall maintain alert history | High |
| FR-AL-005 | System shall support alert acknowledgment | Medium |

### 2.2 Non-Functional Requirements

#### 2.2.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-P-001 | Dashboard page load time | < 2 seconds |
| NFR-P-002 | Real-time data update latency | < 200ms |
| NFR-P-003 | Command execution latency | < 500ms |
| NFR-P-004 | Historical data query (1 day) | < 5 seconds |
| NFR-P-005 | Concurrent dashboard users | 100+ |

#### 2.2.2 Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-R-001 | System uptime | 99.9% |
| NFR-R-002 | Data loss during network issues | 0% (buffered) |
| NFR-R-003 | Mean time to recovery | < 5 minutes |
| NFR-R-004 | Automatic failover | Yes |

#### 2.2.3 Security

| ID | Requirement |
|----|-------------|
| NFR-S-001 | All communications encrypted (TLS 1.3) |
| NFR-S-002 | Authentication required for all operations |
| NFR-S-003 | Passwords hashed with bcrypt |
| NFR-S-004 | JWT tokens with 24-hour expiration |
| NFR-S-005 | API rate limiting enabled |

---

## 3. Architecture Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   INTERNET                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
         │                              │                              │
         │                              │                              │
         ▼                              ▼                              ▼
┌─────────────────┐          ┌─────────────────────────────────────────────────────┐
│  STATION AGENT  │          │                  CLOUD PLATFORM                     │
│  (PC at Site)   │          │  ┌─────────────────────────────────────────────┐   │
│                 │          │  │              LOAD BALANCER                   │   │
│ ┌─────────────┐ │          │  │            (NGINX / HAProxy)                │   │
│ │  SciGlob    │ │          │  └─────────────────────────────────────────────┘   │
│ │  Library    │ │          │                      │                             │
│ └─────────────┘ │          │     ┌────────────────┼────────────────┐           │
│       │         │          │     ▼                ▼                ▼           │
│       ▼         │  WSS     │  ┌──────┐        ┌──────┐        ┌──────┐        │
│ ┌─────────────┐ │◄────────►│  │ API  │        │ API  │        │ API  │        │
│ │  Connection │ │          │  │Server│        │Server│        │Server│        │
│ │  Manager    │ │          │  │  1   │        │  2   │        │  N   │        │
│ └─────────────┘ │          │  └──────┘        └──────┘        └──────┘        │
│       │         │          │     │                │                │           │
│       ▼         │          │     └────────────────┼────────────────┘           │
│ ┌─────────────┐ │          │                      │                             │
│ │   Data      │ │          │     ┌────────────────┼────────────────┐           │
│ │  Collector  │ │          │     ▼                ▼                ▼           │
│ └─────────────┘ │          │  ┌──────┐        ┌──────┐        ┌──────┐        │
│       │         │          │  │Redis │        │Timesc│        │Postgr│        │
│       ▼         │          │  │Clust.│        │aleDB │        │esSQL │        │
│ ┌─────────────┐ │          │  └──────┘        └──────┘        └──────┘        │
│ │  Hardware   │ │          │                                                    │
│ └─────────────┘ │          └────────────────────────────────────────────────────┘
└─────────────────┘
                                         │
                                         │ HTTPS
                                         ▼
                             ┌───────────────────────┐
                             │    WEB DASHBOARD      │
                             │    (React App)        │
                             │    in Browser         │
                             └───────────────────────┘
```

### 3.2 Technology Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| **Station Agent** | Python | 3.11+ | Hardware communication |
| | asyncio + uvloop | - | High-performance async |
| | websockets | 12.0+ | Server connection |
| | msgpack | 1.0+ | Binary serialization |
| **API Server** | FastAPI | 0.100+ | REST API + WebSocket |
| | Uvicorn | 0.24+ | ASGI server |
| | SQLAlchemy | 2.0+ | Database ORM |
| | Pydantic | 2.0+ | Data validation |
| **Message Broker** | Redis | 7.0+ | Pub/Sub, caching |
| | Redis Streams | - | Message queuing |
| **Databases** | TimescaleDB | 2.12+ | Time-series data |
| | PostgreSQL | 15+ | Relational data |
| **Frontend** | React | 18+ | UI framework |
| | Socket.IO Client | 4.0+ | WebSocket client |
| | TanStack Query | 5.0+ | Data fetching |
| | Recharts | 2.0+ | Charts |
| **Workers** | Celery | 5.3+ | Background tasks |
| | Redis | - | Task broker |
| **Email** | SendGrid | - | Email delivery |
| **Infrastructure** | Docker | 24+ | Containerization |
| | Kubernetes | 1.28+ | Orchestration |
| | NGINX | 1.25+ | Load balancer |

### 3.3 Communication Protocols

#### 3.3.1 Station ↔ Server

| Protocol | Format | Use Case |
|----------|--------|----------|
| WebSocket (WSS) | MessagePack | Real-time data streaming |
| WebSocket (WSS) | JSON | Commands and responses |

**Connection Flow:**

```
Station                                          Server
   │                                                │
   │─────────── WSS Connect + API Key ─────────────►│
   │                                                │
   │◄────────── Connection Accepted ───────────────│
   │                                                │
   │─────────── Station Info (JSON) ───────────────►│
   │                                                │
   │◄────────── Configuration (JSON) ──────────────│
   │                                                │
   │══════════ Data Stream (MessagePack) ══════════►│
   │              (continuous, batched)             │
   │                                                │
   │◄═══════════ Commands (JSON) ══════════════════│
   │                                                │
   │─────────── Command Response (JSON) ───────────►│
   │                                                │
```

#### 3.3.2 Dashboard ↔ Server

| Protocol | Format | Use Case |
|----------|--------|----------|
| HTTPS | JSON | REST API calls |
| WebSocket (WSS) | JSON | Real-time updates |

---

## 4. Component Specifications

### 4.1 Station Agent

#### 4.1.1 Overview

The Station Agent is a Python application that runs on each measurement station PC. It interfaces with the SciGlob hardware library and maintains a persistent connection to the central server.

#### 4.1.2 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      STATION AGENT                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    MAIN CONTROLLER                        │   │
│  │  • Startup/shutdown orchestration                         │   │
│  │  • Component lifecycle management                         │   │
│  │  • Error handling and recovery                            │   │
│  └──────────────────────────────────────────────────────────┘   │
│           │              │              │              │         │
│           ▼              ▼              ▼              ▼         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐   │
│  │ CONNECTION │  │    DATA    │  │  COMMAND   │  │  LOCAL   │   │
│  │  MANAGER   │  │ COLLECTOR  │  │  HANDLER   │  │  BUFFER  │   │
│  ├────────────┤  ├────────────┤  ├────────────┤  ├──────────┤   │
│  │• WebSocket │  │• Tracker   │  │• Parse cmd │  │• SQLite  │   │
│  │• Reconnect │  │  50-100 Hz │  │• Validate  │  │• Queue   │   │
│  │• Heartbeat │  │• Sensors   │  │• Execute   │  │• Persist │   │
│  │• Auth      │  │  10 Hz     │  │• Response  │  │• Sync    │   │
│  └────────────┘  │• Status    │  └────────────┘  └──────────┘   │
│                  │  1 Hz      │                                  │
│                  └────────────┘                                  │
│                        │                                         │
│                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   SCIGLOB LIBRARY                         │   │
│  │  HeadSensor │ Tracker │ FilterWheel │ TempController     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                        │                                         │
│                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     HARDWARE                              │   │
│  │  RS-232 Serial Connections                                │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.1.3 Configuration File

```yaml
# station-agent/config.yaml

station:
  id: "station_001"
  name: "Measurement Station Alpha"
  location: "Building A, Room 101"
  latitude: 40.7128
  longitude: -74.0060

server:
  url: "wss://api.sciglob.example.com/ws/station"
  api_key: "${STATION_API_KEY}"  # From environment
  reconnect_delay: 5  # seconds
  heartbeat_interval: 30  # seconds

hardware:
  head_sensor:
    port: "/dev/ttyUSB0"
    baudrate: 9600
    tracker_type: "LuftBlickTR1"
    degrees_per_step: 0.01
    motion_limits: [0, 90, 0, 360]
    home_position: [0.0, 180.0]
    fw1_filters: ["OPEN", "U340", "BP300", "LPNIR", "ND1", "ND2", "ND3", "ND4", "OPAQUE"]
  
  temperature_controller:
    enabled: true
    port: "/dev/ttyUSB1"
    controller_type: "TETech1"

collection:
  tracker:
    enabled: true
    frequency_hz: 50
  sensors:
    enabled: true
    frequency_hz: 10
  status:
    enabled: true
    frequency_hz: 1

buffer:
  enabled: true
  max_size_mb: 100
  flush_on_connect: true

logging:
  level: "INFO"
  file: "/var/log/sciglob-agent/agent.log"
  max_size_mb: 50
  backup_count: 5
```

#### 4.1.4 Data Collection Frequencies

| Data Type | Frequency | Batch Size | Batch Interval |
|-----------|-----------|------------|----------------|
| Tracker Position | 50-100 Hz | 5-10 readings | 100ms |
| Sensor Readings | 10 Hz | 10 readings | 1000ms |
| Filter Wheel Status | 1 Hz | 1 reading | 1000ms |
| System Status | 0.1 Hz | 1 reading | 10000ms |

#### 4.1.5 Data Packet Format

```python
# MessagePack encoded packet
{
    "station_id": "station_001",
    "batch_id": "b_1701619200_001",
    "batch_time": 1701619200.123456,
    "readings": [
        {
            "ts": 1701619200.001,
            "type": "tracker",
            "data": {
                "zen": 45.00,
                "azi": 180.00,
                "zen_s": 4500,
                "azi_s": -1200
            }
        },
        {
            "ts": 1701619200.021,
            "type": "tracker",
            "data": {
                "zen": 45.01,
                "azi": 180.00,
                "zen_s": 4501,
                "azi_s": -1200
            }
        },
        # ... more readings
    ]
}
```

### 4.2 Central Server

#### 4.2.1 Overview

The Central Server is a horizontally scalable FastAPI application that handles WebSocket connections from stations and dashboards, processes data, and manages the system.

#### 4.2.2 Server Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CENTRAL SERVER CLUSTER                             │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        LOAD BALANCER (NGINX)                           │ │
│  │  • SSL termination                                                     │ │
│  │  • WebSocket sticky sessions                                           │ │
│  │  • Health checks                                                       │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                     │                                        │
│          ┌──────────────────────────┼──────────────────────────┐            │
│          ▼                          ▼                          ▼            │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │   API SERVER 1   │    │   API SERVER 2   │    │   API SERVER N   │      │
│  │                  │    │                  │    │                  │      │
│  │ ┌──────────────┐ │    │ ┌──────────────┐ │    │ ┌──────────────┐ │      │
│  │ │  REST API    │ │    │ │  REST API    │ │    │ │  REST API    │ │      │
│  │ │  Endpoints   │ │    │ │  Endpoints   │ │    │ │  Endpoints   │ │      │
│  │ └──────────────┘ │    │ └──────────────┘ │    │ └──────────────┘ │      │
│  │ ┌──────────────┐ │    │ ┌──────────────┐ │    │ ┌──────────────┐ │      │
│  │ │  WebSocket   │ │    │ │  WebSocket   │ │    │ │  WebSocket   │ │      │
│  │ │  Handler     │ │    │ │  Handler     │ │    │ │  Handler     │ │      │
│  │ └──────────────┘ │    │ └──────────────┘ │    │ └──────────────┘ │      │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘      │
│          │                          │                          │            │
│          └──────────────────────────┼──────────────────────────┘            │
│                                     ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                          REDIS CLUSTER                                 │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │ │
│  │  │   Pub/Sub    │  │   Sessions   │  │   Streams    │                 │ │
│  │  │  (Live Data) │  │   (State)    │  │  (Queues)    │                 │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                     │                                        │
│          ┌──────────────────────────┼──────────────────────────┐            │
│          ▼                          ▼                          ▼            │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │  INGESTION       │    │  ALERT           │    │  EMAIL           │      │
│  │  WORKER          │    │  WORKER          │    │  WORKER          │      │
│  │                  │    │                  │    │                  │      │
│  │  • Validate data │    │  • Check rules   │    │  • Format email  │      │
│  │  • Write to DB   │    │  • Trigger alerts│    │  • Send via API  │      │
│  │  • Update cache  │    │  • Rate limit    │    │  • Log delivery  │      │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘      │
│          │                          │                                        │
│          ▼                          ▼                                        │
│  ┌──────────────────┐    ┌──────────────────┐                               │
│  │   TIMESCALEDB    │    │   POSTGRESQL     │                               │
│  │   (Time-series)  │    │   (Relational)   │                               │
│  └──────────────────┘    └──────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Web Dashboard

#### 4.3.1 Overview

The Web Dashboard is a React single-page application that provides real-time monitoring and control capabilities through a modern, responsive interface.

#### 4.3.2 Page Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  HEADER                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ [Logo] SciGlob Platform    [Search]    [Alerts 🔔 3]  [User ▼]         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
├─────────────────┬───────────────────────────────────────────────────────────┤
│  SIDEBAR        │  MAIN CONTENT                                             │
│                 │                                                            │
│  Dashboard      │  ┌─────────────────────────────────────────────────────┐  │
│  ────────────   │  │  STATION OVERVIEW                                   │  │
│  📊 Overview    │  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │  │
│  📍 Map View    │  │  │ 🟢   │ │ 🟢   │ │ 🔴   │ │ 🟢   │ │ 🟡   │      │  │
│                 │  │  │St.001│ │St.002│ │St.003│ │St.004│ │St.005│      │  │
│  Stations       │  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘      │  │
│  ────────────   │  │  ... (300+ stations in grid)                        │  │
│  📡 All         │  └─────────────────────────────────────────────────────┘  │
│  🌐 Network A   │                                                            │
│  🌐 Network B   │  ┌─────────────────────────────────────────────────────┐  │
│                 │  │  SYSTEM METRICS                                     │  │
│  Management     │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐      │  │
│  ────────────   │  │  │ Online     │ │ Data Rate  │ │ Alerts     │      │  │
│  👥 Users       │  │  │   287      │ │  14.5K/s   │ │    3       │      │  │
│  ⚠️ Alerts      │  │  └────────────┘ └────────────┘ └────────────┘      │  │
│  ⚙️ Settings    │  └─────────────────────────────────────────────────────┘  │
│                 │                                                            │
└─────────────────┴───────────────────────────────────────────────────────────┘
```

#### 4.3.3 Key Pages

| Page | Route | Description | Access |
|------|-------|-------------|--------|
| Dashboard | `/` | System overview | All |
| Station List | `/stations` | All stations grid | All |
| Station Detail | `/stations/:id` | Single station view | All |
| Station Map | `/map` | Geographic view | All |
| Users | `/users` | User management | Admin |
| Networks | `/networks` | Network management | Admin |
| Alerts | `/alerts` | Alert history | All |
| Alert Rules | `/alerts/rules` | Configure rules | Admin, NetOp |
| Settings | `/settings` | System settings | Admin |
| Login | `/login` | Authentication | Public |

---

## 5. Data Architecture

### 5.1 Database Design

#### 5.1.1 TimescaleDB (Time-Series Data)

```sql
-- ================================================================
-- TIMESCALEDB SCHEMA - Time-Series Measurement Data
-- ================================================================

-- Main measurements hypertable
CREATE TABLE measurements (
    time            TIMESTAMPTZ NOT NULL,
    station_id      UUID NOT NULL,
    
    -- Tracker data
    zenith_deg      REAL,
    azimuth_deg     REAL,
    zenith_steps    INTEGER,
    azimuth_steps   INTEGER,
    
    -- Filter wheels
    fw1_position    SMALLINT,
    fw1_filter      VARCHAR(20),
    fw2_position    SMALLINT,
    fw2_filter      VARCHAR(20),
    
    -- Head sensor readings (HSN2)
    hs_temperature  REAL,
    hs_humidity     REAL,
    hs_pressure     REAL,
    
    -- Temperature controller
    tc_temperature  REAL,
    tc_setpoint     REAL,
    
    -- Status
    status_code     SMALLINT DEFAULT 0,
    
    -- Metadata
    batch_id        VARCHAR(50)
);

-- Convert to hypertable (1-hour chunks for high-frequency data)
SELECT create_hypertable(
    'measurements', 
    'time', 
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Partitioning by station for better query performance
SELECT add_dimension('measurements', 'station_id', number_partitions => 16);

-- Indexes
CREATE INDEX idx_measurements_station_time 
    ON measurements (station_id, time DESC);

CREATE INDEX idx_measurements_time_brin 
    ON measurements USING BRIN (time) WITH (pages_per_range = 32);

-- Compression policy (compress chunks older than 7 days)
ALTER TABLE measurements SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'station_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('measurements', INTERVAL '7 days');

-- Retention policy (keep 1 year of data)
SELECT add_retention_policy('measurements', INTERVAL '1 year');

-- Continuous aggregates for dashboard queries
CREATE MATERIALIZED VIEW measurements_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    station_id,
    AVG(zenith_deg) AS avg_zenith,
    AVG(azimuth_deg) AS avg_azimuth,
    AVG(hs_temperature) AS avg_temperature,
    AVG(hs_humidity) AS avg_humidity,
    AVG(hs_pressure) AS avg_pressure,
    COUNT(*) AS reading_count
FROM measurements
GROUP BY bucket, station_id
WITH NO DATA;

-- Refresh policy for continuous aggregate
SELECT add_continuous_aggregate_policy('measurements_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);
```

#### 5.1.2 PostgreSQL (Relational Data)

```sql
-- ================================================================
-- POSTGRESQL SCHEMA - Relational Data
-- ================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----------------------------------------------------------------
-- Networks (Regions/Groups of Stations)
-- ----------------------------------------------------------------
CREATE TABLE networks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT,
    timezone        VARCHAR(50) DEFAULT 'UTC',
    settings        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Stations
-- ----------------------------------------------------------------
CREATE TABLE stations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    network_id      UUID REFERENCES networks(id) ON DELETE SET NULL,
    
    -- Identification
    name            VARCHAR(100) NOT NULL,
    code            VARCHAR(20) UNIQUE,
    api_key         VARCHAR(64) UNIQUE NOT NULL,
    api_key_hash    VARCHAR(128) NOT NULL,
    
    -- Location
    location        VARCHAR(255),
    latitude        REAL,
    longitude       REAL,
    altitude        REAL,
    
    -- Hardware configuration
    hardware_config JSONB DEFAULT '{}',
    
    -- Status
    status          VARCHAR(20) DEFAULT 'offline',
    last_seen       TIMESTAMPTZ,
    last_data       TIMESTAMPTZ,
    current_server  VARCHAR(100),  -- Which server has connection
    
    -- Metadata
    notes           TEXT,
    tags            TEXT[],
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_stations_network ON stations(network_id);
CREATE INDEX idx_stations_status ON stations(status);
CREATE INDEX idx_stations_api_key ON stations(api_key);

-- ----------------------------------------------------------------
-- Users
-- ----------------------------------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Authentication
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    
    -- Profile
    name            VARCHAR(100) NOT NULL,
    phone           VARCHAR(20),
    
    -- Role
    role            VARCHAR(20) NOT NULL 
                    CHECK (role IN ('admin', 'network_operator', 'local_operator')),
    
    -- Status
    is_active       BOOLEAN DEFAULT TRUE,
    email_verified  BOOLEAN DEFAULT FALSE,
    last_login      TIMESTAMPTZ,
    
    -- Settings
    settings        JSONB DEFAULT '{}',
    
    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- ----------------------------------------------------------------
-- User-Network Assignments (for Network Operators)
-- ----------------------------------------------------------------
CREATE TABLE user_networks (
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    network_id      UUID REFERENCES networks(id) ON DELETE CASCADE,
    assigned_at     TIMESTAMPTZ DEFAULT NOW(),
    assigned_by     UUID REFERENCES users(id),
    PRIMARY KEY (user_id, network_id)
);

-- ----------------------------------------------------------------
-- User-Station Assignments (for Local Operators)
-- ----------------------------------------------------------------
CREATE TABLE user_stations (
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    station_id      UUID REFERENCES stations(id) ON DELETE CASCADE,
    assigned_at     TIMESTAMPTZ DEFAULT NOW(),
    assigned_by     UUID REFERENCES users(id),
    PRIMARY KEY (user_id, station_id)
);

-- ----------------------------------------------------------------
-- Alert Rules
-- ----------------------------------------------------------------
CREATE TABLE alert_rules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Scope
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    station_id      UUID REFERENCES stations(id) ON DELETE CASCADE,
    network_id      UUID REFERENCES networks(id) ON DELETE CASCADE,
    
    -- Rule definition
    condition       JSONB NOT NULL,
    -- Example: {"field": "hs_temperature", "operator": ">", "value": 50}
    
    -- Alert settings
    severity        VARCHAR(20) DEFAULT 'warning'
                    CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    email_recipients TEXT[] NOT NULL DEFAULT '{}',
    
    -- Rate limiting
    cooldown_minutes INTEGER DEFAULT 60,
    last_triggered  TIMESTAMPTZ,
    
    -- Status
    is_active       BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alert_rules_station ON alert_rules(station_id);
CREATE INDEX idx_alert_rules_network ON alert_rules(network_id);
CREATE INDEX idx_alert_rules_active ON alert_rules(is_active);

-- ----------------------------------------------------------------
-- Alerts (History)
-- ----------------------------------------------------------------
CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_id         UUID REFERENCES alert_rules(id) ON DELETE SET NULL,
    station_id      UUID REFERENCES stations(id) ON DELETE CASCADE,
    
    -- Alert details
    severity        VARCHAR(20) NOT NULL,
    message         TEXT NOT NULL,
    field           VARCHAR(50),
    value           REAL,
    threshold       REAL,
    
    -- Resolution
    status          VARCHAR(20) DEFAULT 'active'
                    CHECK (status IN ('active', 'acknowledged', 'resolved')),
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    notes           TEXT,
    
    -- Email tracking
    email_sent      BOOLEAN DEFAULT FALSE,
    email_sent_at   TIMESTAMPTZ,
    email_error     TEXT,
    
    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_station ON alerts(station_id);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_created ON alerts(created_at DESC);

-- ----------------------------------------------------------------
-- Command History
-- ----------------------------------------------------------------
CREATE TABLE commands (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    station_id      UUID REFERENCES stations(id) ON DELETE CASCADE NOT NULL,
    
    -- Command details
    command_type    VARCHAR(50) NOT NULL,
    parameters      JSONB DEFAULT '{}',
    
    -- Execution
    status          VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'acknowledged', 
                                      'completed', 'failed', 'timeout')),
    sent_at         TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    response        JSONB,
    
    -- Metadata
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_commands_station ON commands(station_id);
CREATE INDEX idx_commands_status ON commands(status);
CREATE INDEX idx_commands_created ON commands(created_at DESC);

-- ----------------------------------------------------------------
-- Audit Log
-- ----------------------------------------------------------------
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id),
    
    -- Action details
    action          VARCHAR(50) NOT NULL,
    resource_type   VARCHAR(50) NOT NULL,
    resource_id     UUID,
    
    -- Details
    details         JSONB DEFAULT '{}',
    ip_address      INET,
    user_agent      TEXT,
    
    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);

-- ----------------------------------------------------------------
-- Refresh Tokens (for JWT)
-- ----------------------------------------------------------------
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    token_hash      VARCHAR(128) UNIQUE NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens(expires_at);
```

---

*[Document continues in Part 2...]*

See `PLATFORM_ARCHITECTURE_PART2.md` for:
- Section 6: Security Architecture
- Section 7: API Specifications
- Section 8: Deployment Architecture
- Section 9: Development Roadmap
- Section 10: Appendices

