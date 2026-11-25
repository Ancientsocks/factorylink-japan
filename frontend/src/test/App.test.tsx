import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

type MockUser = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  language: 'en' | 'ja';
  organization_id: number;
  organization_name: string;
};

const factoryAdmin: MockUser = {
  id: 1,
  email: 'admin@example.jp',
  full_name: 'Factory Admin',
  role: 'ORG_ADMIN',
  language: 'en',
  organization_id: 10,
  organization_name: 'Sakura Factory',
};

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
    blob: async () => new Blob(),
  } as Response;
}

function dashboardData() {
  return {
    kpis: {
      production_orders: 8,
      completed_orders: 3,
      production_progress: 62.5,
      defect_rate: 2.4,
      inventory_value: 125000,
      low_stock_count: 1,
      delayed_orders: 2,
      open_purchase_orders: 4,
      equipment_due: 0,
    },
    production_status: [{ status: 'IN_PROGRESS', count: 5 }],
    production_orders: [],
    recent_activity: [],
    low_stock: [],
    maintenance_due: [],
  };
}

function installFetch(
  handler: (path: string, method: string, init?: RequestInit) => Response | Promise<Response>,
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(String(input), init?.method || 'GET', init),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function createDefaultFetch(user: MockUser = factoryAdmin) {
  return installFetch((path, method, init) => {
    if (path === '/api/v1/auth/login' && method === 'POST') {
      return jsonResponse({ access_token: 'access-1', refresh_token: 'refresh-1', user });
    }
    if (path === '/api/v1/auth/me') return jsonResponse(user);
    if (path === '/api/v1/dashboard') return jsonResponse(dashboardData());
    if (path === '/api/v1/notifications/unread-count') return jsonResponse({ unread_count: 0 });
    if (path === '/api/v1/auth/language' && method === 'PATCH') {
      return jsonResponse({ language: JSON.parse(String(init?.body)).language });
    }
      if (path === '/api/v1/quality/inspections' && method === 'POST') return jsonResponse({ id: 91 }, 201);
    if (path === '/api/v1/purchase-orders' && method === 'GET') return jsonResponse([]);
    if (path === '/api/v1/suppliers') {
      return jsonResponse([{ id: 7, name: 'Osaka Parts Supply' }]);
    }
    return jsonResponse({}, 404);
  });
}

async function signIn(user = factoryAdmin) {
  const languageSelect = document.querySelector('.login-language select');
  if (languageSelect) await userEvent.selectOptions(languageSelect, 'en');
  const input = {
    email: screen.getByLabelText('Email'),
    password: screen.getByLabelText('Password'),
  };
  await userEvent.clear(input.email);
  await userEvent.type(input.email, user.email);
  await userEvent.clear(input.password);
  await userEvent.type(input.password, 'Strong-Test-Password-2026!');
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

describe('FactoryLink application', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    window.history.replaceState({}, '', '/');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('authenticates, stores the session and displays live dashboard values', async () => {
    const fetchMock = createDefaultFetch();
    render(<App />);

    await signIn();

    expect(await screen.findByRole('heading', { name: 'Dashboard', level: 1 })).toBeVisible();
    expect(screen.getByText('62.5%')).toBeVisible();
    expect(screen.getByText('2.4%')).toBeVisible();
    expect(sessionStorage.getItem('factorylink.access')).toBe('access-1');
    expect(sessionStorage.getItem('factorylink.refresh')).toBe('refresh-1');
    const login = fetchMock.mock.calls.find(([path]) => path === '/api/v1/auth/login');
    expect(JSON.parse(String(login?.[1]?.body))).toEqual({
      email: factoryAdmin.email,
      password: 'Strong-Test-Password-2026!',
    });
  });

  it('shows the server authentication error without entering the application', async () => {
    installFetch((path) => path === '/api/v1/auth/login'
      ? jsonResponse({ detail: 'Incorrect email or password.' }, 401)
      : jsonResponse({}));
    render(<App />);

    await userEvent.selectOptions(document.querySelector('.login-language select') as HTMLSelectElement, 'en');
    await userEvent.type(screen.getByLabelText('Email'), 'unknown@factorylink.jp');
    await userEvent.type(screen.getByLabelText('Password'), 'Wrong-Password-2026!');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Incorrect email or password.')).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Dashboard', level: 1 })).not.toBeInTheDocument();
  });

  it('restricts supplier navigation to supplier-authorized workspaces', async () => {
    const supplierUser = { ...factoryAdmin, role: 'SUPPLIER_USER', organization_name: 'Osaka Supplier' };
    createDefaultFetch(supplierUser);
    render(<App />);

    await signIn(supplierUser);

    expect(await screen.findByRole('heading', { name: 'Supplier portal', level: 1 })).toBeVisible();
    expect(within(document.querySelector('.main-nav') as HTMLElement)
      .getByRole('button', { name: 'Purchase Orders' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Inventory' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Quality' })).not.toBeInTheDocument();
  });

  it('switches and persists language while saving the authenticated preference', async () => {
    const fetchMock = createDefaultFetch();
    render(<App />);
    await signIn();
    await screen.findByRole('heading', { name: 'Dashboard', level: 1 });

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'ja');

    expect(await screen.findByRole('heading', { name: /ダッシュボード/ })).toBeVisible();
    await waitFor(() => expect(localStorage.getItem('factorylink.language')).toBe('ja'));
    expect(document.documentElement.lang).toBe('ja');
    expect(fetchMock.mock.calls.some(([path, init]) =>
      path === '/api/v1/auth/language'
      && init?.method === 'PATCH'
      && JSON.parse(String(init.body)).language === 'ja',
    )).toBe(true);
  });

  it('validates purchase-order fields and submits numeric quantities as numbers', async () => {
    const fetchMock = createDefaultFetch();
    fetchMock.mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === '/api/v1/purchase-orders' && init?.method === 'POST') {
        return jsonResponse({ id: 51, po_number: 'PO-UNIT-1' }, 201);
      }
      return createDefaultFetchResponse(path, init, factoryAdmin);
    });
    render(<App />);
    await signIn();
    await screen.findByRole('heading', { name: 'Dashboard', level: 1 });
    await userEvent.click(screen.getByRole('button', { name: 'Purchase Orders' }));
    await screen.findByRole('heading', { name: 'Purchase Orders', level: 1 });
    await userEvent.click(screen.getByRole('button', { name: 'New purchase order' }));

    const dialog = screen.getByRole('heading', { name: 'New purchase order' }).closest('.modal-card');
    expect(dialog).not.toBeNull();
    const modal = within(dialog as HTMLElement);
    const form = dialog?.querySelector('form');
    expect(form).not.toBeNull();
    await userEvent.click(modal.getByRole('button', { name: 'Save' }));
    expect(form as HTMLFormElement).not.toBeValid();
    expect(fetchMock.mock.calls.some(([path, init]) =>
      path === '/api/v1/purchase-orders' && init?.method === 'POST',
    )).toBe(false);

    await userEvent.selectOptions(modal.getByLabelText('Suppliers'), '7');
    await userEvent.type(modal.getByLabelText('Order number'), 'PO-UNIT-1');
    await userEvent.type(modal.getByLabelText('Item'), 'Precision steel');
    const quantity = modal.getByLabelText('Quantity');
    await userEvent.type(quantity, '40');
    expect(quantity).toHaveAttribute('step', 'any');
    expect(quantity).toBeValid();
    await userEvent.type(modal.getByLabelText('Unit', { exact: true }), 'kg');
    await userEvent.click(modal.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([path, init]) =>
      path === '/api/v1/purchase-orders' && init?.method === 'POST',
    )).toBe(true));
    const createCall = fetchMock.mock.calls.find(([path, init]) =>
      path === '/api/v1/purchase-orders' && init?.method === 'POST',
    );
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      supplier_id: 7,
      po_number: 'PO-UNIT-1',
      quantity: 40,
      item_name: 'Precision steel',
      unit: 'kg',
    });
  });

  it('shows API validation errors on the form and keeps the modal open', async () => {
    const fetchMock = createDefaultFetch();
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input) === '/api/v1/purchase-orders' && init?.method === 'POST') {
        return jsonResponse({ detail: 'Order number already exists' }, 409);
      }
      return createDefaultFetchResponse(String(input), init, factoryAdmin);
    });
    render(<App />);
    await signIn();
    await screen.findByRole('heading', { name: 'Dashboard', level: 1 });
    await userEvent.click(screen.getByRole('button', { name: 'Purchase Orders' }));
    await screen.findByRole('heading', { name: 'Purchase Orders', level: 1 });
    await userEvent.click(screen.getByRole('button', { name: 'New purchase order' }));
    const dialog = screen.getByRole('heading', { name: 'New purchase order' }).closest('.modal-card');
    expect(dialog).not.toBeNull();
    const modal = within(dialog as HTMLElement);
    await userEvent.selectOptions(modal.getByLabelText('Suppliers'), '7');
    await userEvent.type(modal.getByLabelText('Order number'), 'PO-DUP');
    await userEvent.type(modal.getByLabelText('Item'), 'Steel');
    await userEvent.type(modal.getByLabelText('Quantity'), '1');
    await userEvent.type(modal.getByLabelText('Unit', { exact: true }), 'kg');
    await userEvent.click(modal.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Order number already exists')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'New purchase order' })).toBeInTheDocument();
  });

  it('creates a finished-product serial inspection with the selected batch and serial ids', async () => {
    const fetchMock = createDefaultFetch();
    fetchMock.mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === '/api/v1/quality/inspections' && init?.method === 'POST') {
        return jsonResponse({ id: 91 }, 201);
      }
      return createDefaultFetchResponse(path, init, factoryAdmin);
    });
    render(<App />);
    await signIn();
    await screen.findByRole('heading', { name: 'Dashboard', level: 1 });
    await userEvent.click(screen.getByRole('button', { name: 'Quality' }));
    await screen.findByRole('heading', { name: 'Quality', level: 1 });
    await userEvent.click(screen.getByRole('button', { name: 'New inspection' }));

    const modal = screen.getByRole('heading', { name: 'New inspection' }).closest('.modal-card');
    expect(modal).not.toBeNull();
    const form = within(modal as HTMLElement);
    await userEvent.type(form.getByLabelText('Inspection number'), 'QI-UI-FP-1');
    await userEvent.selectOptions(form.getByLabelText('Finished-product batch (optional)'), '44');
    await userEvent.selectOptions(form.getByLabelText('Finished-product serial (optional)'), '55');
    expect(form.getByLabelText('Product')).toHaveValue('Finished UI Part');
    await userEvent.selectOptions(form.getByLabelText('Result'), 'PASS');
    await userEvent.type(form.getByLabelText('Units inspected'), '1');
    await userEvent.click(form.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([path, init]) =>
      path === '/api/v1/quality/inspections' && init?.method === 'POST',
    )).toBe(true));
    const createCall = fetchMock.mock.calls.find(([path, init]) =>
      path === '/api/v1/quality/inspections' && init?.method === 'POST',
    );
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      inspection_number: 'QI-UI-FP-1',
      product_name: 'Finished UI Part',
      finished_product_batch_id: 44,
      finished_product_serial_id: 55,
      batch_id: null,
    });
  });
});

