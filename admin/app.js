/* ─── Admin Shared JavaScript ─── */

const API = '/api';

// ── Auth helpers ──────────────────────────────────────────────────────────────

function getToken() {
  return localStorage.getItem('admin_token');
}

function requireAuth() {
  if (!getToken()) {
    window.location.href = '/admin/';
  }
}

async function apiFetch(url, options = {}) {
  const token = getToken();
  const isFormData = options.body instanceof FormData;

  // Don't set Content-Type for FormData — the browser sets the boundary.
  const headers = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem('admin_token');
    window.location.href = '/admin/';
  }

  return res;
}

function logout() {
  if (!confirm('Выйти из панели администратора?')) return;
  localStorage.removeItem('admin_token');
  window.location.href = '/admin/';
}

async function loadAdminInfo() {
  try {
    const res = await apiFetch(`${API}/admin/me`);
    if (!res.ok) return;
    const data = await res.json();
    const loginEl = document.getElementById('adminLogin');
    const initEl = document.getElementById('adminInitial');
    if (loginEl) loginEl.textContent = data.login;
    if (initEl) initEl.textContent = data.login[0].toUpperCase();
  } catch (e) {
    console.error('Failed to load admin info', e);
  }
}

// ── Formatting ────────────────────────────────────────────────────────────────

function fmt(price) {
  return Number(price).toLocaleString('ru-RU') + ' ₽';
}

function stockBadge(status) {
  const map = {
    'in_stock':     ['badge-green', 'В наличии'],
    'out_of_stock': ['badge-red',   'Нет в наличии'],
    'preorder':     ['badge-yellow','Предзаказ'],
  };
  const [cls, label] = map[status] || ['badge-gray', status];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(msg, type = 'default', duration = 2800) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className = `toast show ${type}`;
  setTimeout(() => { t.className = `toast ${type}`; }, duration);
}
