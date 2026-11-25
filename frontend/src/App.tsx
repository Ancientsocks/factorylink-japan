import React, { FormEvent, useEffect, useRef, useState } from 'react';
import {
  Activity, AlertTriangle, ArrowDownToLine, ArrowLeftRight, Bell, Boxes, Building2, CalendarClock,
  CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, ClipboardCheck, ClipboardList, Clock3,
  Download, FileText, Factory, Gauge, Globe2, HardHat, LayoutDashboard, LogOut, Menu, Package,
  PackageCheck, Plus, Search, Settings, ShieldCheck, Truck, Users, Wrench, X, Upload, RefreshCw,
  CircleHelp, CircleUserRound, Languages, ArrowUpRight, Barcode, ChartNoAxesCombined, FileSpreadsheet, BookOpen,
} from 'lucide-react';
import { humanStatus, Language, MessageKey, t } from './i18n';

type User = { id: number; email: string; full_name: string; role: string; language: Language; organization_id: number; organization_name: string; timezone?: string; currency?: string };
type Row = Record<string, any>;
type ModalMode = 'default' | 'equipment' | 'adjustment' | 'qualityTemplate';
type ReportDataset = 'production' | 'inventory' | 'quality';
class ErrorBoundary extends React.Component<{ children: React.ReactNode; language: Language }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      const ja = this.props.language === 'ja';
      return <div className="error-boundary" role="alert">
        <div className="error-boundary-icon"><AlertTriangle size={22} /></div>
        <h2>{ja ? 'この画面を表示できませんでした' : 'This screen could not be displayed'}</h2>
        <p>{this.state.error.message || (ja ? '予期しないエラーが発生しました。' : 'An unexpected error occurred.')}</p>
        <div className="inline-actions">
          <button className="primary-button" onClick={() => this.setState({ error: null })}>{ja ? '再試行' : 'Try again'}</button>
          <button className="subtle-button" onClick={() => window.location.reload()}>{ja ? '再読み込み' : 'Reload page'}</button>
        </div>
      </div>;
    }
    return this.props.children;
  }
}

function GoogleGlyph() {
  return <svg width="17" height="17" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.7 2.4 30.2 0 24 0 14.6 0 6.4 5.4 2.5 13.2l7.9 6.2C12.3 13.5 17.6 9.5 24 9.5z" /><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-2.8-.4-4.1H24v8.4h12.8c-.3 2.1-1.6 5.2-4.6 7.3l7.6 5.9c4.5-4.2 6.7-10.3 6.7-17.5z" /><path fill="#FBBC05" d="M10.4 28.6A14.5 14.5 0 0 1 9.6 24c0-1.6.3-3.2.8-4.6l-7.9-6.2A24 24 0 0 0 0 24c0 3.9.9 7.5 2.5 10.8l7.9-6.2z" /><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.8-5.9l-7.6-5.9c-2.1 1.4-4.9 2.4-8.2 2.4-6.4 0-11.7-4-13.6-9.9l-7.9 6.2C6.4 42.6 14.6 48 24 48z" /></svg>;
}

type Page = 'dashboard' | 'production' | 'inventory' | 'suppliers' | 'purchaseOrders' | 'quality' | 'traceability' | 'maintenance' | 'reports' | 'users' | 'documents' | 'notifications' | 'settings' | 'audit';
const ACCESS = 'factorylink.access';
const REFRESH = 'factorylink.refresh';

let refreshInFlight: Promise<string | null> | null = null;

async function rotateSessionToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const currentRefresh = sessionStorage.getItem(REFRESH);
    if (!currentRefresh) {
      sessionStorage.removeItem(ACCESS);
      window.dispatchEvent(new CustomEvent('factorylink:session-expired'));
      return null;
    }
    try {
      const response = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: currentRefresh }),
      });
      if (!response.ok) throw new Error('Session refresh failed');
      const payload = await response.json();
      sessionStorage.setItem(ACCESS, payload.access_token);
      sessionStorage.setItem(REFRESH, payload.refresh_token);
      window.dispatchEvent(new CustomEvent('factorylink:session', { detail: payload }));
      return payload.access_token as string;
    } catch {
      sessionStorage.removeItem(ACCESS);
      sessionStorage.removeItem(REFRESH);
      window.dispatchEvent(new CustomEvent('factorylink:session-expired'));
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function authorizedFetch(path: string, token: string, options: RequestInit = {}): Promise<Response> {
  const request = (accessToken: string) => {
    const headers = new Headers(options.headers ?? {});
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
    if (options.body && !(options.body instanceof FormData) && !(options.body instanceof Blob) && !headers.has('Content-Type')) {
      // JSON callers pass a string; FormData and Blob callers let the browser set boundaries/types.
      headers.set('Content-Type', 'application/json');
    }
    return fetch(path, { ...options, headers });
  };
  let response = await request(token || sessionStorage.getItem(ACCESS) || '');
  if (response.status === 401 && path !== '/api/v1/auth/refresh' && !path.endsWith('/auth/login') && !path.endsWith('/organizations/register')) {
    const freshToken = await rotateSessionToken();
    if (freshToken) response = await request(freshToken);
  }
  return response;
}

async function api<T = any>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const response = await authorizedFetch(path, token, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const payload = await response.json(); message = payload.detail ?? payload.message ?? message; } catch { /* response may be empty */ }
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function dateText(value: string | null | undefined, language: Language) {
  if (!value) return '—';
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(language === 'ja' ? 'ja-JP' : 'en-GB', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'Asia/Tokyo' }).format(date);
}
function money(value: number, language: Language) {
  return new Intl.NumberFormat(language === 'ja' ? 'ja-JP' : 'en-US', { style: 'currency', currency: 'JPY', maximumFractionDigits: 0 }).format(value || 0);
}
function statusClass(value: string) { return `status status-${String(value || '').toLowerCase().replaceAll('_', '-')}`; }

const navItems: { key: Page; label: MessageKey; icon: any; supplier?: boolean }[] = [
  { key: 'dashboard', label: 'dashboard', icon: LayoutDashboard, supplier: true },
  { key: 'production', label: 'production', icon: Factory },
  { key: 'inventory', label: 'inventory', icon: Boxes },
  { key: 'suppliers', label: 'suppliers', icon: Truck },
  { key: 'purchaseOrders', label: 'purchaseOrders', icon: ClipboardList, supplier: true },
  { key: 'quality', label: 'quality', icon: ShieldCheck },
  { key: 'traceability', label: 'traceability', icon: Barcode },
  { key: 'maintenance', label: 'maintenance', icon: Wrench },
  { key: 'reports', label: 'reports', icon: ChartNoAxesCombined },
  { key: 'users', label: 'users', icon: Users, supplier: true },
  { key: 'documents', label: 'documents', icon: FileText, supplier: true },
  { key: 'notifications', label: 'notifications', icon: Bell, supplier: true },
  { key: 'audit', label: 'audit', icon: Activity },
  { key: 'settings', label: 'settings', icon: Settings, supplier: true },
];
const pageTitle: Record<Page, MessageKey> = {
  dashboard: 'dashboard', production: 'production', inventory: 'inventory', suppliers: 'suppliers', purchaseOrders: 'purchaseOrders', quality: 'quality', traceability: 'traceability', maintenance: 'maintenance', reports: 'reports', users: 'users', documents: 'documents', notifications: 'notifications', settings: 'settings', audit: 'audit',
};

