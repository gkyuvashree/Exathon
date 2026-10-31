# Exathon — Data Pipeline & Observability Engine

Exathon is a high-performance data engineering and pipeline observability platform with a simulated e-commerce data pipeline, labeled failure injection, automated root-cause detection, and interactive pipeline lineage visualization.

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, Pydantic v2, DuckDB, Pandas, NumPy, SciPy, PyYAML, Pytest, HTTPX.
- **Frontend**: Vite, React 18, TypeScript, Tailwind CSS v3.4, `@xyflow/react`, `recharts`, `framer-motion`, `lucide-react`.
- **API Proxy**: Vite dev server proxies `/api` to `http://localhost:8000`.

---

## Repository Layout

```
Exathon/
├── .gitignore               # Git ignore rules for Python, Node, DBs, and env files
├── README.md                # Project documentation and quickstart instructions
├── config/
│   └── lineage.yaml         # Declarative pipeline DAG lineage specification
├── scripts/
│   └── doctor.py            # Diagnostic script verifying runtime, deps, node/npm
├── backend/
│   ├── .venv/               # Pinned Python virtual environment
│   ├── requirements.txt     # Pinned production and test dependencies
│   ├── config/
│   │   └── lineage.yaml     # Packaged DAG lineage declaration
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI application with /api/health & CORS
│   │   └── sim/             # Phase 1 simulation package
│   │       ├── __init__.py
│   │       ├── config.py    # Calendar, profiles, promo days, weights
│   │       ├── generator.py # Vectorized hourly data generator
│   │       ├── failures.py  # 9 failure injectors & 2 hard negatives
│   │       ├── event_log.py # SQLite event logger & decoy ops generator
│   │       ├── pipeline.py  # DuckDB pipeline DAG & control totals
│   │       └── demo_check.py# Demo comparison & performance benchmark
│   └── tests/
│       ├── __init__.py
│       ├── test_health.py   # Pytest smoke test for health endpoint
│       └── test_phase1.py   # Comprehensive Phase 1 test suite
├── frontend/
│   ├── index.html           # HTML shell
│   ├── package.json         # Pinned frontend dependencies and scripts
│   ├── tsconfig.json        # TypeScript configuration
│   ├── vite.config.ts       # Vite configuration with /api proxy to :8000
│   ├── tailwind.config.js   # Tailwind CSS v3.4 configuration
│   ├── postcss.config.js    # PostCSS plugins
│   └── src/
│       ├── main.tsx         # React application entrypoint
│       ├── App.tsx          # Health dashboard, XYFlow lineage & Recharts
│       ├── index.css        # Tailwind style directives
│       └── vite-env.d.ts    # Vite client types
└── docs/
    ├── phase-0-report.md    # Phase 0 verification report
    └── phase-1-report.md    # Phase 1 verification report
```

---

## Quickstart & Verification

Run the environment doctor from the repository root:

```powershell
python scripts/doctor.py
```

Or on bash:
```bash
python3 scripts/doctor.py
```

All 13 diagnostic checks should report `PASS`.

---

## Running Backend

### PowerShell

```powershell
# Navigate to backend directory
cd backend

# Create virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install pinned dependencies
pip install -r requirements.txt

# Run smoke test
python -m pytest -q

# Start FastAPI development server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Bash

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (if not already created)
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt

# Run smoke test
python -m pytest -q

# Start FastAPI development server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend will be available at: `http://localhost:8000/api/health`

---

## Running Frontend

### PowerShell

```powershell
# Navigate to frontend directory
cd frontend

# Install npm dependencies
npm install

# Run type check and production build
npx tsc --noEmit
npm run build

# Start Vite development server
npm run dev
```

### Bash

```bash
# Navigate to frontend directory
cd frontend

# Install npm dependencies
npm install

# Run type check and production build
npx tsc --noEmit
npm run build

# Start Vite development server
npm run dev
```

Frontend will be available at: `http://localhost:5173`
API requests to `/api/*` are automatically proxied to `http://localhost:8000`.

---

## Testing & Quality Gates

1. **Environment Doctor**:
   ```bash
   python scripts/doctor.py
   ```
2. **Backend Unit & Integration Test Suite**:
   ```bash
   cd backend && python -m pytest -q
   ```
3. **Simulation Pipeline & Failure Injection Demo**:
   ```bash
   cd backend && python -m app.sim.demo_check
   ```
4. **Frontend Typecheck & Production Build**:
   ```bash
   cd frontend && npx tsc --noEmit && npm run build
   ```
