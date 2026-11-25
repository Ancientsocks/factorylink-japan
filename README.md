# FactoryLink 🇯🇵
### Manufacturing Operations & Supplier Collaboration Platform

**Connecting suppliers, inventory, production, quality, and traceability in one manufacturing platform.**

FactoryLink is a full-stack manufacturing operations platform designed around the challenges faced by Japanese small and medium-sized manufacturers. It brings disconnected manufacturing workflows into one centralized system, helping manufacturers manage purchasing, supplier collaboration, inventory, production, quality inspections, maintenance, and finished-product traceability.

The project focuses on making manufacturing operations more organized, transparent, and data-driven without requiring businesses to depend on multiple disconnected tools.

---

## 🇯🇵 The Problem: Manufacturing Digitalization in Japan

Japan has a large manufacturing ecosystem supported by manufacturers, component producers, and small and medium-sized suppliers. However, improving digital capabilities and connecting operational data across manufacturing processes remain important challenges.

Japan's **2026 White Paper on Manufacturing Industries**, published by the Ministry of Economy, Trade and Industry (METI), highlights the importance of strengthening industrial competitiveness through digital technology, AI adoption, growth investment, and economic security.

One particularly relevant finding is discussed in a Tokyo Metropolitan Government analysis of the 2026 White Paper:

- Approximately **66%** of surveyed manufacturers collect some production data.
- Only **43.9%** report using that data to achieve operational improvements.
- Data silos, limited digital skills, and difficulties connecting information remain barriers to effective digital transformation.

### Operational Problems

Many manufacturing workflows can still be difficult to coordinate when information is distributed across spreadsheets, disconnected systems, and manual processes.

| Manufacturing challenge | Operational impact |
|---|---|
| Production records scattered across Excel files | Difficult to maintain consistent and centralized information |
| Disconnected supplier systems | Limited visibility into purchase orders and deliveries |
| Difficult product defect tracing | Time-consuming quality investigations |
| Untracked machine downtime | Limited visibility into equipment performance |
| Manually updated production schedules | Increased coordination effort and risk of outdated information |
| Expensive and complicated enterprise systems | Difficult adoption for smaller manufacturers |

### The Software Opportunity

FactoryLink addresses these operational challenges through a unified manufacturing management platform.

Instead of managing suppliers, purchasing, inventory, production, and quality through separate tools, manufacturers can coordinate these workflows through a connected system with shared operational records.

**The goal:** Make manufacturing information easier to manage, connect, track, and analyse.

### Research and References

