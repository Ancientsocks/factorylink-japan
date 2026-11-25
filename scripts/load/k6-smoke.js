import http from 'k6/http';
import { check, sleep, fail } from 'k6';

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8080').replace(/\/$/, '');
const EMAIL = __ENV.LOAD_TEST_EMAIL;
const PASSWORD = __ENV.LOAD_TEST_PASSWORD;
const ALLOW_EXTERNAL = __ENV.ALLOW_EXTERNAL === '1';

if (!EMAIL || !PASSWORD) fail('Set LOAD_TEST_EMAIL and LOAD_TEST_PASSWORD to a dedicated test account.');
if (!ALLOW_EXTERNAL && !/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(BASE_URL)) {
  fail('Load test is restricted to localhost. Set ALLOW_EXTERNAL=1 only for an authorised target.');
}

export const options = {
  scenarios: { dashboard_smoke: { executor: 'constant-vus', vus: Number(__ENV.VUS || 5), duration: __ENV.DURATION || '30s' } },
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<1000'] },
};

export function setup() {
  const response = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({ email: EMAIL, password: PASSWORD }), {
    headers: { 'Content-Type': 'application/json' }, tags: { name: 'login' },
  });
  if (!check(response, { 'test user login succeeds': (r) => r.status === 200 && !!r.json('access_token') })) {
    fail(`Login failed with HTTP ${response.status}; check the dedicated load-test account.`);
  }
  return { token: response.json('access_token') };
}

export default function (data) {
  const params = { headers: { Authorization: `Bearer ${data.token}` } };
  check(http.get(`${BASE_URL}/api/v1/dashboard`, { ...params, tags: { name: 'dashboard' } }), { 'dashboard returns 200': (r) => r.status === 200 });
  check(http.get(`${BASE_URL}/api/v1/notifications/unread-count`, { ...params, tags: { name: 'notification_unread_count' } }), { 'notification count returns 200': (r) => r.status === 200 });
  check(http.get(`${BASE_URL}/api/v1/inventory/batches`, { ...params, tags: { name: 'inventory_batches' } }), { 'inventory endpoint returns 200': (r) => r.status === 200 });
  sleep(1);
}