function App() {
  const [token, setToken] = useState(sessionStorage.getItem(ACCESS) || '');
  const [refreshToken, setRefreshToken] = useState(sessionStorage.getItem(REFRESH) || '');
  const [user, setUser] = useState<User | null>(null);
  const [language, setLanguage] = useState<Language>((localStorage.getItem('factorylink.language') as Language) || 'ja');
  const [page, setPage] = useState<Page>('dashboard');
  const [data, setData] = useState<Row | Row[] | null>(null);
  const [dataPage, setDataPage] = useState<Page | null>(null);
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const pageRequestId = useRef(0);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [toastActionLink, setToastActionLink] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [notificationPreview, setNotificationPreview] = useState<Row[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>('default');
  const [form, setForm] = useState<Row>({});
  const [editing, setEditing] = useState<Row | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{ path: string; label: string } | null>(null);
  const [rowBusy, setRowBusy] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [trace, setTrace] = useState<Row | null>(null);
  const [traceQuery, setTraceQuery] = useState('');

  const tr = (key: MessageKey) => t(language, key);
  const role = user?.role || '';
  const isSupplier = role === 'SUPPLIER_USER' || role === 'SUPPLIER_ADMIN';
  const canAdmin = role === 'ORG_ADMIN';
  const canManageUsers = role === 'ORG_ADMIN' || role === 'SUPPLIER_ADMIN';
  const canCreateProduction = canAdmin || role === 'PRODUCTION_MANAGER';
  const canUpdateProduction = canAdmin || role === 'PRODUCTION_MANAGER' || role === 'OPERATOR';
  const canReceiveInventory = canAdmin || role === 'WAREHOUSE_MANAGER';
  const canManageSuppliers = canAdmin || role === 'PRODUCTION_MANAGER';
  const canCreatePurchaseOrders = canManageSuppliers;
  const canUpdatePurchaseOrders = isSupplier || canAdmin || role === 'PRODUCTION_MANAGER' || role === 'WAREHOUSE_MANAGER';
  const canCreateQuality = canAdmin || role === 'QUALITY_INSPECTOR';
  const canManageMaintenance = canAdmin || role === 'MAINTENANCE_MANAGER';

  useEffect(() => {
    localStorage.setItem('factorylink.language', language);
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    const onSession = (event: Event) => {
      const payload = (event as CustomEvent<any>).detail;
      if (!payload?.access_token) return;
      setToken(payload.access_token);
      setRefreshToken(payload.refresh_token || sessionStorage.getItem(REFRESH) || '');
      if (payload.user) setUser(payload.user);
    };
    const onExpired = () => {
      setToken(''); setRefreshToken(''); setUser(null); setData(null); setPage('dashboard'); setNotificationPreview([]); setUnreadCount(0);
    };
    window.addEventListener('factorylink:session', onSession);
    window.addEventListener('factorylink:session-expired', onExpired);
    return () => {
      window.removeEventListener('factorylink:session', onSession);
      window.removeEventListener('factorylink:session-expired', onExpired);
    };
  }, []);

  useEffect(() => {
    let active = true;
    async function restore() {
      if (!token && refreshToken) {
        try {
          const refreshed = await api<any>('/api/v1/auth/refresh', '', { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken }) });
          if (!active) return;
          setToken(refreshed.access_token); setRefreshToken(refreshed.refresh_token);
          sessionStorage.setItem(ACCESS, refreshed.access_token); sessionStorage.setItem(REFRESH, refreshed.refresh_token);
          setUser(refreshed.user); setLanguage(refreshed.user.language || language);
          return;
        } catch { sessionStorage.removeItem(REFRESH); setRefreshToken(''); }
      }
      if (token) {
        try {
          const current = await api<User>('/api/v1/auth/me', token);
          if (active) { setUser(current); setLanguage(current.language || language); }
        } catch { sessionStorage.removeItem(ACCESS); setToken(''); }
      }
    }
    restore();
    return () => { active = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let active = true;
    if (!token || !user) { setUnreadCount(0); setNotificationPreview([]); return; }
    api<{ unread_count: number }>('/api/v1/notifications/unread-count', token)
      .then((result) => { if (active) setUnreadCount(result.unread_count); })
      .catch(() => { if (active) setUnreadCount(0); });
    return () => { active = false; };
  }, [token, user?.id]);

  async function loadPage(target: Page = page) {
    if (!token || !user) {
      pageRequestId.current += 1;
      setData(null);
      setPageLoading(false);
      return;
    }
    const requestId = ++pageRequestId.current;
    setPageLoading(true);
    setError('');
    try {
      let result: any = null;
      switch (target) {
        case 'dashboard':
          if (isSupplier) result = { purchase_orders: await api('/api/v1/purchase-orders', token) };
          else result = await api('/api/v1/dashboard', token);
          break;
        case 'production': result = await api('/api/v1/production/orders', token); break;
        case 'inventory': result = await api('/api/v1/inventory/batches', token); break;
        case 'suppliers': result = await api('/api/v1/suppliers', token); break;
        case 'purchaseOrders': result = await api('/api/v1/purchase-orders', token); break;
        case 'quality': {
          const [inspections, batches, finishedBatches, serials, templates, capas] = await Promise.all([
            api('/api/v1/quality/inspections', token), api('/api/v1/inventory/batches', token),
            api('/api/v1/quality/finished-batches', token), api('/api/v1/traceability/serials', token),
            api('/api/v1/quality/templates', token), api('/api/v1/quality/capa', token),
          ]);
          result = { inspections, batches, finishedBatches, serials, templates, capas }; break;
        }
        case 'maintenance': {
          const [tasks, equipment, analytics] = await Promise.all([
            api('/api/v1/maintenance/tasks', token), api('/api/v1/maintenance/equipment', token),
            api('/api/v1/maintenance/analytics', token),
          ]);
          result = { tasks, equipment, analytics }; break;
        }
        case 'traceability': result = { serials: await api('/api/v1/traceability/serials', token) }; break;
        case 'users': result = await api('/api/v1/users', token); break;
        case 'documents': result = await api('/api/v1/documents', token); break;
        case 'notifications': result = await api('/api/v1/notifications', token); break;
        case 'settings': result = await api('/api/v1/organizations/current', token); break;
        case 'audit': result = await api('/api/v1/audit', token); break;
        default: result = null;
      }
      if (requestId === pageRequestId.current) { setData(result); setDataPage(target); }
    } catch (err) {
      if (requestId === pageRequestId.current) setError(err instanceof Error ? err.message : tr('error'));
    } finally {
      if (requestId === pageRequestId.current) setPageLoading(false);
    }
  }

  useEffect(() => {
    if (!token || !user) {
      pageRequestId.current += 1;
      setData(null);
      setDataPage(null);
      setPageLoading(false);
      return;
    }
    // Clear the previous module while the newly selected module loads.
    setData(null);
    setDataPage(null);
    setError('');
    void loadPage(page);
    return () => {
      // Ignore requests that finish after navigation or sign-out.
      pageRequestId.current += 1;
    };
  }, [page, token, user]); // eslint-disable-line react-hooks/exhaustive-deps

  function notify(message: string, actionLink = '') { setToast(message); setToastActionLink(actionLink); window.setTimeout(() => { setToast(''); setToastActionLink(''); }, actionLink ? 15000 : 3200); }
  function setField(key: string, value: any) { setForm((current) => ({ ...current, [key]: value })); }

  async function signIn(event: FormEvent<HTMLFormElement>, email: string, password: string) {
    event.preventDefault(); setLoading(true); setError('');
    try {
      const result = await api<any>('/api/v1/auth/login', '', { method: 'POST', body: JSON.stringify({ email, password }) });
      sessionStorage.setItem(ACCESS, result.access_token); sessionStorage.setItem(REFRESH, result.refresh_token);
      setToken(result.access_token); setRefreshToken(result.refresh_token); setUser(result.user); setLanguage(result.user.language || language); setPage('dashboard');
    } catch (err) { setError(err instanceof Error ? err.message : tr('invalidLogin')); }
    finally { setLoading(false); }
  }

  async function registerOrganization(event: FormEvent<HTMLFormElement>, details: Row) {
    event.preventDefault(); setLoading(true); setError('');
    try {
      const result = await api<any>('/api/v1/organizations/register', '', { method: 'POST', body: JSON.stringify(details) });
      sessionStorage.setItem(ACCESS, result.access_token); sessionStorage.setItem(REFRESH, result.refresh_token);
      setToken(result.access_token); setRefreshToken(result.refresh_token); setUser(result.user); setLanguage(result.user.language || 'ja'); setPage('dashboard');
    } catch (err) { setError(err instanceof Error ? err.message : tr('registrationFailed')); }
    finally { setLoading(false); }
  }

  async function googleSession(result: any) {
    sessionStorage.setItem(ACCESS, result.access_token); sessionStorage.setItem(REFRESH, result.refresh_token);
    setToken(result.access_token); setRefreshToken(result.refresh_token); setUser(result.user);
    setLanguage(result.user.language || language); setPage('dashboard');
  }

  async function signOut() {
    try { if (token && refreshToken) await api('/api/v1/auth/logout', token, { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken }) }); } catch { /* local sign-out still proceeds */ }
    sessionStorage.removeItem(ACCESS); sessionStorage.removeItem(REFRESH); setToken(''); setRefreshToken(''); setUser(null); setData(null); setPage('dashboard'); setNotificationPreview([]); setUnreadCount(0);
  }

  async function runAction(path: string, status: string, note = '', downtimeMinutes = 0) {
    try { const body = path.includes('/maintenance/tasks/') ? { status, notes: note, downtime_minutes: downtimeMinutes } : { status, note }; await api(path, token, { method: 'PATCH', body: JSON.stringify(body) }); notify(tr('success')); await loadPage(); }
    catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  async function releaseQualityBatch(batchId: number, inspectionId: number, reason: string, finishedProduct = false) {
    try {
      const path = finishedProduct
        ? `/api/v1/quality/finished-batches/${batchId}/release`
        : `/api/v1/quality/batches/${batchId}/release`;
      await api(path, token, {
        method: 'POST', body: JSON.stringify({ inspection_id: inspectionId, reason }),
      });
      notify(tr('success'));
      await loadPage('quality');
    } catch (err) {
      setError(err instanceof Error ? err.message : tr('error'));
    }
  }

  async function saveEditedRecord() {
    if (!editing) return;
    const id = editing.id;
    if (page === 'suppliers') {
      const payload: Row = { code: form.code, name: form.name, contact_name: form.contact_name || '', email: form.email || '', phone: form.phone || '', prefecture: form.prefecture || '', status: form.status || 'ACTIVE' };
      if (String(form.supplier_organization_code ?? '').trim()) payload.supplier_organization_code = form.supplier_organization_code;
      await api(`/api/v1/suppliers/${id}`, token, { method: 'PATCH', body: JSON.stringify(payload) });
    }
    if (page === 'purchaseOrders') await api(`/api/v1/purchase-orders/${id}`, token, { method: 'PATCH', body: JSON.stringify({ supplier_id: Number(form.supplier_id), po_number: form.po_number, item_name: form.item_name, quantity: Number(form.quantity), unit: form.unit, unit_price: Number(form.unit_price || 0), due_date: form.due_date || null }) });
    if (page === 'production') await api(`/api/v1/production/orders/${id}`, token, { method: 'PATCH', body: JSON.stringify({ order_number: form.order_number, product_name: form.product_name, quantity: Number(form.quantity), material_name: form.material_name || '', material_required: Number(form.material_required || 0), due_date: form.due_date || null, track_serials: form.track_serials !== false }) });
    if (page === 'maintenance' && modalMode === 'equipment') await api(`/api/v1/maintenance/equipment/${id}`, token, { method: 'PATCH', body: JSON.stringify({ code: form.code, name: form.name, location: form.location || '', next_maintenance: form.next_maintenance || null }) });
    else if (page === 'maintenance') await api(`/api/v1/maintenance/tasks/${id}/details`, token, { method: 'PATCH', body: JSON.stringify({ equipment_id: Number(form.equipment_id), title: form.title, due_date: form.due_date || null, notes: form.notes || '', maintenance_type: form.maintenance_type || 'PREVENTIVE' }) });
    if (page === 'quality') {
      let criteria: any[] = [];
      try { criteria = JSON.parse(String(form.criteria_json || '[]')); } catch { throw new Error(language === 'ja' ? '検査基準JSONの形式が正しくありません。' : 'Quality criteria must be valid JSON.'); }
      await api(`/api/v1/quality/templates/${id}`, token, { method: 'PATCH', body: JSON.stringify({ name: form.name, process_type: form.process_type || 'FINAL', criteria }) });
    }
  }

  function openEdit(record: Row, mode: ModalMode = 'default') {
    const initial: Row = { ...record };
    if (page === 'purchaseOrders' || page === 'production' || page === 'maintenance') initial.due_date = record.due_date || '';
    if (page === 'maintenance') { initial.equipment_id = String(record.equipment_id ?? ''); initial.notes = record.notes || ''; initial.next_maintenance = record.next_maintenance || ''; }
    if (page === 'quality') initial.criteria_json = JSON.stringify(record.criteria || [], null, 2);
    setEditing(record); setForm(initial); setModalMode(mode); setModalOpen(true); setError('');
  }

  function requestDelete(path: string, label: string) { setConfirmDelete({ path, label }); setError(''); }

  async function performDelete() {
    if (!confirmDelete) return;
    setRowBusy(true); setError('');
    try {
      await api(confirmDelete.path, token, { method: 'DELETE' });
      setConfirmDelete(null); notify(tr('deleted')); await loadPage();
    } catch (err) {
      setConfirmDelete(null); setError(err instanceof Error ? err.message : tr('error'));
    } finally { setRowBusy(false); }
  }

  async function updateUser(id: number, payload: Row, message = tr('success')) {
    setRowBusy(true); setError('');
    try { await api(`/api/v1/users/${id}`, token, { method: 'PATCH', body: JSON.stringify(payload) }); notify(message); await loadPage(); }
    catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
    finally { setRowBusy(false); }
  }

  async function deactivateUser(id: number) {
    setRowBusy(true); setError('');
    try { await api(`/api/v1/users/${id}`, token, { method: 'DELETE' }); notify(tr('deactivated')); await loadPage(); }
    catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
    finally { setRowBusy(false); }
  }

  async function createRecord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError('');
    try {
      if (editing) {
        await saveEditedRecord();
        setModalOpen(false); setModalMode('default'); setForm({}); setEditing(null);
        notify(tr('success')); await loadPage();
        return;
      }
      if (page === 'suppliers') await api('/api/v1/suppliers', token, { method: 'POST', body: JSON.stringify(form) });
      if (page === 'purchaseOrders') await api('/api/v1/purchase-orders', token, { method: 'POST', body: JSON.stringify({ ...form, supplier_id: Number(form.supplier_id), quantity: Number(form.quantity), unit_price: Number(form.unit_price || 0) }) });
      if (page === 'production') await api('/api/v1/production/orders', token, { method: 'POST', body: JSON.stringify({ ...form, quantity: Number(form.quantity), material_required: Number(form.material_required || 0) }) });
      if (page === 'inventory' && modalMode === 'adjustment') await api('/api/v1/inventory/adjustments', token, { method: 'POST', body: JSON.stringify({ ...form, batch_id: Number(form.batch_id), quantity_delta: Number(form.quantity_delta) }) });
      else if (page === 'inventory') await api('/api/v1/inventory/receipts', token, { method: 'POST', body: JSON.stringify({ ...form, quantity: Number(form.quantity), unit_cost: Number(form.unit_cost || 0), supplier_id: form.supplier_id ? Number(form.supplier_id) : null, purchase_order_id: form.purchase_order_id ? Number(form.purchase_order_id) : null }) });
      if (page === 'quality' && modalMode === 'qualityTemplate') {
        let criteria: any[] = [];
        try { criteria = JSON.parse(String(form.criteria_json || '[]')); } catch { throw new Error(language === 'ja' ? '検査基準JSONの形式が正しくありません。' : 'Quality criteria must be valid JSON.'); }
        await api('/api/v1/quality/templates', token, { method: 'POST', body: JSON.stringify({ code: form.code, name: form.name, process_type: form.process_type || 'FINAL', criteria }) });
      } else if (page === 'quality') {
        await api('/api/v1/quality/inspections', token, { method: 'POST', body: JSON.stringify({
          ...form,
          batch_id: form.batch_id ? Number(form.batch_id) : null,
          finished_product_batch_id: form.finished_product_batch_id ? Number(form.finished_product_batch_id) : null,
          finished_product_serial_id: form.finished_product_serial_id ? Number(form.finished_product_serial_id) : null,
          template_id: form.template_id ? Number(form.template_id) : null,
          defect_count: Number(form.defect_count || 0),
          sample_size: Number(form.sample_size || 1),
          criteria_results: form.criteria_results || {},
        }) });
      }
      if (page === 'maintenance' && modalMode === 'equipment') await api('/api/v1/maintenance/equipment', token, { method: 'POST', body: JSON.stringify(form) });
      else if (page === 'maintenance') await api('/api/v1/maintenance/tasks', token, { method: 'POST', body: JSON.stringify({ ...form, equipment_id: Number(form.equipment_id) }) });
      let inviteResult: any = null;
      if (page === 'users') inviteResult = await api('/api/v1/users/invitations', token, { method: 'POST', body: JSON.stringify(form) });
      setModalOpen(false); setModalMode('default'); setForm({});
      notify(page === 'users' ? (language === 'ja' ? '招待を作成しました' : 'Invitation created') : tr('success'), inviteResult?.development_action_link || '');
      await loadPage();
    } catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
    finally { setLoading(false); }
  }

  async function updateCapa(id: number, values: Row) {
    try { await api(`/api/v1/quality/capa/${id}`, token, { method: 'PATCH', body: JSON.stringify(values) }); notify(tr('success')); await loadPage('quality'); }
    catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  async function shipSerial(serial: string, customerName: string, shipmentReference: string) {
    try {
      await api(`/api/v1/traceability/serials/${encodeURIComponent(serial)}/shipment`, token, { method: 'PATCH', body: JSON.stringify({ customer_name: customerName, shipment_reference: shipmentReference }) });
      notify(language === 'ja' ? '製品を出荷済みにしました' : 'Finished product marked as shipped'); await loadPage('traceability');
    } catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  async function downloadQR(kind: 'lot' | 'serial', identifier: string) {
    try {
      const response = await authorizedFetch(`/api/v1/traceability/qr/${kind}/${encodeURIComponent(identifier)}.svg`, token);
      if (!response.ok) throw new Error(language === 'ja' ? 'QRコードを生成できませんでした。' : 'QR code could not be generated.');
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `factorylink-${kind}-${identifier}.svg`; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    } catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  async function markNotificationRead(id: number) {
    try {
      await api(`/api/v1/notifications/${id}/read`, token, { method: 'PATCH' });
      const wasUnread = notificationPreview.some((item) => item.id === id && !item.is_read)
        || (Array.isArray(data) && data.some((item) => item.id === id && !item.is_read));
      setNotificationPreview((current) => current.map((item) => item.id === id ? { ...item, is_read: true } : item));
      setData((current) => Array.isArray(current) ? current.map((item) => item.id === id ? { ...item, is_read: true } : item) : current);
      if (wasUnread) setUnreadCount((current) => Math.max(0, current - 1));
    } catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  async function markAllNotificationsRead() {
    try {
      await api('/api/v1/notifications/read-all', token, { method: 'PATCH' });
      setUnreadCount(0);
      setNotificationPreview((current) => current.map((item) => ({ ...item, is_read: true })));
      setData((current) => Array.isArray(current) ? current.map((item) => ({ ...item, is_read: true })) : current);
      notify(tr('allNotificationsRead'));
    } catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  async function changeLanguage(next: Language) {
    setLanguage(next);
    if (token) {
      try { await api('/api/v1/auth/language', token, { method: 'PATCH', body: JSON.stringify({ language: next }) }); }
      catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
    }
  }

  async function searchTrace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setTrace(null); setError('');
    const raw = traceQuery.trim();
    const query = raw.replace(/^FACTORYLINK:(LOT|SERIAL):/i, '');
    try {
      const isSerial = /^FP-/i.test(query) || /^SERIAL:/i.test(raw) || /^FACTORYLINK:SERIAL:/i.test(raw);
      const identifier = query.replace(/^SERIAL:/i, '');
      setTrace(await api(isSerial ? `/api/v1/traceability/serials/${encodeURIComponent(identifier)}` : `/api/v1/traceability/${encodeURIComponent(identifier)}`, token));
    } catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  async function downloadReport(dataset: ReportDataset, kind: 'csv' | 'xlsx') {
    try {
      const response = await authorizedFetch(`/api/v1/reports/${dataset}.${kind}`, token);
      if (!response.ok) throw new Error(language === 'ja' ? 'レポートを生成できませんでした。' : 'Report could not be generated.');
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a');
      a.href = url; a.download = `factorylink-${dataset}-report.${kind}`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      notify(language === 'ja' ? 'レポートをダウンロードしました' : 'Report downloaded');
    } catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const input = (event.currentTarget.elements.namedItem('document') as HTMLInputElement);
    const file = input.files?.[0]; if (!file) return;
    if (file.size > 10 * 1024 * 1024) { setError(tr('fileTooLarge')); return; }
    const formData = new FormData(); formData.append('file', file);
    const poId = (event.currentTarget.elements.namedItem('purchase_order_id') as HTMLSelectElement)?.value;
    if (poId) formData.append('purchase_order_id', poId);
    try { await api('/api/v1/documents', token, { method: 'POST', body: formData }); notify(tr('success')); await loadPage(); input.value = ''; }
    catch (err) { setError(err instanceof Error ? err.message : tr('uploadFailed')); }
  }

  async function downloadDocument(id: number, name: string) {
    try {
      const response = await authorizedFetch(`/api/v1/documents/${id}/download`, token);
      if (!response.ok) throw new Error('Download failed');
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
    } catch (err) { setError(err instanceof Error ? err.message : tr('error')); }
  }

  if (!user) return <Login language={language} onLanguage={setLanguage} onSubmit={signIn} onRegister={registerOrganization} onGoogleSession={googleSession} loading={loading} error={error} />;

  const visibleNav = navItems.filter((item) => {
    if (isSupplier) return Boolean(item.supplier) && (item.key !== 'users' || canManageUsers);
    if ((item.key === 'audit' || item.key === 'users') && !canManageUsers) return false;
    return true;
  });
  // Only hand a page the payload that belongs to it. Rendering the previous
  // module's rows here used to crash on shape differences (e.g. a supplier row
  // has no quantity) and blank the whole application.
  const pageData = dataPage === page ? (data as any) : null;
  const openCreate = (mode: ModalMode = 'default') => { setEditing(null); setForm({}); setModalMode(mode); setModalOpen(true); };

  return <div className="app-shell">
    {sidebarOpen && <button className="mobile-scrim" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" />}
    <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <div className="brand-block"><div className="brand-mark"><Factory size={22} /></div><div><div className="brand-name">FactoryLink</div><div className="brand-caption">{isSupplier ? tr('supplierPortal') : tr('tagline')}</div></div><button className="icon-button sidebar-close" onClick={() => setSidebarOpen(false)}><X size={18} /></button></div>
      <div className="workspace-label">{tr('organization')}</div>
      <div className="workspace-card"><div className="workspace-icon"><Building2 size={17} /></div><div className="workspace-copy"><strong>{user.organization_name}</strong><span>{isSupplier ? tr('supplierPortal') : tr('factory')}</span></div><ChevronDown size={15} /></div>
      <div className="nav-label">{tr('overview')}</div>
      <nav className="main-nav">{visibleNav.map((item) => {
        const Icon = item.icon;
        return <button key={item.key} className={`nav-item ${page === item.key ? 'active' : ''}`} onClick={() => { setPage(item.key); setSidebarOpen(false); setError(''); }}><Icon size={18} strokeWidth={1.8} /><span>{tr(item.label)}</span>{item.key === 'notifications' && unreadCount > 0 && <span className="nav-unread-count">{unreadCount > 99 ? '99+' : unreadCount}</span>}</button>;
      })}</nav>
      <div className="sidebar-bottom"><button type="button" className="help-card" onClick={() => setHelpOpen(true)} aria-haspopup="dialog" aria-expanded={helpOpen}><div className="help-icon"><CircleHelp size={16} /></div><div><strong>{language === 'ja' ? 'サポートが必要ですか？' : 'Need a hand?'}</strong><span>{language === 'ja' ? 'ヘルプとガイド' : 'Help & product guide'}</span></div><ArrowUpRight size={14} /></button><div className="user-card"><div className="avatar">{user.full_name.split(' ').map((x) => x[0]).join('').slice(0, 2)}</div><div className="user-copy"><strong>{user.full_name}</strong><span>{humanStatus(language, user.role)}</span></div><button className="icon-button signout-button" onClick={signOut} title={tr('signOut')}><LogOut size={16} /></button></div></div>
    </aside>

    <main className="main-area">
      <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)}><Menu size={20} /></button><div className="breadcrumbs"><span>{tr('brand')}</span><ChevronRight size={14} /><strong>{tr(pageTitle[page])}</strong></div></div><div className="topbar-actions"><div className="locale-select"><Globe2 size={16} /><select value={language} onChange={(e) => changeLanguage(e.target.value as Language)} aria-label={tr('language')}><option value="ja">日本語</option><option value="en">English</option></select><ChevronDown size={13} /></div><div className="notification-wrap"><button className={`icon-button top-notification ${notificationOpen ? 'selected' : ''}`} onClick={() => { const opening = !notificationOpen; setNotificationOpen(opening); if (opening) api<Row[]>('/api/v1/notifications', token).then(setNotificationPreview).catch((err) => setError(err instanceof Error ? err.message : tr('error'))); }} aria-label={`${tr('notifications')}${unreadCount ? `, ${unreadCount} ${tr('unread')}` : ''}`}><Bell size={18} />{unreadCount > 0 && <span className="notification-count">{unreadCount > 99 ? '99+' : unreadCount}</span>}</button>{notificationOpen && <div className="notification-popover"><div className="popover-heading"><strong>{tr('notifications')} <span className="popover-unread">{unreadCount ? `${unreadCount} ${tr('unread')}` : tr('allCaughtUp')}</span></strong><button className="text-link" onClick={() => { setPage('notifications'); setNotificationOpen(false); }}>{tr('viewAll')}</button></div>{notificationPreview.slice(0, 4).map((n) => <div className={`mini-notice ${n.is_read ? 'mini-notice-read' : ''}`} key={n.id}><span className={`notice-dot ${String(n.level).toLowerCase()}`} /><div><strong>{n.title}</strong><span>{n.body}</span></div>{!n.is_read && <button className="mini-mark-read" onClick={() => markNotificationRead(n.id)} aria-label={tr('markRead')}>✓</button>}</div>)}{!notificationPreview.length && <div className="mini-notice"><div><span>{tr('noRecords')}</span></div></div>}{unreadCount > 0 && <button className="popover-footer" onClick={markAllNotificationsRead}>{tr('markAllRead')}</button>}<button className="popover-footer" onClick={() => { setPage('notifications'); setNotificationOpen(false); }}>{tr('viewAll')} <ArrowUpRight size={13} /></button></div>}</div><div className="top-user"><div className="avatar avatar-small">{user.full_name.split(' ').map((x) => x[0]).join('').slice(0, 2)}</div><div><strong>{user.full_name}</strong><span>{humanStatus(language, user.role)}</span></div></div></div></header>
      <section className="content-area">
        {error && <div className="alert alert-error"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError('')}><X size={15} /></button></div>}
        {(loading || pageLoading) && <div className="loading-strip"><span />{tr('loading')}</div>}
        {pageLoading && data === null ? (
          <div role="status" aria-live="polite" style={{ minHeight: 260, display: 'grid', placeItems: 'center', color: '#64748b' }}>
            <strong>{tr('loading')}</strong>
          </div>
        ) : (
          <ErrorBoundary language={language} key={page}>
        {page === 'dashboard' && (isSupplier ? <SupplierDashboard data={pageData?.purchase_orders || []} language={language} onNavigate={setPage} onStatus={runAction} /> : <Dashboard data={pageData} language={language} onNavigate={setPage} />)}
        {page === 'production' && <ProductionPage rows={Array.isArray(pageData) ? pageData : []} language={language} onCreate={openCreate} canCreate={canCreateProduction} canUpdate={canUpdateProduction} canEdit={canCreateProduction} onEdit={(r: Row) => openEdit(r)} onDelete={(r: Row) => requestDelete(`/api/v1/production/orders/${r.id}`, r.order_number)} onStatus={runAction} onProgress={async (id, completed, rejected) => { try { await api(`/api/v1/production/orders/${id}/progress`, token, { method: 'PATCH', body: JSON.stringify({ completed_quantity: completed, rejected_quantity: rejected }) }); notify(tr('success')); await loadPage(); } catch (err) { setError(err instanceof Error ? err.message : tr('error')); } }} searchTerm={searchTerm} setSearchTerm={setSearchTerm} />}
        {page === 'inventory' && <InventoryPage rows={Array.isArray(pageData) ? pageData : []} language={language} onCreate={() => openCreate()} onAdjust={() => openCreate('adjustment')} canReceive={canReceiveInventory} onTrace={(lot) => { setPage('traceability'); setTraceQuery(lot); setTrace(null); }} />}
        {page === 'suppliers' && <SuppliersPage rows={Array.isArray(pageData) ? pageData : []} language={language} onCreate={openCreate} canCreate={canManageSuppliers} canManage={canManageSuppliers} onEdit={(r: Row) => openEdit(r)} onDelete={(r: Row) => requestDelete(`/api/v1/suppliers/${r.id}`, r.name)} />}
        {page === 'purchaseOrders' && <PurchaseOrdersPage rows={Array.isArray(pageData) ? pageData : []} language={language} onCreate={openCreate} canCreate={canCreatePurchaseOrders} canUpdate={canUpdatePurchaseOrders} onStatus={runAction} isSupplier={isSupplier} canManage={canCreatePurchaseOrders} onEdit={(r: Row) => openEdit(r)} onDelete={(r: Row) => requestDelete(`/api/v1/purchase-orders/${r.id}`, r.po_number)} />}
        {page === 'quality' && <QualityPage rows={pageData?.inspections || []} batches={pageData?.batches || []} finishedBatches={pageData?.finishedBatches || []} templates={pageData?.templates || []} capas={pageData?.capas || []} language={language} onCreate={openCreate} canCreate={canCreateQuality} onRelease={releaseQualityBatch} onCreateTemplate={() => openCreate('qualityTemplate')} onEditTemplate={(r: Row) => openEdit(r, 'qualityTemplate')} onDeleteTemplate={(r: Row) => requestDelete(`/api/v1/quality/templates/${r.id}`, r.name)} onCapaUpdate={updateCapa} />}
        {page === 'traceability' && <TraceabilityPage language={language} query={traceQuery} setQuery={setTraceQuery} onSearch={searchTrace} result={trace} serials={pageData?.serials || []} onDownloadQR={downloadQR} onShip={shipSerial} />}
        {page === 'maintenance' && <MaintenancePage tasks={pageData?.tasks || []} equipment={pageData?.equipment || []} analytics={pageData?.analytics || {}} language={language} onCreate={() => openCreate()} onCreateEquipment={() => openCreate('equipment')} canManage={canManageMaintenance} onUpdate={runAction} onEditTask={(r: Row) => openEdit(r)} onDeleteTask={(r: Row) => requestDelete(`/api/v1/maintenance/tasks/${r.id}`, r.title)} onEditEquipment={(r: Row) => openEdit(r, 'equipment')} onDeleteEquipment={(r: Row) => requestDelete(`/api/v1/maintenance/equipment/${r.id}`, r.name)} />}
        {page === 'reports' && <ReportsPage language={language} onDownload={downloadReport} />}
        {page === 'users' && <UsersPage rows={Array.isArray(pageData) ? pageData : []} language={language} onCreate={openCreate} canManage={canManageUsers} currentUserId={user.id} busy={rowBusy} onUpdate={updateUser} onRemove={deactivateUser} />}
        {page === 'documents' && <DocumentsPage rows={Array.isArray(pageData) ? pageData : []} language={language} onUpload={uploadDocument} onDownload={downloadDocument} onDelete={(r: Row) => requestDelete(`/api/v1/documents/${r.id}`, r.display_name)} onOrders={loadPOs} isSupplier={isSupplier} />}
        {page === 'notifications' && <NotificationsPage rows={Array.isArray(pageData) ? pageData : []} language={language} unreadCount={unreadCount} onRead={markNotificationRead} onReadAll={markAllNotificationsRead} />}
        {page === 'settings' && <SettingsPage organization={pageData || {}} language={language} onLanguage={changeLanguage} onReload={() => loadPage()} />}
        {page === 'audit' && <AuditPage rows={Array.isArray(pageData) ? pageData : []} language={language} />}
          </ErrorBoundary>
        )}
      </section>
    </main>
    {modalOpen && <CreateModal page={page} mode={modalMode} editing={Boolean(editing)} language={language} isSupplier={isSupplier} form={form} setField={setField} data={pageData} onClose={() => { setModalOpen(false); setModalMode('default'); setEditing(null); }} onSubmit={createRecord} loading={loading} />}
    {confirmDelete && <ConfirmDialog language={language} label={confirmDelete.label} busy={rowBusy} onCancel={() => setConfirmDelete(null)} onConfirm={performDelete} />}
    {helpOpen && <HelpGuide language={language} isSupplier={isSupplier} canManageUsers={canManageUsers} onClose={() => setHelpOpen(false)} onNavigate={(target) => { setPage(target); setHelpOpen(false); setSidebarOpen(false); setError(''); }} />}
    {toast && <div className="toast"><CheckCircle2 size={17} />{toast}{toastActionLink && <a href={toastActionLink} target="_blank" rel="noreferrer">{language === 'ja' ? '招待リンクを開く' : 'Open invitation link'}</a>}</div>}
  </div>;

  async function loadPOs() { try { return await api('/api/v1/purchase-orders', token); } catch { return []; } }
}


type HelpTopic = {
  id: string;
  titleEn: string;
  titleJa: string;
  summaryEn: string;
  summaryJa: string;
  page?: Page;
  icon: any;
  supplierOnly?: boolean;
  stepsEn: string[];
  stepsJa: string[];
  tipEn: string;
  tipJa: string;
};

const helpTopics: HelpTopic[] = [
  {
    id: 'start', titleEn: 'Getting started', titleJa: 'はじめに',
    summaryEn: 'Set up your factory workspace and understand the daily operating flow.', summaryJa: '工場のワークスペースを設定し、日々の運用フローを確認します。',
    page: 'settings', icon: LayoutDashboard,
    stepsEn: ['Confirm your organisation name, language and timezone in Settings.', 'Ask an organisation administrator to invite each employee from Users & Access and assign only the role they need.', 'Register your suppliers and confirm each supplier workspace code before creating purchase orders.', 'Use the Dashboard to review open work, stock, quality alerts and recent activity.'],
    stepsJa: ['設定で会社名、表示言語、タイムゾーンを確認します。', '組織管理者が「ユーザーとアクセス」から従業員を招待し、必要な権限だけを割り当てます。', '発注前に仕入先を登録し、仕入先ワークスペースコードを確認します。', 'ダッシュボードで未完了作業、在庫、品質アラート、最近の操作を確認します。'],
    tipEn: 'Start with test records. Do not import confidential factory or customer data until production security, backups and customer acceptance are complete.',
    tipJa: 'まずテストデータで操作してください。セキュリティ、バックアップ、顧客受入確認が完了するまで機密データを登録しないでください。',
  },
  {
    id: 'supplier', titleEn: 'Supplier portal', titleJa: '仕入先ポータル',
    summaryEn: 'How supplier users work with purchase orders and shared documents.', summaryJa: '仕入先ユーザーが発注書と共有ドキュメントを扱う方法です。',
    page: 'purchaseOrders', icon: Truck, supplierOnly: true,
    stepsEn: ['Open Purchase Orders to see orders shared with your supplier workspace.', 'Review the item, ordered quantity and requested delivery date before confirming.', 'Update the order status as permitted by your workflow and communicate delivery changes promptly.', 'Open Documents to review or upload files shared for the relevant purchase order.'],
    stepsJa: ['「発注書」を開き、仕入先ワークスペースに共有された注文を確認します。', '確認前に品目、発注数量、希望納期を確認します。', '運用で許可された注文ステータスを更新し、納期変更は速やかに連絡します。', '「ドキュメント」で該当発注書に共有されたファイルを確認またはアップロードします。'],
    tipEn: 'Supplier accounts are isolated from factory inventory, production, quality, maintenance and internal reports.',
    tipJa: '仕入先アカウントから工場の在庫、生産、品質、保全、社内レポートにはアクセスできません。',
  },
  {
    id: 'suppliers', titleEn: 'Suppliers', titleJa: '仕入先管理',
    summaryEn: 'Create supplier records and connect a supplier workspace.', summaryJa: '仕入先情報を登録し、仕入先ワークスペースを接続します。',
    page: 'suppliers', icon: Truck,
    stepsEn: ['Open Suppliers and create a supplier record with its business name and contact details.', 'When the supplier uses FactoryLink, enter the supplier workspace code provided by that supplier.', 'Check that the supplier relationship is correct before sharing purchase orders or documents.', 'Keep supplier email and contact details current so purchasing communication reaches the right people.'],
    stepsJa: ['「仕入先」を開き、会社名と連絡先を登録します。', '仕入先もFactoryLinkを利用する場合、仕入先から提供されたワークスペースコードを入力します。', '発注書やドキュメントを共有する前に、仕入先との紐付けを確認します。', '購買連絡が正しい担当者に届くよう、メールアドレスと連絡先を最新に保ちます。'],
    tipEn: 'A supplier workspace code is provided by the supplier; do not guess or reuse another company’s code.',
    tipJa: '仕入先ワークスペースコードは仕入先から受け取ってください。他社のコードを推測または流用しないでください。',
  },
  {
    id: 'purchaseOrders', titleEn: 'Purchase orders', titleJa: '発注書',
    summaryEn: 'Create an order, share it with a supplier and follow delivery.', summaryJa: '発注書を作成し、仕入先と共有して納品を追跡します。',
    page: 'purchaseOrders', icon: ClipboardList,
    stepsEn: ['Select Purchase Orders and create an order for a registered supplier.', 'Enter a unique purchase-order number, item, quantity, unit price if used, and due date.', 'Submit the order so it becomes available to the linked supplier workspace.', 'Track supplier confirmation and delivery status. Record each partial delivery as a separate receipt in Inventory.'],
    stepsJa: ['「発注書」で登録済みの仕入先を選び、注文を作成します。', '一意の発注番号、品目、数量、必要に応じて単価と納期を入力します。', '発注書を送信し、紐付いた仕入先ワークスペースで確認できるようにします。', '仕入先の確認と納品状況を追跡します。分納は在庫で別々の入庫として記録します。'],
    tipEn: 'Use a distinct receipt reference and lot number for each partial delivery. Total receipts cannot exceed the ordered quantity.',
    tipJa: '分納ごとに異なる入庫参照番号とロット番号を使用します。累計入庫数量は発注数量を超えられません。',
  },
  {
    id: 'inventory', titleEn: 'Inventory & receiving', titleJa: '在庫・入庫',
    summaryEn: 'Receive materials, track lots and maintain an auditable stock ledger.', summaryJa: '材料を入庫し、ロットを追跡し、監査可能な在庫台帳を維持します。',
    page: 'inventory', icon: Boxes,
    stepsEn: ['Open Inventory and choose Receive Stock. Link the receipt to its purchase order when applicable.', 'Enter the material, unique lot number, received quantity, unit, supplier and receipt reference.', 'Check on-hand and reserved quantities. Use the lot trace action to follow material history.', 'For a stock correction, use the adjustment action and enter a clear reference and reason.'],
    stepsJa: ['「在庫」で入庫を選択します。該当する場合は発注書に紐付けます。', '材料、重複しないロット番号、入庫数量、単位、仕入先、入庫参照番号を入力します。', '現在庫と引当済数量を確認し、ロット追跡から材料履歴を確認します。', '在庫修正では調整機能を使い、明確な参照番号と理由を入力します。'],
    tipEn: 'Do not overwrite stock outside the ledger. Negative adjustments cannot reduce stock below quantities reserved for production.',
    tipJa: '台帳を経由せず在庫数量を変更しないでください。マイナス調整で生産引当数量を下回ることはできません。',
  },
  {
    id: 'production', titleEn: 'Production', titleJa: '生産管理',
    summaryEn: 'Plan a production order, reserve materials and record completed output.', summaryJa: '生産オーダーを計画し、材料を引き当て、完成数量を記録します。',
    page: 'production', icon: Factory,
    stepsEn: ['Create a production order with a unique order number, product, planned quantity and due date.', 'Enter material requirements so eligible inventory can be reserved for the order.', 'Move the order through the allowed statuses and update completed and rejected quantities as work progresses.', 'Complete the order only after the physical production result has been checked. Reserved materials are consumed transactionally; accepted units receive serials when serial tracking is enabled.'],
    stepsJa: ['一意のオーダー番号、製品、計画数量、納期を指定して生産オーダーを作成します。', '材料所要量を入力し、対象在庫をオーダーに引き当てます。', '許可されたステータスに従って進め、作業中に完成数量と不良数量を更新します。', '実際の生産結果を確認してから完了にします。引当材料はトランザクションで消費され、シリアル管理が有効な場合は合格品に番号が付与されます。'],
    tipEn: 'Check available stock and quality holds before starting. Cancelled orders release reservations according to the business rules.',
    tipJa: '開始前に使用可能在庫と品質保留を確認します。キャンセル時は業務ルールに従って引当が解除されます。',
  },
  {
    id: 'quality', titleEn: 'Quality & CAPA', titleJa: '品質・是正処置',
    summaryEn: 'Inspect materials and finished goods, contain failures and document corrective action.', summaryJa: '材料と完成品を検査し、不適合を封じ込め、是正処置を記録します。',
    page: 'quality', icon: ShieldCheck,
    stepsEn: ['Review inspection templates for receiving, in-process or final inspection.', 'Create an inspection against the relevant material lot or finished-product batch and enter the required criteria and sample results.', 'A failed criterion results in a failed inspection, puts the lot on quality hold and opens a CAPA case.', 'Record containment, root cause, corrective and preventive actions, verification evidence and closure. Release a held batch only through the authorised release workflow.'],
    stepsJa: ['受入、工程内、最終検査の検査テンプレートを確認します。', '対象の材料ロットまたは完成品バッチに検査を作成し、基準とサンプル結果を入力します。', '基準不合格の場合、検査は不合格となり、ロットが品質保留され、CAPAケースが作成されます。', '封じ込め、根本原因、是正・予防処置、検証証拠、完了を記録します。保留ロットの解除は権限を持つ担当者が承認フローで行います。'],
    tipEn: 'Never bypass a quality hold. Release requires a later passing inspection and a documented reason.',
    tipJa: '品質保留を回避しないでください。解除には後続の合格検査と記録された理由が必要です。',
  },
  {
    id: 'traceability', titleEn: 'Traceability & shipping', titleJa: 'トレーサビリティ・出荷',
    summaryEn: 'Trace a material lot or finished serial from supplier through production and shipment.', summaryJa: '材料ロットまたは完成品シリアルを仕入先から生産、出荷まで追跡します。',
    page: 'traceability', icon: Barcode,
    stepsEn: ['Open Traceability and search by a material lot number or finished-product serial number.', 'Review upstream supplier, purchase order and receipt information, then inspect downstream production, quality and CAPA events.', 'Use the QR download or camera scan where supported. Manual identifier entry is always the fallback.', 'Ship only eligible finished serials and record the customer and shipment reference. Serials linked to held material are quarantined.'],
    stepsJa: ['「トレーサビリティ」で材料ロット番号または完成品シリアル番号を検索します。', '上流の仕入先、発注書、入庫情報を確認し、下流の生産、品質、CAPAイベントを確認します。', '対応環境ではQRダウンロードまたはカメラスキャンを使用します。手入力検索も利用できます。', '出荷可能な完成品シリアルのみを出荷し、顧客名と出荷参照番号を記録します。保留材料に紐付くシリアルは隔離されます。'],
    tipEn: 'If camera scanning is unavailable in the browser, enter the lot or serial identifier manually.',
    tipJa: 'ブラウザーがカメラスキャンに対応していない場合は、ロット番号またはシリアル番号を手入力してください。',
  },
  {
    id: 'maintenance', titleEn: 'Equipment & maintenance', titleJa: '設備・保全',
    summaryEn: 'Register factory equipment and record preventive or unplanned maintenance.', summaryJa: '工場設備を登録し、予防保全や突発保全を記録します。',
    page: 'maintenance', icon: Wrench,
    stepsEn: ['Register equipment with a unique equipment code, name and location.', 'Create preventive maintenance tasks with a due date, or record an unplanned repair.', 'Update the task as work proceeds and record completion notes and downtime details.', 'Review downtime analytics. Availability is meaningful only when planned operating minutes are supplied for the period.'],
    stepsJa: ['一意の設備コード、名称、設置場所で設備を登録します。', '期限を指定して予防保全タスクを作成するか、突発修理を記録します。', '作業の進捗を更新し、完了メモと停止時間を記録します。', '停止時間分析を確認します。稼働率の評価には対象期間の計画稼働時間が必要です。'],
    tipEn: 'Record actual downtime consistently; analytics depend on the quality of the entered operating data.',
    tipJa: '実際の停止時間を一貫した方法で記録してください。分析結果は入力データの品質に依存します。',
  },
  {
    id: 'reports', titleEn: 'Reports, notifications & audit', titleJa: 'レポート・通知・監査',
    summaryEn: 'Export operational data and review system activity.', summaryJa: '業務データをエクスポートし、システム操作を確認します。',
    page: 'reports', icon: ChartNoAxesCombined,
    stepsEn: ['Open Reports and select the available production, inventory or quality dataset.', 'Review the displayed scope and filters before downloading CSV or XLSX.', 'Use Notifications to review operational events and mark them read.', 'Administrators can review Audit Logs for recorded business actions. Audit records are not ordinary editable records.'],
    stepsJa: ['「レポート」で生産、在庫、品質の利用可能なデータセットを選択します。', 'CSVまたはXLSXをダウンロードする前に、対象範囲とフィルターを確認します。', '「通知」で業務イベントを確認し、既読にします。', '管理者は「監査ログ」で記録された業務操作を確認できます。監査記録は通常の編集可能データではありません。'],
    tipEn: 'Exports can contain operational information. Store downloaded reports only in approved locations.',
    tipJa: 'エクスポートには業務情報が含まれる場合があります。ダウンロードしたレポートは承認済みの場所に保管してください。',
  },
  {
    id: 'users', titleEn: 'Users & access', titleJa: 'ユーザー・アクセス権',
    summaryEn: 'Invite employees and assign role-based access.', summaryJa: '従業員を招待し、役割に応じたアクセス権を割り当てます。',
    page: 'users', icon: Users,
    stepsEn: ['An organisation administrator opens Users & Access and creates an invitation using the employee’s name, work email and role.', 'The invitation link is sent by email when SMTP is configured. In local development, the generated link may be shown in the app.', 'The invited employee opens the link and sets their own password.', 'Assign the least-privilege role: Production Manager, Warehouse Manager, Quality Inspector, Maintenance Manager or Operator. Supplier users belong in their supplier workspace.'],
    stepsJa: ['組織管理者が「ユーザーとアクセス」を開き、従業員名、業務用メールアドレス、役割を指定して招待します。', 'SMTP設定済みの場合、招待リンクはメールで送信されます。ローカル開発ではアプリ内にリンクが表示される場合があります。', '招待された従業員がリンクを開き、自分のパスワードを設定します。', '生産管理者、倉庫管理者、品質検査員、保全管理者、オペレーターなど、必要最小限の権限を割り当てます。仕入先ユーザーは仕入先ワークスペースに所属します。'],
    tipEn: 'Do not share one login between employees. Production self-registration is intentionally disabled; use administrator invitations.',
    tipJa: '複数の従業員で同じログインを共有しないでください。本番環境の一般登録は無効にし、管理者招待を利用します。',
  },
  {
    id: 'documents', titleEn: 'Documents', titleJa: 'ドキュメント',
    summaryEn: 'Upload and retrieve files shared with your workspace.', summaryJa: 'ワークスペースで共有されたファイルをアップロード・取得します。',
    page: 'documents', icon: FileText, supplierOnly: true,
    stepsEn: ['Open Documents and select a file to upload.', 'When the file belongs to a purchase order, select the related order before uploading.', 'Use the document list to download files available to your workspace.', 'Only upload business files approved for sharing with the linked supplier or factory workspace.'],
    stepsJa: ['「ドキュメント」を開き、アップロードするファイルを選択します。', '発注書に関連するファイルの場合、アップロード前に該当発注書を選択します。', 'ドキュメント一覧からワークスペースで利用可能なファイルをダウンロードします。', '紐付いた仕入先または工場ワークスペースとの共有が承認された業務ファイルのみアップロードしてください。'],
    tipEn: 'Uploaded files are subject to the configured file-size and malware-scanning controls.',
    tipJa: 'アップロードファイルには、設定されたファイルサイズ制限とマルウェアスキャン制御が適用されます。',
  },
];

function HelpGuide({ language, isSupplier, canManageUsers, onClose, onNavigate }: {
  language: Language;
  isSupplier: boolean;
  canManageUsers: boolean;
  onClose: () => void;
  onNavigate: (page: Page) => void;
}) {
  const [activeId, setActiveId] = useState(isSupplier ? 'supplier' : 'start');
  const ja = language === 'ja';
  const topics = isSupplier
    ? helpTopics.filter((topic) => ['start', 'supplier', 'documents'].includes(topic.id))
    : helpTopics.filter((topic) => !topic.supplierOnly && (topic.id !== 'users' || canManageUsers));
  const active = topics.find((topic) => topic.id === activeId) || topics[0];
  const TopicIcon = active.icon;
  const steps = ja ? active.stepsJa : active.stepsEn;
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKeyDown);
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKeyDown); document.body.style.overflow = oldOverflow; };
  }, [onClose]);
  return <div className="help-guide-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="help-guide-dialog" role="dialog" aria-modal="true" aria-labelledby="help-guide-title">
      <header className="help-guide-header">
        <div className="help-guide-brand"><span className="help-guide-brand-icon"><BookOpen size={20} /></span><div><span className="help-guide-eyebrow">FACTORYLINK ACADEMY</span><h2 id="help-guide-title">{ja ? 'ヘルプと製品ガイド' : 'Help & product guide'}</h2><p>{ja ? '工場チームのための操作ガイド' : 'Practical instructions for your factory team'}</p></div></div>
        <button type="button" className="icon-button help-guide-close" onClick={onClose} aria-label={ja ? '閉じる' : 'Close guide'}><X size={19} /></button>
      </header>
      <div className="help-guide-layout">
        <nav className="help-guide-nav" aria-label={ja ? 'ガイドの項目' : 'Guide topics'}>
          <span className="help-guide-nav-label">{ja ? 'ガイド項目' : 'GUIDE TOPICS'}</span>
          {topics.map((topic) => {
            const Icon = topic.icon;
            return <button type="button" key={topic.id} className={`help-guide-nav-item ${active.id === topic.id ? 'active' : ''}`} onClick={() => setActiveId(topic.id)} aria-current={active.id === topic.id ? 'page' : undefined}>
              <Icon size={16} /><span>{ja ? topic.titleJa : topic.titleEn}</span><ChevronRight size={14} />
            </button>;
          })}
        </nav>
        <article className="help-guide-article">
          <div className="help-guide-topic-icon"><TopicIcon size={22} /></div>
          <div className="help-guide-topic-kicker">{ja ? '操作ガイド' : 'WORKFLOW GUIDE'}</div>
          <h3>{ja ? active.titleJa : active.titleEn}</h3>
          <p className="help-guide-summary">{ja ? active.summaryJa : active.summaryEn}</p>
          <ol className="help-guide-steps">{steps.map((step, index) => <li key={`${active.id}-${index}`}><span className="help-guide-step-number">{String(index + 1).padStart(2, '0')}</span><span>{step}</span></li>)}</ol>
          <div className="help-guide-tip"><ShieldCheck size={17} /><div><strong>{ja ? '重要なポイント' : 'Important to remember'}</strong><p>{ja ? active.tipJa : active.tipEn}</p></div></div>
          {active.page && <button type="button" className="primary-button help-guide-open-page" onClick={() => onNavigate(active.page!)}>{ja ? 'この画面を開く' : `Open ${active.titleEn}`}<ArrowUpRight size={15} /></button>}
          <p className="help-guide-footnote">{ja ? '画面や操作は、所属組織と割り当てられた役割によって異なる場合があります。' : 'Available screens and actions depend on your organisation and assigned role.'}</p>
        </article>
      </div>
      <footer className="help-guide-footer"><span>{ja ? 'FactoryLink · 製造業務ワークスペース' : 'FactoryLink · Manufacturing operations workspace'}</span><button type="button" className="text-link" onClick={onClose}>{ja ? 'ガイドを閉じる' : 'Close guide'}</button></footer>
    </section>
  </div>;
}

