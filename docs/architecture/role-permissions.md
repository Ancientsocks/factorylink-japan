# Role and permission overview

FactoryLink uses tenant-scoped user roles. Each authenticated request derives its organisation context from the signed access token and verifies that the user is active and belongs to that organisation. API dependencies and tenant-scoped queries are the enforcement boundary; hiding a browser action is only a usability improvement.

| Role | Main permitted actions |
|---|---|
| `ORG_ADMIN` | Manage the manufacturer workspace users, suppliers, purchase orders, inventory, production, quality, maintenance, reports and audit views. |
| `PRODUCTION_MANAGER` | Manage supplier directory and purchase orders; create and progress production; read operational views and reports. |
| `WAREHOUSE_MANAGER` | Record goods receipts and inventory adjustments; progress permitted purchase-order receipt workflow; read inventory and operational views. |
| `QUALITY_INSPECTOR` | Manage quality templates, inspections, CAPA actions, batch release after required evidence, and quality/traceability views. |
| `MAINTENANCE_MANAGER` | Register equipment, create and update maintenance tasks, and record downtime. |
| `OPERATOR` | Read shop-floor records and perform permitted production status/progress operations; cannot cancel production orders. |
| `SUPPLIER_ADMIN` | Manage members of its own supplier workspace and access only supplier-scoped information shared through linked manufacturer relationships. |
| `SUPPLIER_USER` | View/update only linked purchase orders, upload/download linked PO documents, and manage own notifications/settings. |

## Tenant isolation

The application enforces organisation membership in the FastAPI dependency layer and filters operational queries by the authenticated organisation. Alembic migration `0004_postgresql_tenant_rls` additionally enables and forces PostgreSQL Row-Level Security for tenant-owned operational tables and defines explicit supplier policies for linked suppliers, purchase orders, attachments and notifications. The runtime DB role is separate from the migration owner and receives reviewed, limited column-level update grants; append-only ledgers are not granted UPDATE/DELETE rights.

SQLite unit tests exercise application-level tenant checks but do not prove PostgreSQL RLS semantics. The PostgreSQL 17 RLS/ACL acceptance script must be run against a real PostgreSQL service before production use.

## Role model boundaries

The local application currently uses the concrete roles listed above. It does not expose an unrestricted cross-tenant `SUPER_ADMIN`, a generic read-only `VIEWER`, or separate `PROCUREMENT_MANAGER`, `INVENTORY_MANAGER` and `QUALITY_MANAGER` aliases. The manufacturer workspace administrator is `ORG_ADMIN`; supplier administrators are scoped to their supplier workspace. Do not assign a role by editing a database row manually; use the invitation UI/API so the organisation type and allowed role are validated.