- [METI – 2026 White Paper on Manufacturing Industries](https://www.meti.go.jp/english/press/2026/0529_003.html)
- [METI – 2026 White Paper Summary (PDF)](https://www.meti.go.jp/english/press/2026/pdf/0529_003a.pdf)
- [Tokyo Metropolitan Government – Analysis of IT Utilization and Cybersecurity Based on the 2026 Manufacturing White Paper](https://www.cybersecurity.metro.tokyo.lg.jp/links/762/index.html)

*FactoryLink is an independent software project inspired by these documented industry challenges. It is not affiliated with or endorsed by the Japanese government.*

---

## 💡 The Solution: FactoryLink

FactoryLink connects the major stages of manufacturing operations through a centralized platform.

### Core Modules

| Module | Capabilities |
|---|---|
| Supplier Management | Supplier registration, supplier workspaces, and collaboration |
| Purchase Management | Purchase orders, supplier confirmations, and delivery tracking |
| Inventory Management | Material tracking, lot management, FIFO allocation, and stock movements |
| Production Management | Production orders, material reservations, progress tracking, and completion |
| Quality Management | Inspection templates, defect recording, quality holds, and corrective actions |
| Machine Maintenance | Equipment records, maintenance scheduling, and maintenance history |
| Product Traceability | QR-based identification and production genealogy |
| Shipping Management | Finished-product tracking and shipment records |
| Analytics & Reporting | Operational dashboards, reports, and CSV/XLSX exports |
| Audit & Notifications | Activity history, system notifications, and operational visibility |

### 1. Supplier Collaboration

Manufacturers can manage suppliers and purchase orders through a centralized workspace.

Suppliers have a separate portal where they can:

- View assigned purchase orders.
- Confirm or respond to orders.
- Update delivery status.
- Share relevant documents.
- Coordinate incoming material deliveries.

### 2. Inventory and Material Tracking

The inventory module tracks materials from receipt through production consumption.

- Record full and partial goods receipts.
- Create inventory lots and batches.
- Track stock movements through an immutable ledger.
- Reserve materials using FIFO allocation.
- Record reason-coded inventory adjustments.
- Maintain material availability information.

### 3. Production Management

Production teams can manage manufacturing orders and monitor execution.

- Create and manage production orders.
- Reserve required materials.
- Track production progress.
- Record material consumption.
- Track accepted and rejected production quantities.
- Generate unique serial numbers for accepted finished units.

### 4. Quality Management

FactoryLink connects quality inspections with production and inventory records.

- Configure inspection templates.
- Perform pass/fail and numeric-tolerance inspections.
- Record defects and inspection results.
- Create quality holds when failures occur.
- Manage corrective and preventive actions (CAPA).
- Require evidence-based approval before releasing held inventory.

### 5. Product Traceability

Product genealogy connects the different stages of manufacturing.

A finished product can be traced through its manufacturing history:

**Supplier → Purchase Order → Goods Receipt → Material Lot → Production Order → Quality Inspection → Finished Product → Shipment**

QR codes support product identification and traceability, with camera scanning and manual lookup options.

### 6. Machine Maintenance

The maintenance module provides a centralized record of equipment and maintenance activities.

- Maintain equipment records.
- Schedule maintenance activities.
- Track maintenance history.
- Record equipment-related operational issues.

### 7. Production Analytics and Reporting

FactoryLink provides operational visibility through dashboards and reports.

- Production progress.
- Inventory and material availability.
- Quality inspection results.
- Defect and rejection information.
- Equipment maintenance records.
- CSV and Excel reporting.

---

## 🔄 Manufacturing Workflow

FactoryLink connects the manufacturing lifecycle from purchasing materials to shipping finished products.

1. **Purchasing:** The manufacturer creates purchase orders and shares them with suppliers.
2. **Supplier Confirmation:** Suppliers confirm orders and update delivery information.
3. **Goods Receipt:** Incoming materials are received and recorded as inventory lots.
4. **Inventory Allocation:** Materials are reserved for production using FIFO.
5. **Production:** Production orders track manufacturing progress and material consumption.
6. **Quality Inspection:** Finished units undergo inspection, with failures creating quality holds and corrective actions.
7. **Serialisation:** Accepted finished units receive unique serial numbers.
8. **Traceability:** QR codes connect finished products to their source materials and manufacturing history.
9. **Shipping:** Finished products are recorded and tracked through shipment.

---

## 🏗️ System Architecture

FactoryLink uses a modular full-stack architecture with a React frontend, FastAPI backend, PostgreSQL database, and supporting background services.

```text
                    FACTORYLINK
                         |
          +--------------+--------------+
          |                             |
    React Frontend                 FastAPI Backend
    React 19                       Python 3.12
    TypeScript                     REST APIs
    Vite                           SQLAlchemy 2
    Nginx                          Pydantic
          |                             |
          |                    +--------+--------+
          |                    |        |        |
          |                PostgreSQL  Redis   Celery
          |                Database    Cache   Workers
          |                                     |
          |                                Scheduler
          |
      Manufacturer
      & Supplier
       Workspaces

          Supporting Services:
          - Alembic Migrations
          - ClamAV File Scanning
          - Docker Compose
          - GitHub Actions CI
```

### Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| UI Delivery | Nginx |
| Backend | Python 3.12, FastAPI |
| ORM | SQLAlchemy 2 |
| Database | PostgreSQL 17 |
| Database Migrations | Alembic |
| Background Processing | Celery |
| Caching and Message Broker | Redis 7 |
| File Security | ClamAV |
| Containerization | Docker, Docker Compose |
| Deployment Configuration | Render Blueprint |
| CI | GitHub Actions |

---

## 🔐 Security and Data Integrity

FactoryLink includes security and data-integrity mechanisms designed for a multi-tenant manufacturing environment.

- Role-based access control (RBAC).
- Multi-tenant data isolation using PostgreSQL Row-Level Security (RLS).
- Refresh-token rotation.
- Email verification and password-reset codes.
- SHA-256 hashing of verification codes stored in the database.
- Code expiration and attempt limits.
- Rate limiting and input validation.
- File scanning integration through ClamAV.
- Audit logs for important operational activities.
- Evidence-gated release of quality-held inventory.

### Authentication Options

- Email-based registration and authentication.
- Email verification and password-reset workflows.
- Optional Google sign-in integration.
- SMTP or Resend integration for email delivery.

---

## 🌐 Localization

FactoryLink is designed with Japanese manufacturing workflows in mind.

- English and Japanese user interfaces.
- Japan/Tokyo timezone defaults.
- Japanese Yen (JPY) currency defaults.
- Separate manufacturer and supplier workspaces.

---

## 🧪 Testing and Verification

The current local evaluation build has undergone automated testing and infrastructure verification.

| Verification | Result |
|---|---|
| Backend automated tests | 207 passed |
| Frontend automated tests | 8 passed |
| Frontend production build | Passed |
| Vite production build | 1,580 modules |
| PostgreSQL version | 17.11 verified |
| Alembic migrations | 14 migrations |
| Docker Compose services | Healthy |
| Backend readiness endpoint | Passed |
| Acceptance runner | 5 passed, 0 failed, 6 skipped |
| Python dependency audit | No known vulnerabilities reported |
| npm dependency audit | No known vulnerabilities reported |

*These results describe the local evaluation environment and do not represent independent production certification.*

---

## 🚀 Running Locally

### Prerequisites

- Git
- Docker Desktop
- Docker Compose

### 1. Clone the Repository

```bash
git clone https://github.com/Ancientsocks/factorylink-japan.git
cd factorylink-japan
```

### 2. Configure Environment Variables

Copy the example environment file:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux/macOS:**

```bash
cp .env.example .env
```

Configure the required environment variables using the example file and the project's configuration documentation.

Do not commit real credentials, API keys, database passwords, or production secrets.

### 3. Start the Application

```bash
docker compose up --build -d
```

### 4. Access FactoryLink

| Service | URL |
|---|---|
| Frontend | http://localhost:8080 |
| Backend API | http://localhost:8080/api |
| API Documentation | http://localhost:8080/docs |
| Health Check | http://localhost:8080/health |

*The API and health routes are subject to the application's configured routing.*

---

## 📁 Project Structure

```text
factorylink-japan/
│
├── frontend/              # React + TypeScript application
│
├── backend/               # FastAPI application
│   ├── app/               # Application modules
│   ├── migrations/        # Alembic migrations
│   └── tests/             # Backend tests
│
├── docker-compose.yml     # Local service orchestration
├── Dockerfile             # Container build configuration
├── render.yaml            # Render deployment configuration
├── .github/               # GitHub Actions workflows
├── .env.example           # Environment variable template
└── README.md
```

*Directory names may vary slightly depending on the repository layout.*

---

## 🛣️ Project Status

**Current Status: Hardened Local Evaluation Candidate**

FactoryLink has a functioning local implementation with core manufacturing workflows, automated tests, database migrations, and containerized services.

### Implemented

- Manufacturer and supplier workspaces.
- Authentication and access control.
- Supplier and purchase-order management.
- Goods receipts and inventory tracking.
- FIFO material reservations.
- Production orders and serialisation.
- Quality inspections and CAPA workflows.
- Product genealogy and QR traceability.
- Equipment and maintenance records.
- Dashboards, reporting, and audit logs.
- English and Japanese localization.
- Docker-based local deployment.

### Remaining Before Production Deployment

- End-to-end browser testing with Playwright.
- Production deployment and environment validation.
- Private object storage integration (S3).
- ClamAV signature database warm-up verification.
- Real email delivery configuration.
- External monitoring and alerting.
- Database backup and point-in-time recovery drills.
- Production security and operational review.

**Important:** FactoryLink is not yet production-approved. The current implementation is intended for local evaluation and further validation.

---

## 🎯 Project Goals

FactoryLink aims to demonstrate how a connected software platform can improve visibility and coordination across manufacturing operations.

Its main objectives are:

- Reduce dependence on disconnected spreadsheets.
- Improve communication between manufacturers and suppliers.
- Make inventory and production information easier to track.
- Improve quality investigation through product genealogy.
- Provide better visibility into manufacturing operations.
- Make digital manufacturing workflows more accessible to smaller businesses.

---

## 👨‍💻 Author

**Abdul Rahman**

- GitHub: [@Ancientsocks](https://github.com/Ancientsocks)
- LinkedIn: [Abdul Rahman](https://www.linkedin.com/in/abdul-rahman-770409247/)

---

*FactoryLink — Connecting every stage of manufacturing, from supplier to finished product.*