function Login({ language, onLanguage, onSubmit, onRegister, onGoogleSession, loading, error }: { language: Language; onLanguage: (x: Language) => void; onSubmit: (e: FormEvent<HTMLFormElement>, email: string, password: string) => void; onRegister: (e: FormEvent<HTMLFormElement>, details: Row) => void; onGoogleSession: (result: any) => void; loading: boolean; error: string }) {
  type AuthMode = 'login' | 'register' | 'forgot' | 'reset' | 'invitation';
  // Demo selectors and self-registration are development-only by default.
  // Production builds expose registration only when explicitly opted in at build time.
  const demoAccountsEnabled = import.meta.env.DEV;
  const publicRegistrationEnabled = import.meta.env.DEV || import.meta.env.VITE_FACTORYLINK_PUBLIC_REGISTRATION === 'true';
  const initialQuery = new URLSearchParams(window.location.search);
  const initialAction = initialQuery.get('action');
  const [mode, setMode] = useState<AuthMode>(initialAction === 'password-reset' ? 'reset' : initialAction === 'accept-invitation' ? 'invitation' : 'login');
  const [actionToken, setActionToken] = useState(initialQuery.get('token') || '');
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [orgName, setOrgName] = useState(''); const [orgCode, setOrgCode] = useState(''); const [orgType, setOrgType] = useState<'MANUFACTURER' | 'SUPPLIER'>('MANUFACTURER');
  const [ownerName, setOwnerName] = useState(''); const [registerEmail, setRegisterEmail] = useState(''); const [registerPassword, setRegisterPassword] = useState(''); const [confirmPassword, setConfirmPassword] = useState('');
  const [prefecture, setPrefecture] = useState(''); const [postalCode, setPostalCode] = useState('');
  const [forgotEmail, setForgotEmail] = useState(''); const [newPassword, setNewPassword] = useState(''); const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [localError, setLocalError] = useState(''); const [actionMessage, setActionMessage] = useState(''); const [actionBusy, setActionBusy] = useState(false);
  const [registerStep, setRegisterStep] = useState<'google' | 'details' | 'code' | 'password'>('details');
  const [registerCode, setRegisterCode] = useState(''); const [registrationTicket, setRegistrationTicket] = useState('');
  const [forgotStep, setForgotStep] = useState<'email' | 'code'>('email'); const [forgotCode, setForgotCode] = useState('');
  const [developmentCode, setDevelopmentCode] = useState(''); const [codeBusy, setCodeBusy] = useState(false);
  const [resendIn, setResendIn] = useState(0);
  const [googleBusy, setGoogleBusy] = useState(false); const [googleError, setGoogleError] = useState('');
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [googleSignup, setGoogleSignup] = useState<{ token: string; email: string; full_name: string } | null>(null);
  const tr = (key: MessageKey) => t(language, key);
  const registering = mode === 'register' && publicRegistrationEnabled;
  useEffect(() => {
    if (initialAction) window.history.replaceState({}, document.title, window.location.pathname);
  }, []);
  const demo = [
    { email: 'admin@factorylink.jp', role: language === 'ja' ? '組織管理者' : 'Factory administrator' },
    { email: 'production@factorylink.jp', role: language === 'ja' ? '生産管理者' : 'Production manager' },
    { email: 'warehouse@factorylink.jp', role: language === 'ja' ? '倉庫管理者' : 'Warehouse manager' },
    { email: 'quality@factorylink.jp', role: language === 'ja' ? '品質検査員' : 'Quality inspector' },
    { email: 'supplier@osaka-parts.jp', role: language === 'ja' ? '仕入先ユーザー' : 'Supplier user' },
  ];
  function submitRegistration(event: FormEvent<HTMLFormElement>) {
    if (registerPassword !== confirmPassword) { event.preventDefault(); setLocalError(language === 'ja' ? 'パスワードが一致しません。' : 'Passwords do not match.'); return; }
    if (!registrationTicket) { event.preventDefault(); setLocalError(language === 'ja' ? '先にメールアドレスの確認を完了してください。' : 'Verify your email address before creating the workspace.'); return; }
    setLocalError('');
    onRegister(event, { organization_name: orgName, organization_code: orgCode.trim().toUpperCase(), organization_type: orgType, owner_name: ownerName, email: registerEmail, password: registerPassword, email_verification_token: registrationTicket, language, postal_code: postalCode, prefecture });
  }
  async function requestRegistrationCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setCodeBusy(true); setLocalError(''); setActionMessage(''); setDevelopmentCode('');
    try {
      const result = await api<any>('/api/v1/auth/email-verification/request', '', { method: 'POST', body: JSON.stringify({ email: registerEmail, purpose: 'REGISTRATION' }) });
      setActionMessage(result.message || '');
      if (result.development_code) setDevelopmentCode(result.development_code);
      if (result.email_sent === false) setLocalError(result.message || '');
      setResendIn(60);
      setRegisterStep('code');
    } catch (err) { setLocalError(err instanceof Error ? err.message : tr('error')); }
    finally { setCodeBusy(false); }
  }
  async function verifyRegistrationCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setCodeBusy(true); setLocalError('');
    try {
      const result = await api<any>('/api/v1/auth/email-verification/verify', '', { method: 'POST', body: JSON.stringify({ email: registerEmail, purpose: 'REGISTRATION', code: registerCode }) });
      setRegistrationTicket(result.verification_token);
      setRegisterStep('password');
      setActionMessage('');
    } catch (err) { setLocalError(err instanceof Error ? err.message : tr('error')); }
    finally { setCodeBusy(false); }
  }
  async function requestResetCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setCodeBusy(true); setLocalError(''); setActionMessage(''); setDevelopmentCode('');
    try {
      const result = await api<any>('/api/v1/auth/email-verification/request', '', { method: 'POST', body: JSON.stringify({ email: forgotEmail, purpose: 'PASSWORD_RESET' }) });
      setActionMessage(result.message || '');
      if (result.development_code) setDevelopmentCode(result.development_code);
      setResendIn(60);
      setForgotStep('code');
    } catch (err) { setLocalError(err instanceof Error ? err.message : tr('error')); }
    finally { setCodeBusy(false); }
  }
  async function completeResetWithCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLocalError('');
    if (newPassword !== confirmNewPassword) { setLocalError(language === 'ja' ? 'パスワードが一致しません。' : 'Passwords do not match.'); return; }
    setCodeBusy(true);
    try {
      const verified = await api<any>('/api/v1/auth/email-verification/verify', '', { method: 'POST', body: JSON.stringify({ email: forgotEmail, purpose: 'PASSWORD_RESET', code: forgotCode }) });
      await api('/api/v1/auth/password-reset/confirm', '', { method: 'POST', body: JSON.stringify({ verification_token: verified.verification_token, password: newPassword }) });
      setMode('login'); setPassword(''); setForgotStep('email'); setForgotCode(''); setNewPassword(''); setConfirmNewPassword(''); setDevelopmentCode('');
      setActionMessage(language === 'ja' ? 'パスワードを更新しました。新しいパスワードでログインしてください。' : 'Password updated. Please sign in with your new password.');
    } catch (err) { setLocalError(err instanceof Error ? err.message : tr('error')); }
    finally { setCodeBusy(false); }
  }
  async function completeAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLocalError(''); setActionMessage('');
    if (newPassword !== confirmNewPassword) { setLocalError(language === 'ja' ? 'パスワードが一致しません。' : 'Passwords do not match.'); return; }
    setActionBusy(true);
    try {
      if (mode === 'invitation') {
        const result = await api<any>('/api/v1/users/invitations/accept', '', { method: 'POST', body: JSON.stringify({ token: actionToken, password: newPassword }) });
        sessionStorage.setItem(ACCESS, result.access_token); sessionStorage.setItem(REFRESH, result.refresh_token);
        window.dispatchEvent(new CustomEvent('factorylink:session', { detail: result }));
      } else {
        await api('/api/v1/auth/password-reset/confirm', '', { method: 'POST', body: JSON.stringify({ token: actionToken, password: newPassword }) });
        setMode('login'); setPassword('');
        setActionMessage(language === 'ja' ? 'パスワードを更新しました。新しいパスワードでログインしてください。' : 'Password updated. Please sign in with your new password.');
      }
    } catch (err) { setLocalError(err instanceof Error ? err.message : tr('error')); }
    finally { setActionBusy(false); }
  }
  function startGoogleSignIn() { window.location.assign('/api/v1/auth/google/start'); }
  async function finishGoogleRegistration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!googleSignup) { setLocalError(tr('error')); return; }
    setCodeBusy(true); setLocalError('');
    try {
      const result = await api<any>('/api/v1/auth/google/register', '', { method: 'POST', body: JSON.stringify({
        signup_token: googleSignup.token, organization_name: orgName,
        organization_code: orgCode.trim().toUpperCase(), organization_type: orgType,
        owner_name: ownerName, language, postal_code: postalCode, prefecture,
      }) });
      onGoogleSession(result);
    } catch (err) { setLocalError(err instanceof Error ? err.message : tr('registrationFailed')); }
    finally { setCodeBusy(false); }
  }
  async function resendVerificationCode(purpose: 'REGISTRATION' | 'PASSWORD_RESET') {
    const target = purpose === 'REGISTRATION' ? registerEmail : forgotEmail;
    setCodeBusy(true); setLocalError(''); setDevelopmentCode('');
    try {
      const result = await api<any>('/api/v1/auth/email-verification/request', '', { method: 'POST', body: JSON.stringify({ email: target, purpose }) });
      setActionMessage(result.message || ''); setResendIn(60);
      if (result.development_code) setDevelopmentCode(result.development_code);
      if (result.email_sent === false) setLocalError(result.message || '');
    } catch (err) { setLocalError(err instanceof Error ? err.message : tr('error')); }
    finally { setCodeBusy(false); }
  }
  useEffect(() => {
    let active = true;
    api<{ google: boolean }>('/api/v1/auth/providers', '')
      .then((result) => { if (active) setGoogleEnabled(Boolean(result.google)); })
      .catch(() => { /* the button simply stays hidden */ });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setTimeout(() => setResendIn((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [resendIn]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const handoff = params.get('google_code');
    const googleFailure = params.get('google_error');
    if (!handoff && !googleFailure) return;
    window.history.replaceState({}, document.title, window.location.pathname);
    if (googleFailure) {
      setGoogleError(googleFailure === 'access_denied'
        ? (language === 'ja' ? 'Google のサインインがキャンセルされました。' : 'Google sign-in was cancelled.')
        : googleFailure === 'account_inactive'
          ? (language === 'ja' ? 'このアカウントは無効です。管理者にお問い合わせください。' : 'This account is inactive. Contact your administrator.')
          : (language === 'ja' ? 'Google サインインを完了できませんでした。もう一度お試しください。' : 'Google sign-in could not be completed. Please try again.'));
      return;
    }
    setGoogleBusy(true);
    api<any>('/api/v1/auth/google/exchange', '', { method: 'POST', body: JSON.stringify({ code: handoff }) })
      .then((result) => {
        if (result.needs_registration) {
          setGoogleSignup({ token: result.signup_token, email: result.email, full_name: result.full_name });
          setOwnerName(result.full_name || ''); setRegisterEmail(result.email || '');
          setMode('register'); setRegisterStep('google'); setLocalError('');
        } else {
          onGoogleSession(result);
        }
      })
      .catch((err) => setGoogleError(err instanceof Error ? err.message : (language === 'ja' ? 'Google サインインに失敗しました。' : 'Google sign-in failed.')))
      .finally(() => setGoogleBusy(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const actionTitle = mode === 'forgot'
    ? (forgotStep === 'email' ? (language === 'ja' ? 'パスワードを再設定' : 'Reset your password') : (language === 'ja' ? '確認コードを入力' : 'Enter your code'))
    : mode === 'reset' ? (language === 'ja' ? '新しいパスワード' : 'Choose a new password')
    : mode === 'invitation' ? (language === 'ja' ? '招待を承認' : 'Accept your invitation')
    : registering ? (registerStep === 'google' ? (language === 'ja' ? 'ワークスペースを作成' : 'Finish your workspace') : registerStep === 'details' ? tr('registerOrganization') : registerStep === 'code' ? (language === 'ja' ? 'メールアドレスを確認' : 'Verify your email') : (language === 'ja' ? 'パスワードを設定' : 'Set your password')) : tr('loginTitle');
  const actionSubtitle = mode === 'forgot'
    ? (forgotStep === 'email'
      ? (language === 'ja' ? '登録メールアドレスに6桁の確認コードを送信します。' : 'We will email a six-digit verification code to your registered address.')
      : (language === 'ja' ? 'メールのコードを入力し、新しいパスワードを設定してください。' : 'Enter the code from your email and choose a new password.'))
    : mode === 'reset' ? (language === 'ja' ? '新しいパスワードを設定してください。' : 'Set a new password for your account.')
    : mode === 'invitation' ? (language === 'ja' ? '招待を完了するためにパスワードを設定してください。' : 'Set a password to activate your FactoryLink account.')
    : registering ? (registerStep === 'google'
      ? (language === 'ja' ? 'Google のメールアドレスは確認済みです。ワークスペース名を入力して完了してください。' : 'Your Google email is verified. Name your workspace to finish signing up.')
      : registerStep === 'details'
      ? (language === 'ja' ? '会社のワークスペースを作成します。最初にメールアドレスを確認します。' : 'Create your company workspace. We verify your email address first.')
      : registerStep === 'code'
        ? (language === 'ja' ? `${registerEmail} に6桁のコードを送信しました。` : `We sent a six-digit code to ${registerEmail}.`)
        : (language === 'ja' ? 'メールアドレスを確認しました。ログインに使うパスワードを設定してください。' : 'Email verified. Choose the password you will sign in with.'))
      : tr('loginSubtitle');
  return <div className="login-screen"><div className="login-art"><div className="login-art-grid" /><div className="login-brand"><div className="brand-mark brand-mark-light"><Factory size={22} /></div><span>FactoryLink</span></div><div className="login-art-copy"><span className="eyebrow">MANUFACTURING INTELLIGENCE · JAPAN</span><h1>{language === 'ja' ? '製造現場のすべてを、ひとつにつなぐ。' : 'Connect every part of your manufacturing operation.'}</h1><p>{language === 'ja' ? '生産、在庫、品質、設備、仕入先をつなぐ統合オペレーションプラットフォーム。' : 'A connected operations workspace for production, inventory, quality, maintenance and supplier collaboration.'}</p><div className="art-stats"><div><strong>01</strong><span>Production</span></div><div><strong>02</strong><span>Quality</span></div><div><strong>03</strong><span>Traceability</span></div></div></div><div className="login-art-footer"><span>FactoryLink</span><span>Monozukuri · Kaizen · Connected</span></div></div><div className="login-panel"><div className="login-language"><Languages size={16} /><select value={language} onChange={(e) => onLanguage(e.target.value as Language)}><option value="ja">日本語</option><option value="en">English</option></select></div><div className="login-form-wrap"><div className="login-symbol"><Factory size={24} /></div><h2>{actionTitle}</h2><p>{actionSubtitle}</p>
  {registering ? (registerStep === 'google' ? <form onSubmit={finishGoogleRegistration} className="login-form">
    <button type="button" className="login-back" onClick={() => { setRegisterStep('details'); setMode('login'); setGoogleSignup(null); setLocalError(''); }}><ChevronLeft size={16} />{language === 'ja' ? 'ログインに戻る' : 'Back to sign in'}</button>
    <p className="login-note">{language === 'ja' ? `${googleSignup?.email || registerEmail} で Google にサインインしました。` : `Signed in as ${googleSignup?.email || registerEmail}.`}</p>
    <label>{tr('organizationName')}<input value={orgName} onChange={(e) => setOrgName(e.target.value)} required minLength={2} maxLength={180} /></label>
    <label>{tr('organizationCode')}<input value={orgCode} onChange={(e) => setOrgCode(e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, '-'))} required minLength={3} maxLength={40} pattern="[A-Z0-9]+(-[A-Z0-9]+)*" /></label>
    <label>{tr('organizationType')}<select value={orgType} onChange={(e) => setOrgType(e.target.value as 'MANUFACTURER' | 'SUPPLIER')}><option value="MANUFACTURER">{tr('manufacturer')}</option><option value="SUPPLIER">{tr('supplier')}</option></select></label>
    <label>{tr('ownerName')}<input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} required minLength={2} /></label>
    <label>{tr('prefecture')}<input value={prefecture} onChange={(e) => setPrefecture(e.target.value)} /></label>
    <label>{language === 'ja' ? '郵便番号' : 'Postal code'}<input value={postalCode} onChange={(e) => setPostalCode(e.target.value)} placeholder="460-0008" /></label>
    {(localError || googleError) && <div className="login-error">{localError || googleError}</div>}
    <button className="primary-button login-submit" disabled={codeBusy}>{codeBusy ? tr('loading') : (language === 'ja' ? 'ワークスペースを作成' : 'Create workspace')}<ChevronRight size={17} /></button>
  </form> : registerStep === 'details' ? <form onSubmit={requestRegistrationCode} className="login-form">
    <label>{tr('organizationName')}<input value={orgName} onChange={(e) => setOrgName(e.target.value)} required minLength={2} maxLength={180} /></label>
    <label>{tr('organizationCode')}<input value={orgCode} onChange={(e) => setOrgCode(e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, '-'))} required minLength={3} maxLength={40} pattern="[A-Z0-9]+(-[A-Z0-9]+)*" /></label>
    <label>{tr('organizationType')}<select value={orgType} onChange={(e) => setOrgType(e.target.value as 'MANUFACTURER' | 'SUPPLIER')}><option value="MANUFACTURER">{tr('manufacturer')}</option><option value="SUPPLIER">{tr('supplier')}</option></select></label>
    <label>{tr('ownerName')}<input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} required minLength={2} /></label>
    <label>{tr('email')}<input type="email" value={registerEmail} onChange={(e) => setRegisterEmail(e.target.value)} required autoComplete="email" /></label>
    <label>{tr('prefecture')}<input value={prefecture} onChange={(e) => setPrefecture(e.target.value)} /></label>
    <label>{language === 'ja' ? '郵便番号' : 'Postal code'}<input value={postalCode} onChange={(e) => setPostalCode(e.target.value)} placeholder="460-0008" /></label>
    {(localError || error) && <div className="login-error">{localError || error}</div>}
    <button className="primary-button login-submit" disabled={codeBusy}>{codeBusy ? tr('loading') : (language === 'ja' ? '確認コードを送信' : 'Send verification code')}<ChevronRight size={17} /></button>
    {googleEnabled && <><div className="login-divider"><span>{language === 'ja' ? 'または' : 'or'}</span></div>
    <button type="button" className="google-button" disabled={googleBusy} onClick={startGoogleSignIn}><GoogleGlyph />{language === 'ja' ? 'Google で登録' : 'Sign up with Google'}</button></>}
    <button type="button" className="text-link login-switch" onClick={() => { setMode('login'); setLocalError(''); }}>{tr('haveAccount')}</button>
  </form> : registerStep === 'code' ? <form onSubmit={verifyRegistrationCode} className="login-form">
    <button type="button" className="login-back" onClick={() => { setRegisterStep('details'); setRegisterCode(''); setLocalError(''); setDevelopmentCode(''); setResendIn(0); }}><ChevronLeft size={16} />{language === 'ja' ? '戻る' : 'Back'}</button>
    {developmentCode && <div className="login-success">{language === 'ja' ? '開発用コード: ' : 'Development code: '}<strong>{developmentCode}</strong></div>}
    <label>{language === 'ja' ? '6桁の確認コード' : 'Six-digit code'}<input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={registerCode} onChange={(e) => setRegisterCode(e.target.value.replace(/\D/g, '').slice(0, 6))} required autoFocus autoComplete="one-time-code" /></label>
    {localError && <div className="login-error">{localError}</div>}
    {actionMessage && <div className="login-success">{actionMessage}</div>}
    <button className="primary-button login-submit" disabled={codeBusy || registerCode.length !== 6}>{codeBusy ? tr('loading') : (language === 'ja' ? 'コードを確認' : 'Verify code')}<ChevronRight size={17} /></button>
    <button type="button" className="text-link login-resend" disabled={codeBusy || resendIn > 0} onClick={() => resendVerificationCode('REGISTRATION')}>{resendIn > 0 ? `${language === 'ja' ? 'コードを再送信' : 'Resend code'} (${resendIn}s)` : (language === 'ja' ? 'コードが届きませんか？再送信' : "Didn't get the code? Resend")}</button>
  </form> : <form onSubmit={submitRegistration} className="login-form">
    <label>{tr('password')}<input type="password" value={registerPassword} onChange={(e) => setRegisterPassword(e.target.value)} required minLength={12} autoComplete="new-password" /></label>
    <label>{language === 'ja' ? 'パスワード（確認）' : 'Confirm password'}<input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required minLength={12} autoComplete="new-password" /></label>
    {localError && <div className="login-error">{localError}</div>}
    <button className="primary-button login-submit" disabled={loading}>{loading ? tr('loading') : tr('createOrganization')}<ChevronRight size={17} /></button>
    <button type="button" className="text-link login-switch" onClick={() => setRegisterStep('code')}>{language === 'ja' ? '戻る' : 'Back'}</button>
  </form>) : mode === 'forgot' ? (forgotStep === 'email' ? <form onSubmit={requestResetCode} className="login-form">
    <button type="button" className="login-back" onClick={() => { setMode('login'); setLocalError(''); setActionMessage(''); setDevelopmentCode(''); }}><ChevronLeft size={16} />{language === 'ja' ? 'ログインに戻る' : 'Back to sign in'}</button>
    <label>{tr('email')}<input type="email" value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)} required autoComplete="email" /></label>
    {(localError || error) && <div className="login-error">{localError || error}</div>}{actionMessage && <div className="login-success">{actionMessage}</div>}
    <button className="primary-button login-submit" disabled={codeBusy}>{codeBusy ? tr('loading') : (language === 'ja' ? '確認コードを送信' : 'Send verification code')}<ChevronRight size={17} /></button>
  </form> : <form onSubmit={completeResetWithCode} className="login-form">
    <button type="button" className="login-back" onClick={() => { setForgotStep('email'); setForgotCode(''); setLocalError(''); setDevelopmentCode(''); setResendIn(0); }}><ChevronLeft size={16} />{language === 'ja' ? '戻る' : 'Back'}</button>
    {developmentCode && <div className="login-success">{language === 'ja' ? '開発用コード: ' : 'Development code: '}<strong>{developmentCode}</strong></div>}
    <label>{language === 'ja' ? '6桁の確認コード' : 'Six-digit code'}<input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={forgotCode} onChange={(e) => setForgotCode(e.target.value.replace(/\D/g, '').slice(0, 6))} required autoFocus autoComplete="one-time-code" /></label>
    <label>{tr('password')}<input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required minLength={12} maxLength={128} autoComplete="new-password" /></label>
    <label>{language === 'ja' ? 'パスワード（確認）' : 'Confirm password'}<input type="password" value={confirmNewPassword} onChange={(e) => setConfirmNewPassword(e.target.value)} required minLength={12} maxLength={128} autoComplete="new-password" /></label>
    {localError && <div className="login-error">{localError}</div>}
    {actionMessage && <div className="login-success">{actionMessage}</div>}
    <button className="primary-button login-submit" disabled={codeBusy || forgotCode.length !== 6 || newPassword.length < 12}>{codeBusy ? tr('loading') : (language === 'ja' ? 'パスワードを更新' : 'Update password')}<ChevronRight size={17} /></button>
    <button type="button" className="text-link login-resend" disabled={codeBusy || resendIn > 0} onClick={() => resendVerificationCode('PASSWORD_RESET')}>{resendIn > 0 ? `${language === 'ja' ? 'コードを再送信' : 'Resend code'} (${resendIn}s)` : (language === 'ja' ? 'コードが届きませんか？再送信' : "Didn't get the code? Resend")}</button>
  </form>) : (mode === 'reset' || mode === 'invitation') ? <form onSubmit={completeAction} className="login-form">
    <label>{tr('password')}<input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required minLength={12} maxLength={128} autoComplete="new-password" /></label>
    <label>{language === 'ja' ? 'パスワード（確認）' : 'Confirm password'}<input type="password" value={confirmNewPassword} onChange={(e) => setConfirmNewPassword(e.target.value)} required minLength={12} maxLength={128} autoComplete="new-password" /></label>
    {!actionToken && <div className="login-error">{language === 'ja' ? 'リンクが無効です。もう一度リンクを取得してください。' : 'The link is missing. Please request a new link.'}</div>}
    {localError && <div className="login-error">{localError}</div>}
    <button className="primary-button login-submit" disabled={actionBusy || !actionToken}>{actionBusy ? tr('loading') : (mode === 'invitation' ? (language === 'ja' ? '招待を承認' : 'Activate account') : (language === 'ja' ? 'パスワードを更新' : 'Update password'))}<ChevronRight size={17} /></button>
    {mode === 'reset' && <button type="button" className="text-link login-switch" onClick={() => setMode('login')}>{language === 'ja' ? 'ログインに戻る' : 'Back to sign in'}</button>}
  </form> : <><form onSubmit={(e) => onSubmit(e, email, password)} className="login-form"><label>{tr('email')}<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" /></label><label>{tr('password')}<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" /></label>{(localError || error) && <div className="login-error">{localError || error}</div>}{actionMessage && <div className="login-success">{actionMessage}</div>}<button className="primary-button login-submit" disabled={loading}>{loading ? tr('loading') : tr('signIn')}<ChevronRight size={17} /></button></form>{googleError && <div className="login-error">{googleError}</div>}{googleEnabled && <><div className="login-divider"><span>{language === 'ja' ? 'または' : 'or'}</span></div><button type="button" className="google-button" disabled={googleBusy} onClick={startGoogleSignIn}><GoogleGlyph />{googleBusy ? (language === 'ja' ? 'Google と通信中…' : 'Connecting to Google…') : (language === 'ja' ? 'Google で続ける' : 'Continue with Google')}</button></>}<div className="login-links"><button type="button" className="text-link" onClick={() => { setMode('forgot'); setForgotEmail(email); setLocalError(''); setActionMessage(''); }}>{language === 'ja' ? 'パスワードをお忘れですか？' : 'Forgot password?'}</button>{publicRegistrationEnabled && <button type="button" className="text-link login-switch" onClick={() => { setMode('register'); setLocalError(''); }}>{tr('needAccount')}</button>}</div>{demoAccountsEnabled && <><div className="demo-title"><span />{tr('demoAccounts')}<span /></div><div className="demo-list">{demo.map((item) => <button key={item.email} onClick={() => setEmail(item.email)} className={email === item.email ? 'demo-account active' : 'demo-account'}><span className="demo-avatar">{item.email[0].toUpperCase()}</span><span>{item.role}</span><ArrowUpRight size={13} /></button>)}</div></>}</>}
  </div><div className="login-copyright">© 2026 FactoryLink · {tr('poweredBy')}</div></div></div>;
}
function PageHeading({ title, subtitle, action, icon: Icon = Factory }: { title: string; subtitle: string; action?: React.ReactNode; icon?: any }) {
  return <div className="page-heading"><div className="page-title-wrap"><div className="page-icon"><Icon size={19} /></div><div><h1>{title}</h1><p>{subtitle}</p></div></div>{action}</div>;
}