function createDefaultFetchResponse(path: string, init: RequestInit | undefined, user: MockUser): Response {
  if (path === '/api/v1/auth/login' && init?.method === 'POST') {
    return jsonResponse({ access_token: 'access-1', refresh_token: 'refresh-1', user });
  }
  if (path === '/api/v1/auth/me') return jsonResponse(user);
  if (path === '/api/v1/dashboard') return jsonResponse(dashboardData());
  if (path === '/api/v1/notifications/unread-count') return jsonResponse({ unread_count: 0 });
  if (path === '/api/v1/auth/language' && init?.method === 'PATCH') {
    return jsonResponse({ language: JSON.parse(String(init.body)).language });
  }
  if (path === '/api/v1/quality/inspections') return jsonResponse([]);
  if (path === '/api/v1/inventory/batches') return jsonResponse([]);
  if (path === '/api/v1/quality/finished-batches') return jsonResponse([{
    id: 44, batch_number: 'FPB-MO-UI-1', product_name: 'Finished UI Part', status: 'AVAILABLE',
  }]);
  if (path === '/api/v1/traceability/serials') return jsonResponse([{
    id: 55, serial_number: 'FP-MO-UI-1-00001', product_name: 'Finished UI Part', status: 'AVAILABLE',
  }]);
  if (path === '/api/v1/quality/templates' || path === '/api/v1/quality/capa') return jsonResponse([]);
  if (path === '/api/v1/purchase-orders' && init?.method !== 'POST') return jsonResponse([]);
  if (path === '/api/v1/suppliers') return jsonResponse([{ id: 7, name: 'Osaka Parts Supply' }]);
  return jsonResponse({}, 404);
}
