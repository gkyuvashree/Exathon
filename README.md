# TraceFlow — Data Pipeline Observability Platform

**Team:** Hack Titans  
**Hackathon:** ExaThon  
**Track:** The Work Behind the Work

## Overview

TraceFlow is a data pipeline observability platform designed to provide visibility into pipeline health, monitor data quality, identify anomalies, and investigate incidents.

It brings pipeline metrics, incident monitoring, metric exploration, and pipeline lineage into a unified dashboard, helping users understand what is happening across their data workflows.

## Key Features

- **System Overview:** Monitor key pipeline health metrics through a centralized dashboard.
- **Incidents & Anomalies:** View detected anomalies and investigate pipeline incidents.
- **Metric Explorer:** Explore historical metric trends through interactive charts.
- **Pipeline Lineage:** Visualize pipeline relationships and dependencies.
- **Evaluation Benchmark:** Evaluate detection performance using seeded development scenarios.

## Technology Stack

### Frontend
- React 18
- TypeScript
- Vite
- Tailwind CSS
- React Flow
- Recharts
- Framer Motion
- Lucide React

### Backend
- Python
- FastAPI
- SQLite
- YAML-based configuration
- Plumbline coherence engine

## Architecture

```text
                 TraceFlow
                     |
          +----------+----------+
          |                     |
       Frontend              Backend
     React + Vite            FastAPI
          |                     |
          |              +------+------+
          |              |             |
          |           Metrics       Detection
          |           Storage       Engine
          |              |             |
          +--------------+-------------+
                         |
                  REST API Endpoints
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Backend health status |
| GET | `/api/overview` | Pipeline overview metrics |
| GET | `/api/metrics/catalog` | Available metrics |
| GET | `/api/metrics/timeseries` | Historical metric data |
| GET | `/api/lineage` | Pipeline lineage information |
| GET | `/api/incidents` | Incident information |

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js and npm
- Git

### 1. Clone the repository

```bash
git clone https://github.com/gkyuvashree/Exathon.git
cd Exathon
```

### 2. Start the Backend

```bash
cd backend

python -m venv .venv
```

Activate the virtual environment.

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the server:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend runs at:

`http://127.0.0.1:8000`

API documentation:

`http://127.0.0.1:8000/docs`

### 3. Start the Frontend

Open a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at:

`http://localhost:5173`

## Testing

### Backend Tests

```bash
cd backend
.venv\Scripts\python -m pytest -q
```

### Frontend Build

```bash
cd frontend
npm run build
```

## Evaluation Benchmark

The development benchmark was evaluated using 50 seeds across 12 scenario types, resulting in 600 scenarios.

| Metric | Result |
|---|---:|
| Precision | 0.879 |
| Recall | 0.842 |
| F1 Score | 0.860 |
| False Alarms / Week | 0.2 |
| Hard-Negative FPR | 51% |
| Duplicate Replay Recall | 0% |
| Timezone Shift Recall | 58% |

These results represent the development evaluation and should not be interpreted as production performance.

## Demo & Presentation

- **GitHub Repository:** https://github.com/gkyuvashree/Exathon
- **Live Demo:** Not currently published
- **Demo Video:** Not available
- **Pitch Deck:** To be added

## Repository Structure

```text
Exathon/
│
├── backend/
│   ├── app/
│   ├── tests/
│   ├── config/
│   └── data/
│
├── frontend/
│   ├── src/
│   └── public/
│
├── reports/
│
└── README.md
```

## Team

**Hack Titans**

Built for ExaThon.

## Notes

- The dashboard uses historical development data.
- Demonstration incidents may include simulated or seeded scenarios.
- Benchmark metrics are based on development evaluation.
- The project should not be described as having a live Exasol integration unless that integration is implemented and verified.