function Dashboard({ data, language, onNavigate }: { data: any; language: Language; onNavigate: (page: Page) => void }) {
  const tr = (key: MessageKey) => t(language, key); const k = data?.kpis || {};
  const cards = [
    { label: tr('productionOrders'), value: k.production_orders ?? '—', icon: Factory, tone: 'blue', note: `${k.completed_orders ?? 0} ${tr('completedOrders').toLowerCase()}` },
    { label: tr('productionProgress'), value: `${k.production_progress ?? 0}%`, icon: Gauge, tone: 'green', note: tr('overview') },
    { label: tr('defectRate'), value: `${k.defect_rate ?? 0}%`, icon: ShieldCheck, tone: 'amber', note: language === 'ja' ? '検査記録ベース' : 'Based on inspection records' },
    { label: tr('inventoryValue'), value: money(k.inventory_value ?? 0, language), icon: Package, tone: 'violet', note: `${k.low_stock_count ?? 0} ${tr('lowStock').toLowerCase()}` },
  ];
  const orderStatus = data?.production_status || []; const max = Math.max(1, ...orderStatus.map((x: any) => x.count));
  return <>
    <PageHeading title={tr('dashboard')} subtitle={`${tr('welcome')}, ${language === 'ja' ? '今日のオペレーション状況をご確認ください。' : 'here is your factory operations at a glance.'}`} action={<span className="date-pill"><CalendarClock size={15} />{dateText(new Date().toISOString(), language)}</span>} />
    <div className="kpi-grid">{cards.map((card, index) => { const Icon = card.icon; return <div className={`kpi-card tone-${card.tone}`} key={index}><div className="kpi-top"><span>{card.label}</span><div className="kpi-icon"><Icon size={18} /></div></div><div className="kpi-value">{card.value}</div><div className="kpi-note"><span className="kpi-note-dot" />{card.note}</div></div>; })}</div>
    <div className="dashboard-grid"><section className="panel production-chart-panel"><div className="panel-heading"><div><h3>{tr('productionOutput')}</h3><p>{language === 'ja' ? '現在の生産オーダーの内訳' : 'A live view of current production order statuses'}</p></div><button className="subtle-button" onClick={() => onNavigate('production')}>{tr('production')}<ArrowUpRight size={14} /></button></div><div className="status-bars">{orderStatus.map((item: any) => <div key={item.status} className="status-bar-row"><div className="bar-label"><span>{humanStatus(language, item.status)}</span><strong>{item.count}</strong></div><div className="bar-track"><div className={`bar-fill fill-${item.status.toLowerCase()}`} style={{ width: `${item.count / max * 100}%` }} /></div></div>)}</div><div className="chart-footnote"><span><span className="legend-dot legend-blue" />{tr('productionOrders')}</span><span>{language === 'ja' ? '実データ' : 'Live database values'}</span></div></section>
      <section className="panel focus-panel"><div className="panel-heading"><div><h3>{tr('overview')}</h3><p>{language === 'ja' ? '本日の注目指標' : 'Operational signals to pay attention to'}</p></div><div className="focus-indicator"><Activity size={15} /></div></div><div className="focus-list"><button onClick={() => onNavigate('production')}><div className="focus-icon focus-blue"><Factory size={17} /></div><div><strong>{k.delayed_orders ?? 0} {tr('delayedOrders')}</strong><span>{language === 'ja' ? '納期超過の生産オーダー' : 'Production orders past due date'}</span></div><ChevronRight size={16} /></button><button onClick={() => onNavigate('inventory')}><div className="focus-icon focus-amber"><AlertTriangle size={17} /></div><div><strong>{k.low_stock_count ?? 0} {tr('lowStock')}</strong><span>{language === 'ja' ? '補充が必要な材料ロット' : 'Material batches to review'}</span></div><ChevronRight size={16} /></button><button onClick={() => onNavigate('purchaseOrders')}><div className="focus-icon focus-green"><Truck size={17} /></div><div><strong>{k.open_purchase_orders ?? 0} {tr('openPO')}</strong><span>{language === 'ja' ? '確認または納品待ち' : 'Awaiting confirmation or delivery'}</span></div><ChevronRight size={16} /></button><button onClick={() => onNavigate('maintenance')}><div className="focus-icon focus-violet"><Wrench size={17} /></div><div><strong>{k.equipment_due ?? 0} {tr('equipmentDue')}</strong><span>{language === 'ja' ? '保全スケジュールを確認' : 'Equipment requiring attention'}</span></div><ChevronRight size={16} /></button></div></section>
    </div>
    <div className="dashboard-bottom-grid"><section className="panel"><div className="panel-heading"><div><h3>{tr('productionOrders')}</h3><p>{language === 'ja' ? '最近の生産オーダー' : 'Latest production orders'}</p></div><button className="icon-button" onClick={() => onNavigate('production')}><ArrowUpRight size={17} /></button></div><div className="compact-table-wrap"><table className="data-table"><thead><tr><th>{tr('orderNumber')}</th><th>{tr('product')}</th><th>{tr('status')}</th><th>{tr('dueDate')}</th></tr></thead><tbody>{(data?.production_orders || []).slice(0, 5).map((r: Row) => <tr key={r.id}><td className="mono strong">{r.order_number}</td><td>{r.product_name}</td><td><span className={statusClass(r.status)}>{humanStatus(language, r.status)}</span></td><td>{dateText(r.due_date, language)}</td></tr>)}{(!data?.production_orders?.length) && <tr><td colSpan={4} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div></section><section className="panel activity-panel"><div className="panel-heading"><div><h3>{tr('recentActivity')}</h3><p>{language === 'ja' ? '監査ログに記録された最近の操作' : 'Latest recorded operations'}</p></div><button className="icon-button" onClick={() => onNavigate('audit')}><ArrowUpRight size={17} /></button></div><div className="activity-list">{(data?.recent_activity || []).map((item: Row, i: number) => <div className="activity-item" key={`${item.entity_id}-${i}`}><span className="activity-marker" /><div><strong>{item.action.replaceAll('_', ' ')} · {item.entity_type}</strong><span>{item.entity_id} · {dateText(item.created_at, language)}</span></div></div>)}{(!data?.recent_activity?.length) && <div className="empty-state compact-empty"><Activity size={23} /><span>{tr('noActivity')}</span></div>}</div></section></div>
  </>;
}

function SupplierDashboard({ data, language, onNavigate, onStatus }: { data: Row[]; language: Language; onNavigate: (page: Page) => void; onStatus: (p: string, s: string, note?: string) => void }) {
  const tr = (key: MessageKey) => t(language, key);
  const open = data.filter((x) => !['DELIVERED', 'CANCELLED'].includes(x.status)).length;
  return <><PageHeading title={tr('supplierPortal')} subtitle={tr('myPurchaseOrders')} icon={Truck} action={<span className="date-pill"><Globe2 size={15} />Asia/Tokyo</span>} /><div className="kpi-grid supplier-kpis"><div className="kpi-card tone-blue"><div className="kpi-top"><span>{tr('purchaseOrders')}</span><div className="kpi-icon"><ClipboardList size={18} /></div></div><div className="kpi-value">{data.length}</div><div className="kpi-note">{tr('overview')}</div></div><div className="kpi-card tone-green"><div className="kpi-top"><span>{tr('openPO')}</span><div className="kpi-icon"><Clock3 size={18} /></div></div><div className="kpi-value">{open}</div><div className="kpi-note">{tr('action')}</div></div><div className="kpi-card tone-violet"><div className="kpi-top"><span>{tr('delivered')}</span><div className="kpi-icon"><PackageCheck size={18} /></div></div><div className="kpi-value">{data.filter((x) => x.status === 'DELIVERED').length}</div><div className="kpi-note">{tr('status')}</div></div><div className="kpi-card tone-amber"><div className="kpi-top"><span>{tr('documents')}</span><div className="kpi-icon"><FileText size={18} /></div></div><div className="kpi-value"><ArrowUpRight size={25} /></div><div className="kpi-note">{language === 'ja' ? '発注書に関連付けて提出' : 'Upload against a shared PO'}</div></div></div><section className="panel"><div className="panel-heading"><div><h3>{tr('myPurchaseOrders')}</h3><p>{language === 'ja' ? 'ステータスを更新して工場と共有' : 'Update delivery status to keep your factory partner informed'}</p></div><button className="subtle-button" onClick={() => onNavigate('purchaseOrders')}>{tr('purchaseOrders')}<ArrowUpRight size={14} /></button></div><PurchaseOrdersTable rows={data} language={language} isSupplier canUpdate onStatus={onStatus} /></section></>;
}

function EmptyPage({ icon: Icon, title, description }: { icon: any; title: string; description: string }) { return <div className="empty-state page-empty"><div className="empty-icon"><Icon size={24} /></div><strong>{title}</strong><span>{description}</span></div>; }
function SearchBar({ value, onChange, language }: { value: string; onChange: (x: string) => void; language: Language }) { return <div className="table-search"><Search size={16} /><input value={value} onChange={(e) => onChange(e.target.value)} placeholder={language === 'ja' ? '検索...' : 'Search records…'} /></div>; }
function TableFrame({ title, subtitle, action, search, children }: { title: string; subtitle: string; action?: React.ReactNode; search?: React.ReactNode; children: React.ReactNode }) { return <section className="panel table-panel"><div className="table-panel-top"><div><h3>{title}</h3><p>{subtitle}</p></div><div className="table-toolbar">{search}{action}</div></div>{children}</section>; }

function ProductionPage({ rows, language, onCreate, canCreate, canUpdate, canEdit, onEdit, onDelete, onStatus, onProgress, searchTerm, setSearchTerm }: { rows: Row[]; language: Language; onCreate: () => void; canCreate: boolean; canUpdate: boolean; canEdit: boolean; onEdit: (row: Row) => void; onDelete: (row: Row) => void; onStatus: (p: string, s: string) => void; onProgress: (id: number, completed: number, rejected: number) => void; searchTerm: string; setSearchTerm: (x: string) => void }) {
  const tr = (key: MessageKey) => t(language, key);
  const filtered = rows.filter((r) => `${r.order_number} ${r.product_name} ${r.status}`.toLowerCase().includes(searchTerm.toLowerCase()));
  const [drafts, setDrafts] = useState<Record<number, { completed: string; rejected: string }>>({});
  const transitions: Record<string, string[]> = { DRAFT: ['PLANNED', 'CANCELLED'], PLANNED: ['READY', 'CANCELLED'], READY: ['IN_PROGRESS', 'CANCELLED'], IN_PROGRESS: ['PAUSED', 'COMPLETED', 'CANCELLED'], PAUSED: ['IN_PROGRESS', 'COMPLETED', 'CANCELLED'] };
  const setDraft = (id: number, key: 'completed' | 'rejected', value: string) => setDrafts((current) => ({ ...current, [id]: { completed: current[id]?.completed ?? String(rows.find((x) => x.id === id)?.completed_quantity ?? 0), rejected: current[id]?.rejected ?? String(rows.find((x) => x.id === id)?.rejected_quantity ?? 0), [key]: value } }));
  return <><PageHeading title={tr('production')} subtitle={language === 'ja' ? '生産オーダー、進捗、材料の割当を管理します。' : 'Plan orders, allocate materials and track shop-floor progress.'} icon={Factory} action={canCreate ? <button className="primary-button" onClick={onCreate}><Plus size={17} />{tr('newProduction')}</button> : undefined} /><div className="mini-stats"><span><Factory size={15} />{rows.length} {tr('productionOrders')}</span><span><CheckCircle2 size={15} />{rows.filter((r) => r.status === 'COMPLETED').length} {tr('completedOrders')}</span><span><AlertTriangle size={15} />{rows.filter((r) => r.due_date && new Date(`${r.due_date}T23:59:59`) < new Date() && !['COMPLETED', 'CANCELLED'].includes(r.status)).length} {tr('delayedOrders')}</span></div><TableFrame title={tr('productionOrders')} subtitle={language === 'ja' ? '生産計画と現場進捗' : 'Production schedule and shop-floor progress'} action={canCreate ? <button className="subtle-button" onClick={onCreate}><Plus size={14} />{tr('createNew')}</button> : undefined} search={<SearchBar value={searchTerm} onChange={setSearchTerm} language={language} />}><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('orderNumber')}</th><th>{tr('product')}</th><th>{tr('quantity')}</th><th>{language === 'ja' ? '完了数' : 'Completed'}</th><th>{language === 'ja' ? '不良数' : 'Rejected'}</th><th>{tr('status')}</th><th>{tr('dueDate')}</th><th>{tr('action')}</th></tr></thead><tbody>{filtered.map((r) => {
    const draft = drafts[r.id] || { completed: String(r.completed_quantity), rejected: String(r.rejected_quantity) };
    const editable = canUpdate && ['IN_PROGRESS', 'PAUSED'].includes(r.status);
    return <tr key={r.id}><td className="mono strong">{r.order_number}</td><td><strong>{r.product_name}</strong><small>{r.material_name}</small></td><td>{r.quantity.toLocaleString()}</td><td>{editable ? <input className="inline-number" aria-label={language === 'ja' ? '完了数' : 'Completed quantity'} type="number" min="0" max={r.quantity} value={draft.completed} onChange={(e) => setDraft(r.id, 'completed', e.target.value)} /> : <>{r.completed_quantity.toLocaleString()} <span className="muted">/ {r.quantity.toLocaleString()}</span></>}</td><td>{editable ? <input className="inline-number" aria-label={language === 'ja' ? '不良数' : 'Rejected quantity'} type="number" min="0" max={r.quantity} value={draft.rejected} onChange={(e) => setDraft(r.id, 'rejected', e.target.value)} /> : r.rejected_quantity.toLocaleString()}</td><td><span className={statusClass(r.status)}>{humanStatus(language, r.status)}</span></td><td>{dateText(r.due_date, language)}</td><td><div className="inline-actions">{canEdit && ['DRAFT', 'PLANNED'].includes(r.status) && <button className="row-action" onClick={() => onEdit(r)}>{language === 'ja' ? '編集' : 'Edit'}</button>}{canEdit && ['DRAFT', 'PLANNED', 'CANCELLED'].includes(r.status) && <button className="row-action danger" onClick={() => onDelete(r)}>{language === 'ja' ? '削除' : 'Delete'}</button>}{editable && <button className="row-action" onClick={() => onProgress(r.id, Number(draft.completed), Number(draft.rejected))}>{language === 'ja' ? '進捗保存' : 'Save output'}</button>}{canUpdate && (transitions[r.status] || []).filter((next) => next !== 'CANCELLED' || canCreate).map((next) => <button key={next} className="row-action" onClick={() => onStatus(`/api/v1/production/orders/${r.id}/status`, next)}>{next === 'COMPLETED' ? (language === 'ja' ? '完了' : 'Complete') : next === 'CANCELLED' ? (language === 'ja' ? '取消' : 'Cancel') : next === 'PAUSED' ? (language === 'ja' ? '一時停止' : 'Pause') : next === 'IN_PROGRESS' ? (language === 'ja' ? '再開' : 'Resume') : tr('advance')} <ChevronRight size={13} /></button>)}</div></td></tr>;
  })}{!filtered.length && <tr><td colSpan={8} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div></TableFrame></>;
}

function InventoryPage({ rows, language, onCreate, onAdjust, canReceive, onTrace }: { rows: Row[]; language: Language; onCreate: () => void; onAdjust: () => void; canReceive: boolean; onTrace: (lot: string) => void }) {
  const tr = (key: MessageKey) => t(language, key);
  return <><PageHeading title={tr('inventory')} subtitle={language === 'ja' ? 'ロット単位の在庫、入庫、引当を管理します。' : 'Manage receipts, lot-level stock and reserved quantities.'} icon={Boxes} action={canReceive ? <div className="inline-actions"><button className="subtle-button" onClick={onAdjust}>{language === 'ja' ? '在庫調整' : 'Adjust stock'}</button><button className="primary-button" onClick={onCreate}><Plus size={17} />{tr('newReceipt')}</button></div> : undefined} /><div className="mini-stats"><span><Boxes size={15} />{rows.length} {language === 'ja' ? 'ロット' : 'batches'}</span><span><Package size={15} />{rows.reduce((sum, x) => sum + x.quantity_on_hand, 0).toLocaleString()} {language === 'ja' ? '総数量' : 'total on hand'}</span><span><AlertTriangle size={15} />{rows.filter((x) => x.status === 'HOLD').length} {tr('hold')}</span></div><TableFrame title={language === 'ja' ? '材料ロット' : 'Material batches'} subtitle={tr('stockLedger')} action={canReceive ? <button className="subtle-button" onClick={onCreate}><Plus size={14} />{tr('receive')}</button> : undefined}><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('material')}</th><th>{tr('lotNumber')}</th><th>{tr('quantity')}</th><th>{language === 'ja' ? '引当済' : 'Reserved'}</th><th>{language === 'ja' ? '利用可能' : 'Available'}</th><th>{tr('price')}</th><th>{tr('status')}</th><th /></tr></thead><tbody>{rows.map((r) => <tr key={r.id}><td><strong>{r.material_name}</strong><small>{r.unit}</small></td><td className="mono">{r.lot_number}</td><td>{r.quantity_on_hand.toLocaleString()} {r.unit}</td><td>{r.quantity_reserved.toLocaleString()}</td><td className="strong">{(r.quantity_on_hand - r.quantity_reserved).toLocaleString()}</td><td>{money(r.unit_cost, language)}</td><td><span className={statusClass(r.status)}>{humanStatus(language, r.status)}</span></td><td><button className="icon-button table-icon-action" onClick={() => onTrace(r.lot_number)} title={tr('traceability')}><ArrowLeftRight size={16} /></button></td></tr>)}{!rows.length && <tr><td colSpan={8} className="empty-cell">{tr('noStock')}</td></tr>}</tbody></table></div></TableFrame></>;
}

