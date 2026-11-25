# FactoryLink 🇯🇵
### Manufacturing Operations & Supplier Collaboration Platform

**Connecting Japanese manufacturers, suppliers, inventory, production, quality control, and traceability in one platform.**

FactoryLink is a full-stack manufacturing operations and supplier collaboration platform designed around the operational challenges faced by Japanese manufacturing companies, particularly small and medium-sized manufacturers.

It provides a centralized digital workspace to manage the manufacturing lifecycle — from purchasing raw materials and coordinating with suppliers to production, quality inspections, inventory management, and finished-product shipments.

Built with **English and Japanese language support**, Tokyo timezone defaults, and Japanese Yen (JPY) currency conventions.

---

## 1. The Problem: Manufacturing Challenges in Japan

Japan has one of the world's most established manufacturing industries. However, maintaining manufacturing productivity and competitiveness has become increasingly challenging.

While researching Japan's manufacturing industry and government publications, I identified several important challenges:

### Key challenges

**1. Labour Shortages**

Manufacturers, particularly smaller businesses, face difficulties securing and retaining skilled workers. This creates pressure to improve productivity and reduce dependence on manual administrative processes.

**2. Supplier and Supply-Chain Coordination**

Manufacturers depend on multiple suppliers for raw materials and components. Disconnected communication, delayed delivery updates, and limited visibility into supplier activities can make production planning difficult.

**3. Manufacturing Productivity**

Managing purchasing, inventory, production, and quality operations through disconnected systems or manual processes makes it difficult to maintain visibility across the manufacturing lifecycle.

**4. Digital Transformation (DX)**

Smaller manufacturers can face financial, technical, and workforce barriers when adopting digital technologies and connecting their existing business operations.

**5. Inventory and Production Traceability**

Manufacturers need reliable information about material batches, production activities, inspection results, and finished products. Poor visibility can make quality investigations and inventory reconciliation more difficult.

### Government research and references

FactoryLink's problem context is informed by the following Japanese government publications:

- [METI – Smart Manufacturing Development Guideline (2024)](https://www.meti.go.jp/english/press/2024/0628_002.html): Identifies supply-chain disruptions, productivity declines associated with labour shortages, and increasing management costs.
- [METI – White Paper on Manufacturing Industries (2025)](https://www.meti.go.jp/english/press/2025/0530_007.html): Discusses manufacturing competitiveness, digital transformation, human resources, and economic security.
- [METI – 2025 White Paper on Small and Medium Enterprises](https://www.meti.go.jp/english/press/2025/0425_001.html): Highlights structural labour shortages and increasing production and investment costs.
- [Small and Medium Enterprise Agency – 2025 White Paper](https://www.chusho.meti.go.jp/pamflet/hakusyo/2025/shokibo/b2_1_1.html): Discusses barriers to digital transformation, including costs, insufficient DX personnel, and limited time.

---

## 2. The Solution: FactoryLink

FactoryLink aims to address operational fragmentation by connecting essential manufacturing activities in one system.

Instead of treating purchasing, suppliers, inventory, production, quality, and maintenance as separate processes, FactoryLink connects them through a shared operational workflow.

### How FactoryLink addresses these challenges

| Manufacturing challenge | FactoryLink solution |
|---|---|
| Disconnected supplier communication | Dedicated supplier collaboration portal |
| Limited purchase-order visibility | Purchase orders and delivery tracking |
| Inventory inconsistencies | Batch-based inventory and immutable stock ledger |
| Production material shortages | FIFO inventory reservations |
| Difficult product traceability | Forward and backward lot genealogy |
| Quality-control problems | Inspection templates, quality holds, and CAPA |
| Equipment downtime | Preventive maintenance and breakdown tracking |
| Language barriers | English and Japanese interface |

**The goal:** Improve operational visibility, strengthen supplier coordination, and provide manufacturers with a connected digital foundation for managing their operations.

FactoryLink is an independent software project inspired by these industry challenges, not an officially endorsed Japanese government product.

---

## 3. Manufacturing Workflow

FactoryLink models the manufacturing lifecycle from purchasing raw materials to shipping finished products.

1. **Purchase Orders:** Manufacturers create purchase orders and share them with registered suppliers.
2. **Supplier Collaboration:** Suppliers access a separate workspace to confirm orders, update delivery progress, and share documents.
3. **Goods Receiving:** Factories record partial or complete deliveries. Each receipt creates inventory lots and immutable stock movements.
4. **Inventory Management:** Materials are tracked by batch, with FIFO reservations, stock adjustments, and inventory history.
5. **Production Management:** Production orders reserve materials, track progress, and record completed and rejected quantities.
6. **Product Serialisation:** Accepted finished units receive unique serial numbers linked to their source material lots.
7. **Quality Control:** Reusable inspection templates support pass/fail checks and numeric tolerance validation.
8. **Corrective Actions:** Failed inspections trigger quality holds and CAPA cases. Releasing held inventory requires explicit approval and supporting evidence.
9. **Traceability:** Manufacturers can investigate the complete journey from supplier and raw material batches to production, inspection, and shipment.
10. **Maintenance:** Equipment maintenance, breakdowns, and downtime are recorded and analysed.

---

## 4. Core Features

### Supplier and Procurement Management
- Multi-tenant manufacturer and supplier workspaces.
- Supplier registry and supplier portal.
- Purchase-order creation and management.
- Supplier order confirmations and delivery updates.
- Document sharing between manufacturers and suppliers.
- Partial and complete goods receipts.

### Inventory and Warehouse Management
- Material and batch management.
- FIFO stock reservations.
- Immutable stock movement ledger.
- Reason-coded inventory adjustments.
- Inventory reconciliation and stock visibility.

### Production Management
- Production order management.
- Material reservation and consumption.
- Production progress tracking.
- Completed and rejected quantity tracking.
- Unique serial numbers for accepted finished products.

### Quality Management
- Reusable quality inspection templates.
- Pass/fail and numeric tolerance inspections.
- Defect recording.
- Automatic quality holds following failed inspections.
- Corrective and Preventive Action (CAPA) lifecycle.
- Evidence-gated quality release.

### Product Traceability
- Forward material-lot genealogy.
- Backward finished-product serial genealogy.
- Supplier-to-finished-product traceability.
- QR code generation and downloading.
- Camera-based QR scanning with manual fallback.
- Shipment records.

### Maintenance Management
- Equipment registry.
- Preventive maintenance scheduling.
- Unplanned maintenance and breakdown records.
- Equipment downtime tracking.
- Maintenance analytics.

### Administration and Reporting
- Role-based access control.
- User and supplier management.
- Refresh-token rotation.
- Audit history.
- Notifications and operational dashboards.
- CSV and XLSX reports.
- Safe editing, deletion, deactivation, and archival rules.

### Japanese Localization
- English and Japanese user interfaces.
- Japanese UTF-8 character handling.
- Tokyo timezone defaults.
- Japanese Yen (JPY) currency defaults.

---

## 5. Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Backend | Python 3.12, FastAPI |
| ORM | SQLAlchemy 2 |
| Database | PostgreSQL 17 |
| Migrations | Alembic |
| Background Jobs | Celery |
| Message Broker / Cache | Redis 7 |
| Malware Scanning | ClamAV |
| Web Server | Nginx |
| Containerization | Docker, Docker Compose |
| Cloud Deployment | Render Blueprint |
| CI | GitHub Actions |

### Architecture

FactoryLink follows a modular monolith architecture with separate frontend, backend, database, background-worker, scheduler, and malware-scanning services.

The system uses PostgreSQL row-level security to enforce tenant isolation and database-backed inventory and traceability records to maintain operational consistency.

---

## 6. Security and Data Integrity

Security and data integrity are important because manufacturing systems handle supplier information, inventory records, quality evidence, and production history.

Implemented security measures include:

- Multi-tenant access isolation using PostgreSQL Row-Level Security.
- Role-based permissions.
- Access and refresh-token authentication.
- Refresh-token rotation.
- Six-digit email verification codes.
- SHA-256 hashing of verification codes.
- Verification-code expiration and attempt limits.
- Rate limiting.
- Password reset verification.
- Optional Google authentication.
- ClamAV document malware scanning.
- Immutable stock movement history.
- Audit logging.
- Controlled quality-hold release.
- Safe deletion rules to protect historical records.

---

## 7. Testing and Verification

FactoryLink has undergone extensive local testing.

| Verification | Result |
|---|---|
| Backend automated tests | 207 passed |
| Frontend unit tests | 8 passed |
| Production frontend build | Passed |
| PostgreSQL migration verification | 0014 applied successfully |
| Runtime database permissions | Create, update, and delete verified |
| Docker Compose services | All verified healthy |
| Dependency security audits | No known vulnerabilities reported |
| Acceptance tests | 5 passed, 0 failed, 6 skipped |
| Alembic migration history | 14 migrations |

### Important verification notes

- PostgreSQL 17.11 was tested.
- Docker Compose was tested with PostgreSQL, Redis, ClamAV, migrations, backend, worker, scheduler, and frontend.
- The application readiness endpoint was verified.
- Playwright browser journeys remain to be fully verified.
- Real external email delivery requires SMTP or Resend configuration.

---

## 8. Running Locally

### Prerequisites

- Docker Desktop
- Docker Compose
- Git

### Clone the repository

```bash
git clone https://github.com/Ancientsocks/factorylink-japan.git
cd factorylink-japan
```

### Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and configure the required local environment values.

### Start the application

```bash
docker compose up --build -d
```

### Access the application

| Service | URL |
|---|---|
| FactoryLink Frontend | http://localhost:8080 |
| Backend API | http://localhost:8080/api |
| API Documentation | http://localhost:8080/docs |
| API Readiness | http://localhost:8080/health/ready |

To inspect running services:

```bash
docker compose ps
```

To inspect application logs:

```bash
docker compose logs -f
```

To stop the application:

```bash
docker compose down
```

---

## 9. Project Documentation

FactoryLink includes detailed technical and operational documentation.

| Document | Description |
|---|---|
| `ARCHITECTURE.md` | Application architecture |
| `DATABASE_DESIGN.md` | Database structure and relationships |
| `API_DOCUMENTATION.md` | API endpoints |
| `SECURITY.md` | Security implementation |
| `TESTING.md` | Testing and verification |
| `DEPLOYMENT.md` | Deployment instructions |
| `PRODUCTION_DEPLOYMENT.md` | Production deployment guidance |
| `PRODUCTION_OPERATIONS_RUNBOOK.md` | Operational procedures |
| `USER_GUIDE.md` | Application usage |
| `TROUBLESHOOTING.md` | Common issues and solutions |

---

## 10. Current Project Status

**Status: Hardened Local Evaluation Candidate**

FactoryLink is functional locally using Docker Compose, and its automated tests, database migrations, frontend build, and local infrastructure have been verified.

However, it has not yet received full production approval.

The following activities remain:

- Complete Playwright end-to-end browser testing.
- Verify the cloud deployment on Render.
- Configure and verify private S3-compatible object storage.
- Verify real SMTP or Resend email delivery.
- Verify ClamAV signature database warm-up.
- Configure external application monitoring.
- Perform production backup and point-in-time recovery drills.
- Complete production security and operational acceptance testing.

---

## 11. Project Vision

FactoryLink was developed with a simple idea:

**Manufacturing operations should work as one connected system, not as disconnected processes.**

By bringing suppliers, purchasing, inventory, production, quality control, traceability, and maintenance together, FactoryLink demonstrates how a connected digital platform can help manufacturers improve operational visibility and coordination.

The project explores how modern web technologies can be applied to real-world industrial workflows, with particular attention to the challenges faced by Japanese manufacturers.

---

## 12. Author

**Abdul Rahman**

GitHub: [@Ancientsocks](https://github.com/Ancientsocks)

LinkedIn: [Abdul Rahman](https://www.linkedin.com/in/abdul-rahman-770409247/)

---

*FactoryLink — Connecting Manufacturing Operations, One Workflow at a Time.*
