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

// ── Modal overlay helpers ─────────────────────────────────────────────────────
// The old "click overlay to close" handlers used a bare click listener:
//
//   overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
//
// A click = mousedown + mouseup on the same element. But if the user presses
// the mouse button INSIDE the modal (e.g. to drag-select text or drag an image)
// and releases it OUTSIDE (on the overlay), the browser still fires a "click"
// on the overlay — so the modal collapsed "by itself". We track mousedown
// origin and only close when the gesture started on the overlay too.
function enableOverlayClose(overlayEl, closeFn) {
  if (!overlayEl) return;
  let mouseDownOnOverlay = false;
  overlayEl.addEventListener('mousedown', (e) => {
    mouseDownOnOverlay = (e.target === overlayEl);
  });
  overlayEl.addEventListener('click', (e) => {
    if (e.target === overlayEl && mouseDownOnOverlay) {
      mouseDownOnOverlay = false;
      closeFn();
    }
    mouseDownOnOverlay = false;
  });
}

// ── Mobile sidebar toggle ─────────────────────────────────────────────────────
// Injects a hamburger button into the topbar on mobile and toggles the sidebar.
// Without this, on phones the sidebar is off-canvas (transform: translateX(-240px))
// and there is no way to navigate between sections (Products → Dashboard, etc.).
function initMobileSidebar() {
  const topbar = document.querySelector('.topbar');
  const sidebar = document.getElementById('sidebar');
  if (!topbar || !sidebar) return;
  // Avoid double-injection.
  if (document.getElementById('mobileMenuToggle')) return;

  const btn = document.createElement('button');
  btn.id = 'mobileMenuToggle';
  btn.className = 'mobile-menu-toggle';
  btn.setAttribute('aria-label', 'Меню');
  btn.innerHTML = '<svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>';
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    sidebar.classList.toggle('open');
  });
  topbar.insertBefore(btn, topbar.firstChild);

  // Close sidebar when a nav link is tapped, or on outside click.
  sidebar.addEventListener('click', (e) => {
    if (e.target.closest('.nav-item')) sidebar.classList.remove('open');
  });
  document.addEventListener('click', (e) => {
    if (!sidebar.contains(e.target) && !btn.contains(e.target)) {
      sidebar.classList.remove('open');
    }
  });
}

document.addEventListener('DOMContentLoaded', initMobileSidebar);