function SuppliersPage({ rows, language, onCreate, canCreate, canManage, onEdit, onDelete }: { rows: Row[]; language: Language; onCreate: () => void; canCreate: boolean; canManage: boolean; onEdit: (row: Row) => void; onDelete: (row: Row) => void }) {
  const tr = (key: MessageKey) => t(language, key);
  return <><PageHeading title={tr('suppliers')} subtitle={language === 'ja' ? '取引先の連絡先と登録状態を管理します。' : 'Maintain supplier contacts and collaboration status.'} icon={Truck} action={canCreate ? <button className="primary-button" onClick={onCreate}><Plus size={17} />{tr('newSupplier')}</button> : undefined} /><TableFrame title={tr('suppliers')} subtitle={`${rows.length} ${tr('records')}`} action={canCreate ? <button className="subtle-button" onClick={onCreate}><Plus size={14} />{tr('add')}</button> : undefined}><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('code')}</th><th>{tr('name')}</th><th>{tr('contact')}</th><th>{tr('email')}</th><th>{tr('phone')}</th><th>{tr('prefecture')}</th><th>{tr('status')}</th><th>{tr('action')}</th></tr></thead><tbody>{rows.map((r) => <tr key={r.id}><td className="mono strong">{r.code}</td><td><strong>{r.name}</strong></td><td>{r.contact_name || '—'}</td><td>{r.email || '—'}</td><td>{r.phone || '—'}</td><td>{r.prefecture || '—'}</td><td><span className={statusClass(r.status)}>{humanStatus(language, r.status)}</span></td><td><div className="inline-actions">{canManage && <><button className="row-action" onClick={() => onEdit(r)}>{tr('edit')}</button><button className="row-action danger" onClick={() => onDelete(r)}>{tr('delete')}</button></>}</div></td></tr>)}{!rows.length && <tr><td colSpan={8} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div></TableFrame></>;
}

function PurchaseOrdersPage({ rows, language, onCreate, canCreate, canUpdate, canManage, onEdit, onDelete, onStatus, isSupplier }: { rows: Row[]; language: Language; onCreate: () => void; canCreate: boolean; canUpdate: boolean; canManage: boolean; onEdit: (row: Row) => void; onDelete: (row: Row) => void; onStatus: (p: string, s: string, note?: string) => void; isSupplier: boolean }) {
  const tr = (key: MessageKey) => t(language, key);
  return <><PageHeading title={tr('purchaseOrders')} subtitle={isSupplier ? tr('myPurchaseOrders') : (language === 'ja' ? '発注、仕入先確認、分納状況を管理します。' : 'Manage supplier commitments, confirmations and deliveries.')} icon={ClipboardList} action={canCreate ? <button className="primary-button" onClick={onCreate}><Plus size={17} />{tr('newPO')}</button> : undefined} /><div className="mini-stats"><span><ClipboardList size={15} />{rows.length} {tr('purchaseOrders')}</span><span><Clock3 size={15} />{rows.filter((x) => !['DELIVERED', 'CANCELLED'].includes(x.status)).length} {tr('openPO')}</span></div><section className="panel table-panel"><div className="table-panel-top"><div><h3>{tr('orderDetails')}</h3><p>{language === 'ja' ? '発注書ステータスと納期' : 'Purchase order status and delivery dates'}</p></div></div><PurchaseOrdersTable rows={rows} language={language} isSupplier={isSupplier} canUpdate={canUpdate} canManage={canManage} onEdit={onEdit} onDelete={onDelete} onStatus={onStatus} /></section></>;
}

function PurchaseOrdersTable({ rows, language, isSupplier, canUpdate, canManage = false, onEdit, onDelete, onStatus }: { rows: Row[]; language: Language; isSupplier: boolean; canUpdate: boolean; canManage?: boolean; onEdit?: (row: Row) => void; onDelete?: (row: Row) => void; onStatus: (p: string, s: string, note?: string) => void }) {
  const tr = (key: MessageKey) => t(language, key);
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('orderNumber')}</th><th>{tr('item')}</th><th>{tr('quantity')}</th><th>{tr('price')}</th><th>{tr('status')}</th><th>{tr('dueDate')}</th><th>{tr('action')}</th></tr></thead><tbody>{rows.map((r) => {
    const next = isSupplier ? (r.status === 'SUBMITTED' ? 'CONFIRMED' : r.status === 'CONFIRMED' || r.status === 'PARTIALLY_DELIVERED' ? 'IN_TRANSIT' : '') : (r.status === 'DRAFT' ? 'SUBMITTED' : r.status === 'SUBMITTED' ? 'CONFIRMED' : '');
    return <tr key={r.id}><td className="mono strong">{r.po_number}</td><td><strong>{r.item_name}</strong></td><td><strong>{r.quantity.toLocaleString()} {r.unit}</strong>{Number(r.received_quantity || 0) > 0 && <small className="muted">{language === 'ja' ? `受入 ${Number(r.received_quantity).toLocaleString()} · 残 ${Number(r.remaining_quantity || 0).toLocaleString()}` : `Received ${Number(r.received_quantity).toLocaleString()} · Remaining ${Number(r.remaining_quantity || 0).toLocaleString()}`}</small>}</td><td>{money(r.unit_price * r.quantity, language)}</td><td><span className={statusClass(r.status)}>{humanStatus(language, r.status)}</span></td><td>{dateText(r.due_date, language)}</td><td><div className="inline-actions">{canUpdate && next ? <button className="row-action" onClick={() => onStatus(`/api/v1/purchase-orders/${r.id}/status`, next)}>{isSupplier ? (next === 'CONFIRMED' ? tr('confirm') : tr('advance')) : tr('advance')} <ChevronRight size={13} /></button> : null}{canManage && ['DRAFT', 'SUBMITTED'].includes(r.status) && onEdit && <button className="row-action" onClick={() => onEdit(r)}>{tr('edit')}</button>}{canManage && ['DRAFT', 'CANCELLED'].includes(r.status) && onDelete && <button className="row-action danger" onClick={() => onDelete(r)}>{tr('delete')}</button>}{!canUpdate && !canManage && <span className="muted">—</span>}</div></td></tr>;
  })}{!rows.length && <tr><td colSpan={7} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div>;
}

function QualityPage({ rows, batches, finishedBatches, templates, capas, language, onCreate, canCreate, onRelease, onCreateTemplate, onEditTemplate, onDeleteTemplate, onCapaUpdate }: {
  rows: Row[]; batches: Row[]; finishedBatches: Row[]; templates: Row[]; capas: Row[]; language: Language; onCreate: () => void; canCreate: boolean;
  onRelease: (batchId: number, inspectionId: number, reason: string, finishedProduct?: boolean) => void; onCreateTemplate: () => void;
  onEditTemplate: (row: Row) => void; onDeleteTemplate: (row: Row) => void;
  onCapaUpdate: (id: number, values: Row) => void;
}) {
  const tr = (key: MessageKey) => t(language, key);
  const heldBatches = batches.filter((batch) => batch.status === 'HOLD');
  const heldFinishedBatches = finishedBatches.filter((batch) => batch.status === 'HOLD');
  const [drafts, setDrafts] = useState<Record<number, Row>>({});
  const initialDraft = (capa: Row) => drafts[capa.id] || {
    containment_action: capa.containment_action || '', root_cause: capa.root_cause || '',
    corrective_action: capa.corrective_action || '', preventive_action: capa.preventive_action || '',
    verification: capa.verification || '', owner: capa.owner || '', due_date: capa.due_date || '',
  };
  const setDraft = (capa: Row, key: string, value: string) => setDrafts((current) => ({ ...current, [capa.id]: { ...initialDraft(capa), [key]: value } }));
  const nextStatus: Record<string, string> = { OPEN: 'CONTAINED', CONTAINED: 'INVESTIGATING', INVESTIGATING: 'IMPLEMENTED', IMPLEMENTED: 'VERIFIED', VERIFIED: 'CLOSED' };
  return <>
    <PageHeading title={tr('quality')} subtitle={language === 'ja' ? '検査基準、判定、不適合、封じ込め、原因分析、是正・予防処置を管理します。' : 'Manage inspection criteria, results, containment, root cause, corrective and preventive actions.'} icon={ShieldCheck}
      action={canCreate ? <div className="inline-actions"><button className="subtle-button" onClick={onCreateTemplate}><ClipboardList size={15} />{language === 'ja' ? 'テンプレート' : 'Templates'}</button><button className="primary-button" onClick={onCreate}><Plus size={17} />{tr('newInspection')}</button></div> : undefined} />
    <div className="mini-stats"><span><ClipboardCheck size={15} />{rows.length} {language === 'ja' ? '検査記録' : 'inspections'}</span><span className="stat-good"><CheckCircle2 size={15} />{rows.filter((x) => x.result === 'PASS').length} {tr('pass')}</span><span className="stat-bad"><AlertTriangle size={15} />{rows.filter((x) => x.result === 'FAIL').length} {tr('fail')}</span><span><ClipboardList size={15} />{capas.filter((x) => x.status !== 'CLOSED').length} {language === 'ja' ? '未完了CAPA' : 'open CAPA'}</span></div>
    <section className="panel">
      <div className="panel-heading"><div><h3>{language === 'ja' ? '検査テンプレート' : 'Quality inspection templates'}</h3><p>{language === 'ja' ? '受入・工程内・最終検査の再利用可能な基準' : 'Reusable receiving, in-process and final inspection criteria'}</p></div><span className="date-pill">{templates.length} {tr('records')}</span></div>
      <div className="template-chip-list">{templates.map((template) => <div className="template-chip" key={template.id}><strong>{template.name}</strong><span className="mono">{template.code}</span><small>{humanStatus(language, template.process_type)} · {template.criteria?.length || 0} {language === 'ja' ? '基準' : 'criteria'}</small>{canCreate && <div className="inline-actions"><button className="row-action" onClick={() => onEditTemplate(template)}>{tr('edit')}</button><button className="row-action danger" onClick={() => onDeleteTemplate(template)}>{tr('delete')}</button></div>}</div>)}{!templates.length && <div className="empty-cell">{language === 'ja' ? '検査テンプレートはありません。テンプレートを作成してください。' : 'No templates yet. Create a reusable inspection template.'}</div>}</div>
    </section>
    {heldBatches.length > 0 && <TableFrame title={tr('heldBatches')} subtitle={language === 'ja' ? '合格した最新の再検査と記録済みの備考がある場合のみ解除できます。' : 'A hold can be released only after the latest inspection passes and has documented notes.'}>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('material')}</th><th>{tr('lotNumber')}</th><th>{tr('quantity')}</th><th>{tr('result')}</th><th>{tr('notes')}</th><th>{tr('action')}</th></tr></thead><tbody>
        {heldBatches.map((batch) => {
          const latest = rows.filter((inspection) => inspection.batch_id === batch.id).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime() || b.id - a.id)[0];
          const canRelease = canCreate && latest?.result === 'PASS' && String(latest?.notes || '').trim().length >= 5;
          return <tr key={batch.id}><td><strong>{batch.material_name}</strong></td><td className="mono">{batch.lot_number}</td><td>{batch.quantity_on_hand} {batch.unit}</td><td>{latest ? <span className={statusClass(latest.result)}>{humanStatus(language, latest.result)}</span> : '—'}</td><td className="cell-wrap">{latest?.notes || tr('reinspectionPending')}</td><td>{canRelease ? <button className="row-action" onClick={() => onRelease(batch.id, latest.id, latest.notes)}>{tr('releaseHold')} <CheckCircle2 size={13} /></button> : <span className="muted">{tr('reinspectionPending')}</span>}</td></tr>;
        })}
      </tbody></table></div>
    </TableFrame>}
    {heldFinishedBatches.length > 0 && <TableFrame title={language === 'ja' ? '保留中の完成品バッチ' : 'Finished-product batches on hold'} subtitle={language === 'ja' ? '完成品の最新検査が合格し、備考が記録された後にのみ解除できます。' : 'Release requires the latest batch or serial inspection to pass with documented notes.'}>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>{language === 'ja' ? '完成品バッチ' : 'Finished batch'}</th><th>{tr('product')}</th><th>{tr('quantity')}</th><th>{tr('result')}</th><th>{tr('notes')}</th><th>{tr('action')}</th></tr></thead><tbody>
        {heldFinishedBatches.map((batch) => {
          const related = rows.filter((inspection) => inspection.finished_product_batch_id === batch.id)
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime() || b.id - a.id);
          const latest = related[0];
          const canRelease = canCreate && latest?.result === 'PASS' && String(latest?.notes || '').trim().length >= 5;
          return <tr key={batch.id}><td className="mono">{batch.batch_number}</td><td><strong>{batch.product_name}</strong></td><td>{batch.quantity}</td><td>{latest ? <span className={statusClass(latest.result)}>{humanStatus(language, latest.result)}</span> : '—'}</td><td className="cell-wrap">{latest?.notes || tr('reinspectionPending')}</td><td>{canRelease ? <button className="row-action" onClick={() => onRelease(batch.id, latest.id, latest.notes, true)}>{tr('releaseHold')} <CheckCircle2 size={13} /></button> : <span className="muted">{tr('reinspectionPending')}</span>}</td></tr>;
        })}
      </tbody></table></div>
    </TableFrame>}
    <TableFrame title={tr('inspectionHistory')} subtitle={language === 'ja' ? '基準結果と判定根拠を保存します。' : 'Recorded results include the applied template criteria and inspection notes.'} action={canCreate ? <button className="subtle-button" onClick={onCreate}><Plus size={14} />{tr('createNew')}</button> : undefined}>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>{language === 'ja' ? '検査番号' : 'Inspection No.'}</th><th>{tr('product')}</th><th>{tr('batch')}</th><th>{tr('result')}</th><th>{tr('defects')}</th><th>{language === 'ja' ? '基準結果' : 'Criteria results'}</th><th>{tr('correctiveAction')}</th></tr></thead><tbody>{rows.map((r) => <tr key={r.id}><td className="mono strong">{r.inspection_number}</td><td>{r.product_name}</td><td className="mono">{batches.find((b) => b.id === r.batch_id)?.lot_number || finishedBatches.find((b) => b.id === r.finished_product_batch_id)?.batch_number || (r.finished_product_serial_id ? language === 'ja' ? `シリアル #${r.finished_product_serial_id}` : `Serial #${r.finished_product_serial_id}` : '—')}</td><td><span className={statusClass(r.result)}>{humanStatus(language, r.result)}</span></td><td>{r.defect_count} / {r.sample_size}</td><td className="cell-wrap">{Object.entries(r.criteria_results || {}).map(([key, value]) => `${key}: ${value}`).join(' · ') || '—'}</td><td className="cell-wrap">{r.corrective_action || '—'}</td></tr>)}{!rows.length && <tr><td colSpan={7} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div>
    </TableFrame>
    <section className="panel capa-panel">
      <div className="panel-heading"><div><h3>{language === 'ja' ? '是正・予防処置 (CAPA)' : 'Corrective and preventive actions (CAPA)'}</h3><p>{language === 'ja' ? '不合格検査から自動作成されたケースを段階的に完了します。' : 'Cases are opened automatically for failed inspections and progress through controlled stages.'}</p></div><span className="date-pill">{capas.length} {language === 'ja' ? '件' : 'cases'}</span></div>
      {capas.map((capa) => {
        const draft = initialDraft(capa);
        const next = nextStatus[capa.status];
        return <article className="capa-case" key={capa.id}>
          <div className="capa-case-heading"><div><strong className="mono">{capa.case_number}</strong><span>{capa.title}</span><small>{language === 'ja' ? '検査ID' : 'Inspection'} #{capa.inspection_id} · {dateText(capa.created_at, language)}</small></div><span className={statusClass(capa.status)}>{humanStatus(language, capa.status)}</span></div>
          <div className="capa-fields">
            <label>{language === 'ja' ? '封じ込め処置' : 'Containment action'}<textarea value={draft.containment_action} onChange={(e) => setDraft(capa, 'containment_action', e.target.value)} /></label>
            <label>{language === 'ja' ? '根本原因' : 'Root cause'}<textarea value={draft.root_cause} onChange={(e) => setDraft(capa, 'root_cause', e.target.value)} /></label>
            <label>{language === 'ja' ? '是正処置' : 'Corrective action'}<textarea value={draft.corrective_action} onChange={(e) => setDraft(capa, 'corrective_action', e.target.value)} /></label>
            <label>{language === 'ja' ? '予防処置' : 'Preventive action'}<textarea value={draft.preventive_action} onChange={(e) => setDraft(capa, 'preventive_action', e.target.value)} /></label>
            <label>{language === 'ja' ? '有効性確認' : 'Verification evidence'}<textarea value={draft.verification} onChange={(e) => setDraft(capa, 'verification', e.target.value)} /></label>
            <label>{language === 'ja' ? '担当者' : 'Owner'}<input value={draft.owner} onChange={(e) => setDraft(capa, 'owner', e.target.value)} /></label>
            <label>{tr('dueDate')}<input type="date" value={draft.due_date || ''} onChange={(e) => setDraft(capa, 'due_date', e.target.value)} /></label>
          </div>
          {capa.status !== 'CLOSED' && <div className="inline-actions capa-actions"><button className="subtle-button" onClick={() => onCapaUpdate(capa.id, draft)}>{language === 'ja' ? '内容を保存' : 'Save case details'}</button>{next && <button className="primary-button" onClick={() => onCapaUpdate(capa.id, { ...draft, status: next })}>{language === 'ja' ? `次へ: ${humanStatus(language, next)}` : `Advance to ${humanStatus(language, next)}`}<ChevronRight size={14} /></button>}</div>}
        </article>;
      })}
      {!capas.length && <div className="empty-cell">{language === 'ja' ? '未完了のCAPAはありません。検査が不合格になるとケースが作成されます。' : 'No CAPA cases yet. A case is opened automatically when an inspection fails.'}</div>}
    </section>
  </>;
}

function TraceabilityPage({ language, query, setQuery, onSearch, result, serials, onDownloadQR, onShip }: {
  language: Language; query: string; setQuery: (x: string) => void; onSearch: (e: FormEvent<HTMLFormElement>) => void; result: Row | null;
  serials: Row[]; onDownloadQR: (kind: 'lot' | 'serial', id: string) => void; onShip: (serial: string, customer: string, reference: string) => void;
}) {
  const tr = (key: MessageKey) => t(language, key);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [scanOpen, setScanOpen] = useState(false);
  const [scanError, setScanError] = useState('');
  const [shipDrafts, setShipDrafts] = useState<Record<string, { customer: string; reference: string }>>({});
  useEffect(() => {
    if (!scanOpen) return;
    let active = true;
    let stream: MediaStream | undefined;
    let frame = 0;
    const Detector = (window as any).BarcodeDetector;
    if (!Detector || !navigator.mediaDevices?.getUserMedia) {
      setScanError(language === 'ja' ? 'このブラウザーではカメラQR読取を利用できません。下の検索欄に番号を入力してください。' : 'Camera QR scanning is unavailable in this browser. Enter the identifier in the search field instead.');
      return () => { active = false; };
    }
    const detector = new Detector({ formats: ['qr_code', 'code_128', 'ean_13', 'ean_8'] });
    setScanError('');
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      .then(async (media) => {
        stream = media;
        if (!active || !videoRef.current) { media.getTracks().forEach((track) => track.stop()); return; }
        videoRef.current.srcObject = media;
        await videoRef.current.play();
        const detect = async () => {
          if (!active || !videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            if (codes?.length) {
              const value = String(codes[0].rawValue || '').trim();
              if (value) {
                const match = value.match(/FACTORYLINK:(?:LOT|SERIAL):(.+)$/i);
                const urlMatch = value.match(/(?:serials\/|trace\/serial\/)([^/?#]+)/i);
                setQuery(decodeURIComponent((match?.[1] || urlMatch?.[1] || value).trim()));
                setScanOpen(false);
                return;
              }
            }
          } catch { /* continue scanning; camera permissions are handled above */ }
          frame = window.requestAnimationFrame(detect);
        };
        detect();
      })
      .catch((err) => setScanError(err instanceof Error ? err.message : (language === 'ja' ? 'カメラにアクセスできません。' : 'Unable to access the camera.')));
    return () => {
      active = false;
      if (frame) window.cancelAnimationFrame(frame);
      stream?.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
    };
  }, [scanOpen, language, setQuery]);

  const isSerialResult = Boolean(result?.serial);
  const resultEvents: Row[] = result?.events || [];
  const setShip = (serial: string, key: 'customer' | 'reference', value: string) => setShipDrafts((current) => ({ ...current, [serial]: { customer: current[serial]?.customer || '', reference: current[serial]?.reference || '', [key]: value } }));
  return <>
    <PageHeading title={tr('traceability')} subtitle={language === 'ja' ? '材料ロットから生産、完成品シリアル、品質、出荷までを追跡します。' : 'Trace material lots through production, finished serials, quality and shipment.'} icon={Barcode} />
    <section className="panel trace-search-panel"><form className="trace-search-form" onSubmit={onSearch}><div className="trace-search-copy"><div className="trace-search-icon"><Barcode size={22} /></div><div><h3>{language === 'ja' ? 'ロットまたは製品シリアルを検索' : 'Search a lot or finished-product serial'}</h3><p>{language === 'ja' ? 'QRコードをカメラで読み取るか、識別番号を入力してください。' : 'Scan a QR code with your camera or enter an identifier manually.'}</p></div></div><div className="trace-search-controls"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="LOT-8831 or FP-MO-2026-004-00001" required /><button className="primary-button"><Search size={16} />{tr('search')}</button><button className="subtle-button" type="button" onClick={() => setScanOpen((value) => !value)}><Barcode size={16} />{language === 'ja' ? 'QRスキャン' : 'Scan QR'}</button></div></form>{scanOpen && <div className="qr-scanner-panel"><video ref={videoRef} playsInline muted /><div><strong>{language === 'ja' ? 'QRコードをカメラに向けてください' : 'Point your camera at a QR code'}</strong><p className="muted">{language === 'ja' ? '読み取り後、自動的に識別番号が検索欄に入力されます。' : 'The identifier will be placed in the search field when detected.'}</p>{scanError && <p className="alert-inline">{scanError}</p>}<button type="button" className="subtle-button" onClick={() => setScanOpen(false)}>{tr('close')}</button></div></div>}</section>

    {result && (isSerialResult ? <>
      <section className="panel"><div className="panel-heading"><div><h3>{language === 'ja' ? '完成品の検査・是正履歴' : 'Finished-product inspection and corrective-action history'}</h3><p>{result.finished_product_batch?.batch_number || result.serial.serial_number}</p></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>{language === 'ja' ? '検査番号' : 'Inspection'}</th><th>{tr('result')}</th><th>{tr('notes')}</th><th>{tr('correctiveAction')}</th><th>{tr('dueDate')}</th></tr></thead><tbody>{(result.finished_product_inspections || []).map((inspection: Row) => <tr key={inspection.id}><td className="mono">{inspection.inspection_number}</td><td><span className={statusClass(inspection.result)}>{humanStatus(language, inspection.result)}</span></td><td>{inspection.notes || '—'}</td><td>{inspection.corrective_action || '—'}</td><td>{dateText(inspection.created_at, language)}</td></tr>)}{!result.finished_product_inspections?.length && <tr><td colSpan={5} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div></section>
      <div className="trace-batch-summary"><div><span className="summary-label">{language === 'ja' ? '製品シリアル' : 'Finished serial'}</span><strong className="mono">{result.serial.serial_number}</strong></div><div><span className="summary-label">{tr('product')}</span><strong>{result.serial.product_name}</strong></div><div><span className="summary-label">{tr('status')}</span><span className={statusClass(result.serial.status)}>{humanStatus(language, result.serial.status)}</span></div><div><span className="summary-label">{tr('orderNumber')}</span><strong className="mono">{result.production_order?.order_number || '—'}</strong></div><button className="subtle-button" onClick={() => onDownloadQR('serial', result.serial.serial_number)}><Barcode size={15} />{language === 'ja' ? 'QRコード' : 'Download QR'}</button></div>
      <section className="panel"><div className="panel-heading"><div><h3>{language === 'ja' ? '完成品の製造情報' : 'Finished-product manufacturing record'}</h3><p>{language === 'ja' ? '生産オーダーと消費材料の関係' : 'Production order and the source material genealogy'}</p></div></div><div className="source-genealogy-list">{(result.sources || []).map((source: Row) => <div className="genealogy-card" key={source.batch.id}><div><strong>{source.batch.material_name}</strong><small className="mono">{source.batch.lot_number}</small></div><div><span>{source.supplier?.name || '—'}</span><small>{source.purchase_order?.po_number || (language === 'ja' ? '発注書なし' : 'No PO link')}</small></div><div><span>{source.batch.quantity_on_hand} {source.batch.unit}</span><small>{language === 'ja' ? '現在庫' : 'Current stock'}</small></div><button className="row-action" onClick={() => { setQuery(source.batch.lot_number); }}>{language === 'ja' ? 'ロットを入力' : 'Use lot'} <ChevronRight size={13} /></button></div>)}{!result.sources?.length && <div className="empty-cell">{language === 'ja' ? 'この製品に紐付く材料ロットはありません。' : 'No source material lots are linked to this finished product.'}</div>}</div></section>
      <section className="panel"><div className="panel-heading"><div><h3>{language === 'ja' ? '出荷情報' : 'Shipment record'}</h3><p>{language === 'ja' ? '顧客と出荷参照番号を記録します。' : 'Record the customer and shipment reference for this serial.'}</p></div></div>{result.serial.status === 'AVAILABLE' ? <div className="ship-form"><label>{language === 'ja' ? '顧客名' : 'Customer'}<input value={shipDrafts[result.serial.serial_number]?.customer || ''} onChange={(e) => setShip(result.serial.serial_number, 'customer', e.target.value)} /></label><label>{language === 'ja' ? '出荷参照番号' : 'Shipment reference'}<input value={shipDrafts[result.serial.serial_number]?.reference || ''} onChange={(e) => setShip(result.serial.serial_number, 'reference', e.target.value)} /></label><button className="primary-button" disabled={!shipDrafts[result.serial.serial_number]?.customer?.trim() || !shipDrafts[result.serial.serial_number]?.reference?.trim()} onClick={() => onShip(result.serial.serial_number, shipDrafts[result.serial.serial_number].customer, shipDrafts[result.serial.serial_number].reference)}><Truck size={15} />{language === 'ja' ? '出荷を記録' : 'Record shipment'}</button></div> : <p>{result.serial.customer_name || '—'} · {result.serial.shipment_reference || '—'} · {dateText(result.serial.shipped_at, language)}</p>}</section>
    </> : <>
      {(result.finished_product_batches || []).map((finishedBatch: Row) => <section className="panel" key={finishedBatch.id}><div className="panel-heading"><div><h3>{language === 'ja' ? '完成品バッチの検査履歴' : 'Finished-product batch inspection history'}</h3><p>{finishedBatch.batch_number} · {finishedBatch.product_name} · {humanStatus(language, finishedBatch.status)}</p></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>{language === 'ja' ? '検査番号' : 'Inspection'}</th><th>{tr('result')}</th><th>{tr('notes')}</th><th>{tr('correctiveAction')}</th><th>{tr('dueDate')}</th></tr></thead><tbody>{(finishedBatch.inspections || []).map((inspection: Row) => <tr key={inspection.id}><td className="mono">{inspection.inspection_number}</td><td><span className={statusClass(inspection.result)}>{humanStatus(language, inspection.result)}</span></td><td>{inspection.notes || '—'}</td><td>{inspection.corrective_action || '—'}</td><td>{dateText(inspection.created_at, language)}</td></tr>)}{!finishedBatch.inspections?.length && <tr><td colSpan={5} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div></section>)}
      <div className="trace-batch-summary"><div><span className="summary-label">{tr('material')}</span><strong>{result.batch.material_name}</strong></div><div><span className="summary-label">{tr('lotNumber')}</span><strong className="mono">{result.batch.lot_number}</strong></div><div><span className="summary-label">{tr('quantity')}</span><strong>{result.batch.quantity_on_hand} {result.batch.unit}</strong></div><div><span className="summary-label">{tr('status')}</span><span className={statusClass(result.batch.status)}>{humanStatus(language, result.batch.status)}</span></div><button className="subtle-button" onClick={() => onDownloadQR('lot', result.batch.lot_number)}><Barcode size={15} />{language === 'ja' ? 'QRコード' : 'Download QR'}</button></div>
      {result.purchase_order && <div className="mini-stats"><span><Truck size={15} />{result.supplier?.name || '—'}</span><span><ClipboardList size={15} />{result.purchase_order.po_number}</span><span><PackageCheck size={15} />{result.purchase_order.received_quantity} / {result.purchase_order.quantity} {result.purchase_order.unit}</span></div>}
      <section className="panel"><div className="panel-heading"><div><h3>{tr('traceHistory')}</h3><p>{language === 'ja' ? '受入から出荷までのイベント履歴' : 'Chronological lot events from receipt through shipment'}</p></div><span className="date-pill">{resultEvents.length} {language === 'ja' ? '件のイベント' : 'events'}</span></div><div className="trace-timeline">{resultEvents.map((event: Row) => <div className="trace-event" key={event.id}><div className="trace-event-rail"><span className="trace-event-dot" /></div><div className="trace-event-main"><div className="trace-event-head"><strong>{humanStatus(language, event.event_type)}</strong><span>{dateText(event.created_at, language)}</span></div><p>{event.details || '—'}</p><small className="mono">{event.reference}</small></div></div>)}{!resultEvents.length && <div className="empty-cell">{tr('noRecords')}</div>}</div></section>
      <section className="panel"><div className="panel-heading"><div><h3>{language === 'ja' ? '生産・完成品への展開' : 'Downstream production and finished goods'}</h3><p>{language === 'ja' ? 'この材料ロットを消費した生産オーダーと製品シリアル' : 'Production orders and finished serials that consumed this material lot'}</p></div><span className="date-pill">{result.finished_serials?.length || 0} {language === 'ja' ? 'シリアル' : 'serials'}</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('orderNumber')}</th><th>{tr('product')}</th><th>{tr('status')}</th><th>{language === 'ja' ? '完成品シリアル' : 'Finished serials'}</th></tr></thead><tbody>{(result.production_orders || []).map((order: Row) => <tr key={order.id}><td className="mono">{order.order_number}</td><td>{order.product_name}</td><td><span className={statusClass(order.status)}>{humanStatus(language, order.status)}</span></td><td>{(result.finished_serials || []).filter((serial: Row) => serial.production_order_id === order.id).map((serial: Row) => <button key={serial.id} className="row-action" onClick={() => { setQuery(serial.serial_number); }}>{serial.serial_number}</button>)}</td></tr>)}{!result.production_orders?.length && <tr><td colSpan={4} className="empty-cell">{language === 'ja' ? 'このロットを消費した生産オーダーはありません。' : 'No production orders have consumed this lot.'}</td></tr>}</tbody></table></div></section>
      <section className="panel"><div className="panel-heading"><div><h3>{tr('stockLedger')}</h3><p>{language === 'ja' ? '数量変更の不変記録' : 'Recorded quantity changes against the lot'}</p></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('status')}</th><th>{tr('quantity')}</th><th>{tr('orderNumber')}</th><th>{tr('notes')}</th><th>{tr('dueDate')}</th></tr></thead><tbody>{(result.movements || []).map((m: Row) => <tr key={m.id}><td>{humanStatus(language, m.movement_type)}</td><td>{m.quantity}</td><td className="mono">{m.reference}</td><td>{m.note}</td><td>{dateText(m.created_at, language)}</td></tr>)}</tbody></table></div></section>
    </>)}

    <section className="panel"><div className="panel-heading"><div><h3>{language === 'ja' ? '完成品シリアル台帳' : 'Finished-product serial register'}</h3><p>{language === 'ja' ? '生産完了時に生成されたシリアル番号と出荷状態' : 'Serial numbers generated at production completion and their shipping state'}</p></div><span className="date-pill">{serials.length} {tr('records')}</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>{language === 'ja' ? 'シリアル番号' : 'Serial number'}</th><th>{tr('product')}</th><th>{tr('orderNumber')}</th><th>{tr('status')}</th><th>{language === 'ja' ? '出荷先' : 'Customer'}</th><th>{tr('action')}</th></tr></thead><tbody>{serials.map((serial) => <tr key={serial.id}><td><button className="row-action mono" onClick={() => setQuery(serial.serial_number)}>{serial.serial_number}</button></td><td>{serial.product_name}</td><td className="mono">{serial.production_order_id}</td><td><span className={statusClass(serial.status)}>{humanStatus(language, serial.status)}</span></td><td>{serial.customer_name || '—'}</td><td><div className="inline-actions"><button className="icon-button" title="Download QR" onClick={() => onDownloadQR('serial', serial.serial_number)}><Barcode size={16} /></button><button className="row-action" onClick={() => setQuery(serial.serial_number)}>{language === 'ja' ? '履歴' : 'Trace'}</button></div></td></tr>)}{!serials.length && <tr><td colSpan={6} className="empty-cell">{language === 'ja' ? 'シリアル番号はありません。製造オーダーをシリアル追跡ありで完了すると生成されます。' : 'No serials yet. Complete a production order with serial tracking enabled to generate them.'}</td></tr>}</tbody></table></div></section>
  </>;
}

function MaintenancePage({ tasks, equipment, analytics, language, onCreate, onCreateEquipment, canManage, onUpdate, onEditTask, onDeleteTask, onEditEquipment, onDeleteEquipment }: {
  tasks: Row[]; equipment: Row[]; analytics: Row; language: Language; onCreate: () => void; onCreateEquipment: () => void;
  canManage: boolean; onUpdate: (p: string, s: string, note?: string, downtimeMinutes?: number) => void;
  onEditTask: (row: Row) => void; onDeleteTask: (row: Row) => void; onEditEquipment: (row: Row) => void; onDeleteEquipment: (row: Row) => void;
}) {
  const tr = (key: MessageKey) => t(language, key); const [downtime, setDowntime] = useState<Record<number, string>>({});
  return <><PageHeading title={tr('maintenance')} subtitle={language === 'ja' ? '設備台帳、予防保全、突発停止、停止時間を管理します。' : 'Manage equipment, preventive work, unplanned downtime and maintenance history.'} icon={Wrench} action={canManage ? <div className="inline-actions"><button className="subtle-button" onClick={onCreateEquipment}>{language === 'ja' ? '設備を登録' : 'Add equipment'}</button><button className="primary-button" onClick={onCreate}><Plus size={17} />{tr('newTask')}</button></div> : undefined} />
    <div className="mini-stats"><span><Wrench size={15} />{equipment.length} {tr('equipment')}</span><span><CalendarClock size={15} />{tasks.filter((x) => x.status === 'OVERDUE').length} {humanStatus(language, 'OVERDUE')}</span><span><Clock3 size={15} />{analytics.total_downtime_minutes ?? tasks.reduce((sum, x) => sum + (x.downtime_minutes || 0), 0)} {tr('downtime')}</span></div>
    <section className="panel maintenance-analytics"><div className="panel-heading"><div><h3>{language === 'ja' ? '停止時間分析' : 'Downtime analytics'}</h3><p>{language === 'ja' ? '作業分類ごとの記録済み停止時間' : 'Recorded downtime split by maintenance classification'}</p></div><Gauge size={20} /></div><div className="downtime-breakdown"><div><span>{language === 'ja' ? '予防保全' : 'Preventive downtime'}</span><strong>{analytics.preventive_downtime_minutes ?? 0} min</strong></div><div><span>{language === 'ja' ? '突発保全' : 'Unplanned downtime'}</span><strong>{analytics.unplanned_downtime_minutes ?? 0} min</strong></div><div><span>{language === 'ja' ? '設備稼働率' : 'Equipment availability'}</span><strong>{analytics.availability_percent == null ? '—' : `${analytics.availability_percent}%`}</strong><small>{language === 'ja' ? '計画稼働時間を指定すると算出します。' : 'Supply planned operating minutes for the reporting period to calculate availability.'}</small></div></div></section>
    <TableFrame title={tr('maintenanceSchedule')} subtitle={language === 'ja' ? '予定・進行中・完了の保全作業' : 'Scheduled, active and completed maintenance work'} action={canManage ? <button className="subtle-button" onClick={onCreate}><Plus size={14} />{tr('createNew')}</button> : undefined}><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('equipmentName')}</th><th>{tr('task')}</th><th>{language === 'ja' ? '区分' : 'Type'}</th><th>{tr('dueDate')}</th><th>{tr('status')}</th><th>{tr('downtime')}</th><th>{tr('action')}</th></tr></thead><tbody>{tasks.map((r) => <tr key={r.id}><td><strong>{r.equipment}</strong></td><td>{r.title}</td><td><span className={statusClass(r.maintenance_type || 'PREVENTIVE')}>{humanStatus(language, r.maintenance_type || 'PREVENTIVE')}</span></td><td>{dateText(r.due_date, language)}</td><td><span className={statusClass(r.status)}>{humanStatus(language, r.status)}</span></td><td>{r.downtime_minutes || 0}</td><td><div className="inline-actions">{canManage && r.status !== 'COMPLETED' && r.status !== 'CANCELLED' && <><input aria-label={tr('downtime')} className="inline-number" type="number" min="0" value={downtime[r.id] ?? String(r.downtime_minutes || 0)} onChange={(e) => setDowntime((v) => ({ ...v, [r.id]: e.target.value }))} /><button className="row-action" onClick={() => onUpdate(`/api/v1/maintenance/tasks/${r.id}`, 'COMPLETED', '', Number(downtime[r.id] ?? r.downtime_minutes ?? 0))}>{language === 'ja' ? '完了にする' : 'Complete'} <CheckCircle2 size={13} /></button></>}{canManage && r.status === 'SCHEDULED' && <button className="row-action" onClick={() => onEditTask(r)}>{tr('edit')}</button>}{canManage && (r.status === 'SCHEDULED' || r.status === 'CANCELLED') && <button className="row-action danger" onClick={() => onDeleteTask(r)}>{tr('delete')}</button>}{!canManage && <span className="muted">—</span>}</div></td></tr>)}{!tasks.length && <tr><td colSpan={7} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div></TableFrame>
    <section className="equipment-grid">{equipment.map((e) => <div className="equipment-card" key={e.id}><div className="equipment-top"><div className="equipment-icon"><Wrench size={18} /></div><span className={statusClass(e.status)}>{humanStatus(language, e.status)}</span></div><strong>{e.name}</strong><span>{e.code} · {e.location}</span><div className="equipment-foot"><span>{tr('dueDate')}</span><strong>{dateText(e.next_maintenance, language)}</strong></div><div className="equipment-foot"><span>{tr('downtime')}</span><strong>{e.total_downtime_minutes || 0} min</strong></div>{canManage && <div className="inline-actions"><button className="row-action" onClick={() => onEditEquipment(e)}>{tr('edit')}</button><button className="row-action danger" onClick={() => onDeleteEquipment(e)}>{tr('delete')}</button></div>}</div>)}</section>
  </>;
}

function ReportsPage({ language, onDownload }: { language: Language; onDownload: (dataset: ReportDataset, kind: 'csv' | 'xlsx') => void }) {
  const cards: { dataset: ReportDataset; title: string; description: string }[] = language === 'ja' ? [
    { dataset: 'production', title: '生産レポート', description: '生産オーダー、完了数、不良数、進捗状況を出力します。' },
    { dataset: 'inventory', title: '在庫レポート', description: 'ロット別在庫、引当数量、利用可能数、在庫評価額を出力します。' },
    { dataset: 'quality', title: '品質レポート', description: '検査結果、不良数、検査数量、不良率、是正処置を出力します。' },
  ] : [
    { dataset: 'production', title: 'Production report', description: 'Production orders, output, rejected quantities and status.' },
    { dataset: 'inventory', title: 'Inventory report', description: 'Lot-level on-hand, reserved and available stock with JPY valuation.' },
    { dataset: 'quality', title: 'Quality report', description: 'Inspection outcomes, defect counts, sample sizes, defect rate and corrective actions.' },
  ];
  return <><PageHeading title={t(language, 'reports')} subtitle={language === 'ja' ? '組織の実データから生産・在庫・品質レポートを出力します。' : 'Export production, inventory and quality reports from live organisation data.'} icon={ChartNoAxesCombined} /><section className="reports-grid">{cards.map((card) => <div className="report-card" key={card.dataset}><div className={`report-icon report-${card.dataset}`}><FileSpreadsheet size={21} /></div><h3>{card.title}</h3><p>{card.description}</p><div className="report-actions"><button className="primary-button" onClick={() => onDownload(card.dataset, 'csv')}><Download size={15} />CSV</button><button className="subtle-button" onClick={() => onDownload(card.dataset, 'xlsx')}><Download size={15} />Excel</button></div></div>)}</section><div className="report-note"><ShieldCheck size={17} /><span>{language === 'ja' ? 'レポートには認証済み組織のデータのみが含まれます。' : 'Reports are scoped to the authenticated organisation and supplier accounts cannot export factory reports.'}</span></div></>;
}

function UsersPage({ rows, language, onCreate, canManage, currentUserId, busy, onUpdate, onRemove }: {
  rows: Row[]; language: Language; onCreate: () => void; canManage: boolean; currentUserId: number; busy: boolean;
  onUpdate: (id: number, payload: Row, message?: string) => void; onRemove: (id: number) => void;
}) {
  const tr = (key: MessageKey) => t(language, key);
  const roles = ['ORG_ADMIN', 'PRODUCTION_MANAGER', 'WAREHOUSE_MANAGER', 'QUALITY_INSPECTOR', 'MAINTENANCE_MANAGER', 'OPERATOR'];
  return <><PageHeading title={tr('users')} subtitle={language === 'ja' ? '組織内ユーザーとロールベースのアクセス権を管理します。' : 'Manage organisation users and role-based access.'} icon={Users} action={<button className="primary-button" onClick={onCreate}><Plus size={17} />{tr('newUser')}</button>} /><TableFrame title={tr('users')} subtitle={`${rows.length} ${tr('records')}`} action={<button className="subtle-button" onClick={onCreate}><Plus size={14} />{tr('add')}</button>}><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('name')}</th><th>{tr('email')}</th><th>{tr('role')}</th><th>{tr('language')}</th><th>{tr('status')}</th><th>{tr('dueDate')}</th><th>{tr('action')}</th></tr></thead><tbody>{rows.map((r) => <tr key={r.id}><td><div className="person-cell"><div className="avatar avatar-tiny">{r.full_name.split(' ').map((x: string) => x[0]).join('').slice(0, 2)}</div><strong>{r.full_name}</strong></div></td><td>{r.email}</td><td>{canManage && r.id !== currentUserId ? <select className="inline-select" aria-label={tr('role')} value={r.role} disabled={busy} onChange={(e) => onUpdate(r.id, { role: e.target.value })}>{roles.map((role) => <option key={role} value={role}>{humanStatus(language, role)}</option>)}</select> : humanStatus(language, r.role)}</td><td>{r.language === 'ja' ? '日本語' : 'English'}</td><td><span className={statusClass(r.is_active ? 'ACTIVE' : 'CANCELLED')}>{humanStatus(language, r.is_active ? 'ACTIVE' : 'CANCELLED')}</span></td><td>{dateText(r.created_at, language)}</td><td>{canManage && r.id !== currentUserId ? <button className="row-action danger" disabled={busy} onClick={() => onRemove(r.id)}>{language === 'ja' ? '無効化' : 'Deactivate'}</button> : <span className="muted">—</span>}</td></tr>)}{!rows.length && <tr><td colSpan={7} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div></TableFrame><div className="report-note"><ShieldCheck size={17} /><span>{language === 'ja' ? '各ユーザーは1つの組織に紐づき、APIで組織境界が検証されます。' : 'Each user belongs to one organisation; API endpoints enforce organisation boundaries.'}</span></div></>;
}

function DocumentsPage({ rows, language, onUpload, onDownload, onDelete, onOrders, isSupplier }: { rows: Row[]; language: Language; onUpload: (e: FormEvent<HTMLFormElement>) => void; onDownload: (id: number, name: string) => void; onDelete: (row: Row) => void; onOrders: () => Promise<any>; isSupplier: boolean }) {
  const tr = (key: MessageKey) => t(language, key); const [orders, setOrders] = useState<Row[]>([]);
  useEffect(() => { onOrders().then((result) => setOrders(result || [])); }, []);
  return <><PageHeading title={tr('documents')} subtitle={language === 'ja' ? '発注書に関連する帳票や仕入先書類を安全に共有します。' : 'Share supplier and factory documents against purchase orders.'} icon={FileText} /><section className="panel upload-panel"><form onSubmit={onUpload} className="upload-form"><div className="upload-symbol"><Upload size={22} /></div><div className="upload-copy"><h3>{tr('upload')}</h3><p>{tr('fileTypes')}</p></div><div className="upload-fields">{!isSupplier && <select name="purchase_order_id" defaultValue=""><option value="">{language === 'ja' ? '組織全体の書類' : 'Organisation document'}</option>{orders.map((x) => <option key={x.id} value={x.id}>{x.po_number} · {x.item_name}</option>)}</select>}{isSupplier && <select name="purchase_order_id" required defaultValue=""><option value="">{tr('attachToPO')}</option>{orders.map((x) => <option key={x.id} value={x.id}>{x.po_number} · {x.item_name}</option>)}</select>}<input name="document" type="file" accept=".pdf,.png,.jpg,.jpeg,.csv,.xlsx" required /><button className="primary-button"><Upload size={16} />{tr('upload')}</button></div></form></section><TableFrame title={tr('documents')} subtitle={`${rows.length} ${tr('records')}`}><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('name')}</th><th>{tr('item')}</th><th>{language === 'ja' ? 'サイズ' : 'Size'}</th><th>{tr('dueDate')}</th><th>{tr('action')}</th></tr></thead><tbody>{rows.map((r) => <tr key={r.id}><td><div className="file-cell"><div className="file-icon"><FileText size={17} /></div><strong>{r.display_name}</strong></div></td><td className="mono">{r.purchase_order_id ? `PO #${r.purchase_order_id}` : '—'}</td><td>{(r.size_bytes / 1024).toFixed(1)} KB</td><td>{dateText(r.created_at, language)}</td><td><div className="inline-actions"><button className="row-action" onClick={() => onDownload(r.id, r.display_name)}><Download size={14} />{language === 'ja' ? 'ダウンロード' : 'Download'}</button><button className="row-action danger" onClick={() => onDelete(r)}>{tr('delete')}</button></div></td></tr>)}{!rows.length && <tr><td colSpan={5} className="empty-cell">{tr('noDocuments')}</td></tr>}</tbody></table></div></TableFrame></>;
}

function NotificationsPage({ rows, language, unreadCount, onRead, onReadAll }: { rows: Row[]; language: Language; unreadCount: number; onRead: (id: number) => void; onReadAll: () => void }) {
  const [filter, setFilter] = useState<'all' | 'unread' | 'critical'>('all');
  const tr = (key: MessageKey) => t(language, key);
  const filtered = rows.filter((row) => filter === 'unread' ? !row.is_read : filter === 'critical' ? ['WARNING', 'CRITICAL'].includes(String(row.level).toUpperCase()) : true);
  return <><PageHeading title={tr('notifications')} subtitle={language === 'ja' ? '発注、生産、品質、設備保全に関するお知らせ。' : 'Updates from procurement, production, quality and maintenance.'} icon={Bell} action={unreadCount > 0 ? <button className="subtle-button" onClick={onReadAll}>{tr('markAllRead')}</button> : undefined} /><div className="notification-toolbar"><div className="notification-filters"><button className={filter === 'all' ? 'filter-chip active' : 'filter-chip'} onClick={() => setFilter('all')}>{tr('allNotifications')} <span>{rows.length}</span></button><button className={filter === 'unread' ? 'filter-chip active' : 'filter-chip'} onClick={() => setFilter('unread')}>{tr('unreadOnly')} <span>{unreadCount}</span></button><button className={filter === 'critical' ? 'filter-chip active' : 'filter-chip'} onClick={() => setFilter('critical')}>{tr('attentionRequired')}</button></div><span className="notification-count-summary">{filtered.length} {tr('records')}</span></div><div className="notification-list">{filtered.map((r) => <div className={`notification-card ${r.is_read ? 'is-read' : ''}`} key={r.id}><div className={`notification-symbol ${String(r.level).toLowerCase()}`}><Bell size={18} /></div><div className="notification-content"><div className="notification-title"><strong>{r.title}</strong><span className={statusClass(r.level)}>{humanStatus(language, r.level)}</span></div><p>{r.body}</p><small>{dateText(r.created_at, language)}</small></div>{!r.is_read && <button className="text-link" onClick={() => onRead(r.id)}>{tr('markRead')}</button>}</div>)}{!filtered.length && <EmptyPage icon={Bell} title={filter === 'unread' ? tr('allCaughtUp') : tr('noRecords')} description={language === 'ja' ? '選択した条件に一致する通知はありません。' : 'There are no notifications matching this filter.'} />}</div></>;
}

function SettingsPage({ organization, language, onLanguage, onReload }: { organization: Row; language: Language; onLanguage: (l: Language) => void; onReload: () => void }) {
  const tr = (key: MessageKey) => t(language, key);
  return <><PageHeading title={tr('settings')} subtitle={language === 'ja' ? '組織情報、ロケール、表示設定を確認します。' : 'Review your organisation profile and locale preferences.'} icon={Settings} /><div className="settings-grid"><section className="panel settings-panel"><div className="panel-heading"><div><h3>{tr('organization')}</h3><p>{language === 'ja' ? '登録済みの組織プロフィール' : 'Registered organisation profile'}</p></div><Building2 size={19} /></div><div className="settings-fields"><label>{tr('name')}<input value={organization.name || ''} readOnly /></label><label>{tr('code')}<input value={organization.code || ''} readOnly /></label><label>{tr('prefecture')}<input value={organization.prefecture || ''} readOnly /></label><label>{tr('timezone')}<input value={organization.timezone || 'Asia/Tokyo'} readOnly /></label><label>{tr('currency')}<input value={organization.currency || 'JPY'} readOnly /></label><label>{language === 'ja' ? '住所' : 'Address'}<input value={organization.address || ''} readOnly /></label></div></section><section className="panel settings-panel"><div className="panel-heading"><div><h3>{tr('language')}</h3><p>{language === 'ja' ? '画面表示言語を選択します。' : 'Choose your preferred interface language.'}</p></div><Globe2 size={19} /></div><div className="language-choice"><button className={language === 'ja' ? 'language-option selected' : 'language-option'} onClick={() => onLanguage('ja')}><span className="language-flag">あ</span><div><strong>日本語</strong><small>Japanese interface</small></div>{language === 'ja' && <CheckCircle2 size={18} />}</button><button className={language === 'en' ? 'language-option selected' : 'language-option'} onClick={() => onLanguage('en')}><span className="language-flag flag-en">EN</span><div><strong>English</strong><small>English interface</small></div>{language === 'en' && <CheckCircle2 size={18} />}</button></div><div className="settings-footnote"><ShieldCheck size={16} /><span>{language === 'ja' ? '日付はAsia/Tokyoで表示し、サーバー時刻はUTCで保存されます。' : 'Dates are displayed in Asia/Tokyo; server timestamps are stored in UTC.'}</span></div><button className="subtle-button" onClick={onReload}><RefreshCw size={14} />{tr('refresh')}</button></section></div></>;
}

function AuditPage({ rows, language }: { rows: Row[]; language: Language }) {
  const tr = (key: MessageKey) => t(language, key);
  return <><PageHeading title={tr('audit')} subtitle={language === 'ja' ? '組織内の重要な変更と操作履歴。' : 'A record of significant actions performed within this organisation.'} icon={Activity} /><TableFrame title={tr('audit')} subtitle={`${rows.length} ${tr('records')}`}><div className="table-scroll"><table className="data-table"><thead><tr><th>{tr('action')}</th><th>{tr('item')}</th><th>{tr('code')}</th><th>{language === 'ja' ? 'ユーザーID' : 'User ID'}</th><th>{tr('dueDate')}</th></tr></thead><tbody>{rows.map((r) => <tr key={r.id}><td><span className="audit-action">{r.action}</span></td><td>{r.entity_type}</td><td className="mono">{r.entity_id}</td><td>{r.user_id}</td><td>{dateText(r.created_at, language)}</td></tr>)}{!rows.length && <tr><td colSpan={5} className="empty-cell">{tr('noRecords')}</td></tr>}</tbody></table></div></TableFrame></>;
}

function ConfirmDialog({ language, label, busy, onCancel, onConfirm }: { language: Language; label: string; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  const tr = (key: MessageKey) => t(language, key);
  return <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
    <section className="modal-card confirm-card" role="alertdialog" aria-modal="true" aria-labelledby="confirm-delete-title">
      <div className="modal-header"><div><span className="eyebrow">FACTORYLINK</span><h2 id="confirm-delete-title">{tr('deleteTitle')}</h2></div><button className="icon-button" onClick={onCancel} aria-label={tr('close')}><X size={19} /></button></div>
      <div className="modal-body"><p className="confirm-label"><AlertTriangle size={17} />{label}</p><p className="muted">{tr('deleteBody')}</p></div>
      <div className="modal-footer"><button type="button" className="subtle-button" onClick={onCancel}>{tr('cancel')}</button><button type="button" className="danger-button" disabled={busy} onClick={onConfirm}>{busy ? tr('loading') : tr('delete')}</button></div>
    </section>
  </div>;
}

function CreateModal({ page, mode, editing, language, isSupplier, form, setField, data, onClose, onSubmit, loading }: { page: Page; mode: ModalMode; editing: boolean; language: Language; isSupplier: boolean; form: Row; setField: (key: string, value: any) => void; data: any; onClose: () => void; onSubmit: (e: FormEvent<HTMLFormElement>) => void; loading: boolean }) {
  const tr = (key: MessageKey) => t(language, key);
  const [suppliers, setSuppliers] = useState<Row[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<Row[]>([]);
  const editTitles: Record<string, string> = {
    suppliers: language === 'ja' ? '仕入先を編集' : 'Edit supplier',
    purchaseOrders: language === 'ja' ? '発注書を編集' : 'Edit purchase order',
    production: language === 'ja' ? '生産オーダーを編集' : 'Edit production order',
    maintenance: mode === 'equipment' ? (language === 'ja' ? '設備を編集' : 'Edit equipment') : (language === 'ja' ? '保全タスクを編集' : 'Edit maintenance task'),
    quality: language === 'ja' ? '検査テンプレートを編集' : 'Edit inspection template',
    users: language === 'ja' ? 'ユーザーを編集' : 'Edit user',
  };
  const titles: Record<string, string> = { suppliers: tr('newSupplier'), purchaseOrders: tr('newPO'), production: tr('newProduction'), inventory: mode === 'adjustment' ? (language === 'ja' ? '在庫調整' : 'Adjust inventory') : tr('newReceipt'), quality: mode === 'qualityTemplate' ? (language === 'ja' ? '検査テンプレートを作成' : 'Create quality template') : tr('newInspection'), maintenance: mode === 'equipment' ? (language === 'ja' ? '設備を登録' : 'Register equipment') : tr('newTask'), users: language === 'ja' ? 'ユーザーを招待' : 'Invite user' };
  useEffect(() => {
    if (page === 'purchaseOrders' || page === 'inventory') {
      api<Row[]>('/api/v1/suppliers', sessionStorage.getItem(ACCESS) || '').then(setSuppliers).catch(() => {});
    }
    if (page === 'inventory') {
      api<Row[]>('/api/v1/purchase-orders', sessionStorage.getItem(ACCESS) || '')
        .then((rows) => setPurchaseOrders(rows.filter((row) => ['CONFIRMED', 'IN_TRANSIT', 'PARTIALLY_DELIVERED'].includes(row.status) && (row.remaining_quantity ?? row.quantity) > 0)))
        .catch(() => setPurchaseOrders([]));
    }
  }, [page]);
  const input = (key: string, label: string, type = 'text', placeholder = '', required = true, min?: string) => <label>{label}<input type={type} value={form[key] ?? ''} min={min} step={type === 'number' && ['quantity', 'unit_price', 'unit_cost', 'material_required', 'quantity_delta'].includes(key) ? 'any' : undefined} onChange={(e) => setField(key, e.target.value)} placeholder={placeholder} required={required} /></label>;
  const select = (key: string, label: string, options: { value: string; label: string }[], required = true) => <label>{label}<select value={form[key] ?? ''} onChange={(e) => setField(key, e.target.value)} required={required}><option value="">—</option>{options.map((o) => <option value={o.value} key={o.value}>{o.label}</option>)}</select></label>;
  let fields: React.ReactNode = null;
  if (page === 'suppliers') fields = <div className="form-grid">{input('code', tr('code'))}{input('name', tr('name'))}{input('contact_name', tr('contact'), 'text', '', false)}{input('email', tr('email'), 'email', '', false)}{input('phone', tr('phone'), 'tel', '', false)}{input('prefecture', tr('prefecture'), 'text', '', false)}{select('status', tr('status'), [{ value: 'ACTIVE', label: humanStatus(language, 'ACTIVE') }, { value: 'INACTIVE', label: humanStatus(language, 'INACTIVE') }], false)}{input('supplier_organization_code', language === 'ja' ? '仕入先会社コード（任意）' : 'Supplier workspace code (optional)', 'text', language === 'ja' ? '仕入先から共有されたコード' : 'Code shared by the supplier', false)}</div>;
  if (page === 'purchaseOrders') fields = <div className="form-grid">{select('supplier_id', tr('suppliers'), suppliers.map((x) => ({ value: String(x.id), label: x.name })))}{input('po_number', tr('orderNumber'))}{input('item_name', tr('item'))}{input('quantity', tr('quantity'), 'number', '', true, '0.001')}{input('unit', tr('unit'), 'text', 'pcs', true)}{input('unit_price', tr('price'), 'number', '0', false, '0')}{input('due_date', tr('dueDate'), 'date', '', false)}</div>;
  if (page === 'production') fields = <div className="form-grid">{input('order_number', tr('orderNumber'))}{input('product_name', tr('product'))}{input('quantity', tr('quantity'), 'number', '', true, '0.001')}{input('material_name', tr('material'), 'text', '', false)}{input('material_required', tr('materialRequired'), 'number', '0', false, '0')}{input('due_date', tr('dueDate'), 'date', '', false)}<label className="checkbox-field span-two"><input type="checkbox" checked={form.track_serials !== false} onChange={(e) => setField('track_serials', e.target.checked)} />{language === 'ja' ? '完成品シリアル番号を自動生成する' : 'Generate a unique serial number for each completed unit'}</label></div>;
  if (page === 'inventory' && mode === 'adjustment') fields = <div className="form-grid">{select('batch_id', language === 'ja' ? '対象ロット' : 'Material batch', (Array.isArray(data) ? data : []).map((x: Row) => ({ value: String(x.id), label: `${x.lot_number} · ${x.material_name} · ${x.quantity_on_hand} ${x.unit}` })))}{input('quantity_delta', language === 'ja' ? '数量差分 (+/-)' : 'Quantity delta (+/-)', 'number', 'e.g. -5 or 12', true)}{input('reference', language === 'ja' ? '調整参照番号' : 'Adjustment reference') }<label className="span-two">{language === 'ja' ? '調整理由' : 'Reason'}<textarea value={form.reason ?? ''} onChange={(e) => setField('reason', e.target.value)} required minLength={3} /></label><p className="span-two muted">{language === 'ja' ? 'マイナス調整は引当済数量を下回ることはできません。' : 'Negative adjustments cannot reduce stock below quantities reserved for production.'}</p></div>;
  else if (page === 'inventory') fields = <div className="form-grid"><label className="span-two">{language === 'ja' ? '発注書に紐付け（任意）' : 'Link to purchase order (optional)'}<select value={form.purchase_order_id ?? ''} onChange={(e) => { const value = e.target.value; const po = purchaseOrders.find((x) => String(x.id) === value); setField('purchase_order_id', value); if (po) { setField('material_name', po.item_name); setField('unit', po.unit); setField('supplier_id', String(po.supplier_id)); setField('unit_cost', String(po.unit_price)); } }}><option value="">{language === 'ja' ? '手動入庫（発注書なし）' : 'Manual receipt (no purchase order)'}</option>{purchaseOrders.map((po) => <option key={po.id} value={po.id}>{po.po_number} · {po.item_name} · {po.remaining_quantity ?? po.quantity} {po.unit} {language === 'ja' ? '残' : 'remaining'}</option>)}</select></label>{input('material_name', tr('material'))}{input('lot_number', tr('lotNumber'))}{input('quantity', tr('quantity'), 'number', '', true, '0.001')}{input('unit', tr('unit'), 'text', 'kg')}{input('unit_cost', language === 'ja' ? '単価 (JPY)' : 'Unit cost (JPY)', 'number', '0', false, '0')}{select('supplier_id', tr('suppliers'), suppliers.map((x) => ({ value: String(x.id), label: x.name })), false)}{input('reference', language === 'ja' ? '入庫参照番号' : 'Receipt reference')}</div>;
  if (page === 'quality' && mode === 'qualityTemplate') fields = <div className="form-grid">{input('code', language === 'ja' ? 'テンプレートコード' : 'Template code')}{input('name', language === 'ja' ? 'テンプレート名' : 'Template name')}{select('process_type', language === 'ja' ? '検査工程' : 'Inspection stage', [{ value: 'RECEIVING', label: language === 'ja' ? '受入検査' : 'Receiving' }, { value: 'IN_PROCESS', label: language === 'ja' ? '工程内検査' : 'In-process' }, { value: 'FINAL', label: language === 'ja' ? '最終検査' : 'Final' }])}<label className="span-two">{language === 'ja' ? '検査基準 (JSON)' : 'Inspection criteria (JSON)'}<textarea rows={8} value={form.criteria_json ?? '[{"key":"dimension","label":"Dimensional tolerance","kind":"NUMERIC","minimum":9.95,"maximum":10.05,"required":true},{"key":"surface","label":"Surface finish","kind":"PASS_FAIL","required":true}]'} onChange={(e) => setField('criteria_json', e.target.value)} required /></label><p className="span-two muted">{language === 'ja' ? 'PASS_FAIL、NUMERIC、TEXT の基準を定義できます。数値基準の範囲外は自動的に不合格になります。' : 'Supported criterion kinds: PASS_FAIL, NUMERIC and TEXT. Numeric values outside the configured limits automatically fail the inspection.'}</p></div>;
  else if (page === 'quality') {
    const selectedTemplate = (data?.templates || []).find((item: Row) => String(item.id) === String(form.template_id));
    fields = <div className="form-grid">{input('inspection_number', language === 'ja' ? '検査番号' : 'Inspection number')}{input('product_name', tr('product'))}{select('batch_id', language === 'ja' ? '材料ロット（任意）' : 'Material batch (optional)', (data?.batches || []).map((x: Row) => ({ value: String(x.id), label: `${x.lot_number} · ${x.material_name}` })), false)}<label>{language === 'ja' ? '完成品バッチ（任意）' : 'Finished-product batch (optional)'}<select value={form.finished_product_batch_id ?? ''} onChange={(e) => { const selected = (data?.finishedBatches || []).find((batch: Row) => String(batch.id) === e.target.value); setField('finished_product_batch_id', e.target.value); if (selected) setField('product_name', selected.product_name); }}><option value="">—</option>{(data?.finishedBatches || []).map((batch: Row) => <option key={batch.id} value={batch.id}>{batch.batch_number} · {batch.product_name}</option>)}</select></label><label>{language === 'ja' ? '完成品シリアル（任意）' : 'Finished-product serial (optional)'}<select value={form.finished_product_serial_id ?? ''} onChange={(e) => { const selected = (data?.serials || []).find((serial: Row) => String(serial.id) === e.target.value); setField('finished_product_serial_id', e.target.value); if (selected) setField('product_name', selected.product_name); }}><option value="">—</option>{(data?.serials || []).map((serial: Row) => <option key={serial.id} value={serial.id}>{serial.serial_number} · {serial.product_name}</option>)}</select></label>{select('template_id', language === 'ja' ? '検査テンプレート（任意）' : 'Quality template (optional)', (data?.templates || []).map((x: Row) => ({ value: String(x.id), label: `${x.code} · ${x.name}` })), false)}{select('result', tr('result'), [{ value: 'PASS', label: tr('pass') }, { value: 'FAIL', label: tr('fail') }])}{input('defect_count', tr('defects'), 'number', '0', false, '0')}{input('sample_size', tr('sampleSize'), 'number', '1', true, '1')}
      {selectedTemplate && <div className="span-two criteria-editor"><strong>{language === 'ja' ? '検査基準の結果' : 'Criterion results'}</strong>{selectedTemplate.criteria.map((criterion: Row) => <label key={criterion.key}>{criterion.label}{criterion.kind === 'PASS_FAIL' ? <select required value={(form.criteria_results || {})[criterion.key] || ''} onChange={(e) => setField('criteria_results', { ...(form.criteria_results || {}), [criterion.key]: e.target.value })}><option value="">—</option><option value="PASS">{tr('pass')}</option><option value="FAIL">{tr('fail')}</option></select> : <input required={criterion.required !== false} type={criterion.kind === 'NUMERIC' ? 'number' : 'text'} min={criterion.minimum} max={criterion.maximum} value={(form.criteria_results || {})[criterion.key] ?? ''} onChange={(e) => setField('criteria_results', { ...(form.criteria_results || {}), [criterion.key]: e.target.value })} />}</label>)}</div>}
      <label className="span-two">{tr('notes')}<textarea value={form.notes ?? ''} onChange={(e) => setField('notes', e.target.value)} /></label><label className="span-two">{tr('correctiveAction')}<textarea value={form.corrective_action ?? ''} onChange={(e) => setField('corrective_action', e.target.value)} placeholder={language === 'ja' ? '不合格の場合は封じ込め処置を入力' : 'Required when result is FAIL; recorded as the containment action'} /></label></div>;
  }
  if (page === 'maintenance' && mode === 'equipment') fields = <div className="form-grid">{input('code', tr('code'))}{input('name', tr('equipmentName'))}{input('location', language === 'ja' ? '設置場所' : 'Location', 'text', '', false)}{input('next_maintenance', tr('dueDate'), 'date', '', false)}</div>;
  else if (page === 'maintenance') fields = <div className="form-grid">{select('equipment_id', tr('equipment'), (data?.equipment || []).map((x: Row) => ({ value: String(x.id), label: `${x.code} · ${x.name}` })))}{input('title', tr('task'))}{input('due_date', tr('dueDate'), 'date', '', false)}{select('maintenance_type', language === 'ja' ? '保全区分' : 'Maintenance type', [{ value: 'PREVENTIVE', label: language === 'ja' ? '予防保全' : 'Preventive' }, { value: 'UNPLANNED', label: language === 'ja' ? '突発保全' : 'Unplanned' }])}<label className="span-two">{tr('notes')}<textarea value={form.notes ?? ''} onChange={(e) => setField('notes', e.target.value)} /></label></div>;
  if (page === 'users') fields = <div className="form-grid">{input('full_name', tr('name'))}{input('email', tr('email'), 'email')}{select('role', tr('role'), (isSupplier ? ['SUPPLIER_USER'] : ['ORG_ADMIN', 'PRODUCTION_MANAGER', 'WAREHOUSE_MANAGER', 'QUALITY_INSPECTOR', 'MAINTENANCE_MANAGER', 'OPERATOR']).map((x) => ({ value: x, label: humanStatus(language, x) })))}{select('language', tr('language'), [{ value: 'ja', label: '日本語' }, { value: 'en', label: 'English' }])}<p className="span-two muted">{language === 'ja' ? '招待リンクがメールで送信されます。ローカル開発では生成リンクが画面に表示されます。' : 'An invitation link is emailed to the user. In local development, the generated link appears after creation.'}</p></div>;
  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}><section className="modal-card"><div className="modal-header"><div><span className="eyebrow">FACTORYLINK WORKSPACE</span><h2>{editing ? (editTitles[page] || tr('editTitle')) : (titles[page] || tr('createNew'))}</h2></div><button className="icon-button" onClick={onClose}><X size={19} /></button></div><form onSubmit={onSubmit}><div className="modal-body">{fields}</div><div className="modal-footer"><button type="button" className="subtle-button" onClick={onClose}>{tr('cancel')}</button><button className="primary-button" disabled={loading}>{loading ? tr('loading') : (editing ? tr('saveChanges') : tr('save'))}<ChevronRight size={15} /></button></div></form></section></div>;
}

export default App;
