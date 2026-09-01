/* ===========================================================================
   XTEMPLS — Личный кабинет (frontend logic)
   Подключается на register / login / verify-email / account страницах.
   Токен хранится в localStorage под ключом 'xtempls_token'.
   =========================================================================== */

const API = '/api';
const TOKEN_KEY = 'xtempls_token';
const tg = window.Telegram?.WebApp;

fetch(`${API}/config`).then(r => r.ok ? r.json() : null).then(data => {
  const id = data && data.metrika_counter_id;
  if (!id || window.__xtemplsYm) return;
  window.__xtemplsYm = String(id).replace(/\D/g, '');
  if (!window.__xtemplsYm) return;
  (function (m, e, t, r, i, k, a) {
    m[i] = m[i] || function () { (m[i].a = m[i].a || []).push(arguments); };
    m[i].l = 1 * new Date();
    k = e.createElement(t); a = e.getElementsByTagName(t)[0];
    k.async = 1; k.src = r; a.parentNode.insertBefore(k, a);
  })(window, document, 'script', 'https://mc.yandex.ru/metrika/tag.js', 'ym');
  window.ym(Number(window.__xtemplsYm), 'init', {
    clickmap: true, trackLinks: true, accurateTrackBounce: true, webvisor: false,
  });
}).catch(() => {});

// ─── Хелперы ───────────────────────────────────────────────────────────────

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

/** fetch с авто-вставкой Authorization. При 401 — выкидывает на логин. */
async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (res.status === 401 && !path.startsWith('/account/login')) {
    clearToken();
    location.href = '/login.html';
    throw new Error('Не авторизован');
  }
  return res;
}

function showToast(msg, duration = 2800) {
  const t = document.getElementById('toast');
  if (!t) { alert(msg); return; }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.remove('show'), duration);
}

function fmtPrice(n) {
  return Number(n || 0).toLocaleString('ru-RU') + ' ₽';
}

const STATUS_LABELS = {
  new: 'Принят',
  in_progress: 'В работе',
  done: 'Выполнен',
  cancelled: 'Отменён',
};
const PAYMENT_LABELS = {
  pending: 'Ожидает оплаты',
  paid: 'Оплачен',
  failed: 'Ошибка оплаты',
};

// ─── Инициализация Telegram WebApp + кнопка «Назад» ────────────────────────
if (tg) {
  tg.ready();
  tg.expand();
  document.documentElement.style.setProperty('--tg-bg', tg.backgroundColor || '#0a0a0a');
}
const backBtn = document.getElementById('backBtn');
if (backBtn) {
  backBtn.addEventListener('click', () => {
    if (window.history.length > 1) window.history.back();
    else window.location.href = '/';
  });
  if (tg?.BackButton) {
    tg.BackButton.show();
    tg.BackButton.onClick(() => backBtn.click());
  }
}

// Автозаполнение имени из Telegram на странице регистрации
const nameInput = document.getElementById('name');
if (nameInput && tg?.initDataUnsafe?.user) {
  const u = tg.initDataUnsafe.user;
  nameInput.value = [u.first_name, u.last_name].filter(Boolean).join(' ') || nameInput.value;
}
// Реферальный код из URL / localStorage / Telegram start_param → скрытое поле
(() => {
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get('ref') || params.get('startapp');
  const fromTg = window.Telegram?.WebApp?.initDataUnsafe?.start_param;
  const stored = (() => { try { return localStorage.getItem('xtempls_ref'); } catch (e) { return null; } })();
  const ref = (fromUrl || fromTg || stored || '').toString().trim().toUpperCase();
  if (ref) {
    try { localStorage.setItem('xtempls_ref', ref); } catch (e) {}
  }
  const refInput = document.getElementById('refCode');
  if (refInput && refInput.tagName === 'INPUT' && ref) refInput.value = ref;
  const hint = document.getElementById('refHint');
  if (hint && ref) {
    hint.hidden = false;
    hint.textContent = `Вас пригласили по коду ${ref}`;
  }
})();

// Подсказка на странице входа или регистрации, если пользователь пришёл из оформления заказа:
// объясняем, зачем нужна авторизация и что корзина и введённые данные сохранены.
(() => {
  const sub = document.querySelector('.auth-subtitle');
  const loginFormEl = document.getElementById('loginForm');
  const registerFormEl = document.getElementById('registerForm');
  if (!sub || (!loginFormEl && !registerFormEl)) return;
  let intent = null;
  try { intent = JSON.parse(localStorage.getItem('xtempls_checkout_intent') || 'null'); } catch (e) {}
  // Текст про «корзина сохранится» показываем ТОЛЬКО при реальном переходе из
  // оформления заказа (from_checkout=true). При простом клике на «Личный кабинет»
  // из меню intent либо отсутствует, либо не имеет флага — тогда показываем
  // стандартный подзаголовок страницы входа/регистрации.
  const fresh = intent && intent.from_checkout === true && intent.ts
    && (Date.now() - intent.ts) < 24 * 3600 * 1000;
  if (fresh) {
    if (loginFormEl) {
      sub.textContent = 'Войдите, чтобы завершить оформление заказа — ваша корзина и данные доставки сохранены.';
    } else if (registerFormEl) {
      sub.textContent = 'Зарегистрируйтесь, чтобы завершить оформление заказа — ваша корзина и данные доставки сохранены.';
      const nameIn = document.getElementById('name');
      const phoneIn = document.getElementById('phone');
      if (nameIn && intent.name) nameIn.value = intent.name;
      if (phoneIn && intent.phone) phoneIn.value = intent.phone;
    }
  }
})();

// ─── Регистрация ────────────────────────────────────────────────────────────
const registerForm = document.getElementById('registerForm');
if (registerForm) {
  registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('submitBtn');
    const body = {
      email: document.getElementById('email').value.trim(),
      password: document.getElementById('password').value,
      name: document.getElementById('name').value.trim() || undefined,
      phone: document.getElementById('phone').value.trim() || undefined,
      ref_code: document.getElementById('refCode').value || undefined,
      tg_init_data: window.Telegram?.WebApp?.initData || undefined,
    };
    btn.disabled = true; btn.textContent = 'Регистрируем…';
    try {
      const res = await fetch(`${API}/account/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { showToast(data.detail || 'Ошибка регистрации'); return; }
      try { localStorage.removeItem('xtempls_ref'); } catch (e) {}
      showToast('Готово! Проверьте почту для подтверждения.');
      setTimeout(() => location.href = '/login.html', 1500);
    } catch (err) {
      showToast('Не удалось связаться с сервером');
    } finally {
      btn.disabled = false; btn.textContent = 'Зарегистрироваться';
    }
  });
}

// ─── Вход ──────────────────────────────────────────────────────────────────
const loginForm = document.getElementById('loginForm');
if (loginForm) {
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('submitBtn');
    const body = {
      email: document.getElementById('email').value.trim(),
      password: document.getElementById('password').value,
    };
    btn.disabled = true; btn.textContent = 'Входим…';
    try {
      const res = await fetch(`${API}/account/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        // 403 «не подтверждён» — показываем дольше, это важная инструкция.
        showToast(data.detail || 'Неверный email или пароль', res.status === 403 ? 5000 : 2800);
        return;
      }
      setToken(data.access_token);
      // Если пользователь пришёл к входу из оформления заказа — возвращаем его
      // на ту страницу, откуда он пришёл, с параметром ?checkout=1.
      const raw = localStorage.getItem('xtempls_checkout_intent');
      if (raw) {
        try {
          const intent = JSON.parse(raw);
          const fresh = intent && intent.ts && (Date.now() - intent.ts) < 24 * 3600 * 1000;
          if (fresh) {
            const returnUrl = intent.return_url || '/catalog.html';
            const sep = returnUrl.includes('?') ? '&' : '?';
            location.href = `${returnUrl}${sep}checkout=1`;
            return;
          } else {
            localStorage.removeItem('xtempls_checkout_intent');
          }
        } catch (e) {
          localStorage.removeItem('xtempls_checkout_intent');
        }
      }
      location.href = '/account.html';
    } catch (err) {
      showToast('Не удалось связаться с сервером');
    } finally {
      btn.disabled = false; btn.textContent = 'Войти';
    }
  });
}

// ─── Подтверждение email (verify-email.html) ────────────────────────────────
async function runVerifyEmail() {
  if (!document.getElementById('statusBox')) return;
  const token = new URLSearchParams(location.search).get('token');
  const titleEl = document.getElementById('statusTitle');
  const textEl = document.getElementById('statusText');
  const iconEl = document.getElementById('statusIcon');
  const actionsEl = document.getElementById('statusActions');

  if (!token) {
    iconEl.textContent = '⚠️';
    titleEl.textContent = 'Ссылка недействительна';
    textEl.textContent = 'В ссылке отсутствует токен подтверждения.';
    return;
  }
  try {
    const res = await fetch(`${API}/account/verify-email`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      iconEl.textContent = '✅';
      titleEl.textContent = 'Email подтверждён!';
      textEl.textContent = 'Теперь вы можете войти в личный кабинет.';
      actionsEl.style.display = 'block';
    } else {
      iconEl.textContent = '❌';
      titleEl.textContent = 'Не удалось подтвердить';
      textEl.textContent = data.detail || 'Ссылка недействительна или устарела.';
    }
  } catch (err) {
    iconEl.textContent = '❌';
    titleEl.textContent = 'Ошибка соединения';
    textEl.textContent = 'Попробуйте позже.';
  }
}
runVerifyEmail();

// ─── Личный кабинет (account.html) ─────────────────────────────────────────
// Этот блок исполняется только если на странице есть шапка профиля.
const accountHeader = document.getElementById('accountHeader');

async function initAccount() {
  if (!accountHeader) return;
  if (!getToken()) { location.href = '/login.html'; return; }

  let me = null;
  try {
    const res = await apiFetch('/account/me');
    if (!res.ok) { clearToken(); location.href = '/login.html'; return; }
    me = await res.json();
  } catch (e) { return; }

  renderHeader(me);
  loadOverview();
  setupTabs();
  setupProfile(me);
  setupPassword();
  setupAddresses();
  setupFavorites();
  setupReferral(me);
  setupBonuses();
  setupNotifications();
}

function renderHeader(me) {
  document.getElementById('userName').textContent = me.name || me.email;
  document.getElementById('userEmail').textContent = me.email;
  document.getElementById('avatar').textContent = (me.name || me.email)[0].toUpperCase();
  const bonusChip = document.getElementById('bonusChip');
  if (Number(me.bonus_balance) > 0) {
    bonusChip.style.display = '';
    document.getElementById('bonusAmount').textContent = me.bonus_balance;
  }
  const vChip = document.getElementById('verifyChip');
  if (me.is_verified) {
    vChip.textContent = '✓ Подтверждён';
    vChip.classList.add('verified');
  } else {
    vChip.textContent = '⚠ Не подтверждён';
  }
}

// Выход
const logoutBtn = document.getElementById('logoutBtn');
if (logoutBtn) logoutBtn.addEventListener('click', () => {
  clearToken();
  location.href = '/login.html';
});

// ─── Табы ───────────────────────────────────────────────────────────────────
// Ленивая загрузка данных вкладки при первом открытии (чтобы не дёргать все
// API разом при входе). Ключ — data-tab, значение — функция загрузки.
const _tabLoaders = {
  orders: loadOrders,
  favorites: loadFavorites,
  referral: setupReferral,
  bonuses: setupBonuses,
  notifications: setupNotifications,
  addresses: loadAddresses,
};
const _tabLoaded = new Set();

function setupTabs() {
  const tabs = document.querySelectorAll('.account-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.account-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.account-section').forEach(s => s.classList.remove('active'));
      tab.classList.add('active');
      const name = tab.dataset.tab;
      document.getElementById('tab-' + name).classList.add('active');
      // Подгружаем данные вкладки при первом открытии.
      if (_tabLoaders[name] && !_tabLoaded.has(name)) {
        _tabLoaded.add(name);
        _tabLoaders[name]();
      }
    });
  });
}

// ─── Обзор ─────────────────────────────────────────────────────────────────
async function loadOverview() {
  const box = document.getElementById('overviewStats');
  if (!box) return;
  box.innerHTML = '<div class="state-box"><div class="state-sub">Загрузка…</div></div>';
  try {
    const [ordersRes, bonusRes] = await Promise.all([
      apiFetch('/account/orders?per_page=1'),
      apiFetch('/account/bonuses'),
    ]);
    const orders = await ordersRes.json();
    const bonus = await bonusRes.json();
    box.innerHTML = `
      <div class="stat-card"><div class="stat-num">${orders.total}</div><div class="stat-label">заказов</div></div>
      <div class="stat-card"><div class="stat-num">${bonus.balance || 0}</div><div class="stat-label">бонусов, ₽</div></div>
    `;
  } catch (e) {
    box.innerHTML = '<div class="state-box"><div class="state-sub">Не удалось загрузить</div></div>';
  }
}

// ─── Заказы ────────────────────────────────────────────────────────────────
async function loadOrders() {
  const list = document.getElementById('ordersList');
  if (!list) return;
  list.innerHTML = '<div class="state-box"><div class="state-sub">Загрузка…</div></div>';
  try {
    const res = await apiFetch('/account/orders?per_page=50');
    const data = await res.json();
    if (!data.items.length) {
      list.innerHTML = '<div class="state-box"><div class="state-icon">📦</div><div class="state-title">Заказов пока нет</div><div class="state-sub">Ваши покупки появятся здесь</div></div>';
      return;
    }
    list.innerHTML = data.items.map(orderCard).join('');
  } catch (e) {
    list.innerHTML = '<div class="state-box"><div class="state-sub">Ошибка загрузки</div></div>';
  }
}

function orderCard(o) {
  const total = o.items.reduce((s, it) => s + Number(it.product_price) * it.quantity, 0);
  const itemsHtml = o.items.map(it =>
    `<div class="order-item-line">${escapeHtml(it.product_name)}${it.size ? ' · ' + escapeHtml(it.size) : ''} ×${it.quantity} — ${fmtPrice(it.product_price * it.quantity)}</div>`
  ).join('');

  // Блок доставки/контактов — показываем, если есть хоть что-то.
  const meta = [];
  if (o.delivery_address) meta.push(`<div class="order-meta-line">📦 ${escapeHtml(o.delivery_address)}</div>`);
  const contactParts = [];
  if (o.customer_phone) contactParts.push(`📞 ${escapeHtml(o.customer_phone)}`);
  if (o.customer_telegram) contactParts.push(`💬 @${escapeHtml(String(o.customer_telegram).replace('@', ''))}`);
  if (contactParts.length) meta.push(`<div class="order-meta-line">${contactParts.join(' &nbsp; ')}</div>`);
  if (o.comment) meta.push(`<div class="order-meta-line">📝 ${escapeHtml(o.comment)}</div>`);
  const metaHtml = meta.length ? `<div class="order-meta">${meta.join('')}</div>` : '';

  return `
    <div class="order-card">
      <div class="order-card-head">
        <span class="order-num">№${o.id}</span>
        <span class="order-status-badge status-${o.status}">${STATUS_LABELS[o.status] || o.status}</span>
      </div>
      <div class="order-date">${new Date(o.created_at).toLocaleString('ru-RU')}</div>
      <div class="order-items">${itemsHtml}</div>
      ${metaHtml}
      <div class="order-card-foot">
        <span class="order-pay status-pay-${o.payment_status}">${PAYMENT_LABELS[o.payment_status] || o.payment_status}</span>
        <span class="order-total">${fmtPrice(total)}</span>
      </div>
    </div>`;
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

// ─── Профиль ───────────────────────────────────────────────────────────────
function setupProfile(me) {
  const nameEl = document.getElementById('pName');
  const phoneEl = document.getElementById('pPhone');
  const emailEl = document.getElementById('pEmail');
  if (!nameEl) return;
  nameEl.value = me.name || '';
  phoneEl.value = me.phone || '';
  emailEl.value = me.email;

  document.getElementById('profileForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/account/me', {
        method: 'PUT',
        body: JSON.stringify({ name: nameEl.value.trim() || null, phone: phoneEl.value.trim() || null }),
      });
      const data = await res.json();
      if (!res.ok) { showToast(data.detail || 'Ошибка'); return; }
      renderHeader(data);
      showToast('Профиль сохранён');
    } catch (err) { showToast('Ошибка соединения'); }
  });
}

function setupPassword() {
  const form = document.getElementById('passwordForm');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const oldP = document.getElementById('oldPass').value;
    const newP = document.getElementById('newPass').value;
    if (newP.length < 6) { showToast('Минимум 6 символов'); return; }
    try {
      const res = await apiFetch('/account/change-password', {
        method: 'POST',
        body: JSON.stringify({ old_password: oldP, new_password: newP }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { showToast(data.detail || 'Ошибка'); return; }
      form.reset();
      showToast('Пароль изменён');
    } catch (err) { showToast('Ошибка соединения'); }
  });
}

// ─── Адреса ────────────────────────────────────────────────────────────────
function setupAddresses() {
  const addBtn = document.getElementById('addAddrBtn');
  if (!addBtn) return;
  loadAddresses();
  addBtn.addEventListener('click', () => openAddrForm());
  document.getElementById('addrCancelBtn').addEventListener('click', closeAddrForm);
  document.getElementById('addrForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('addrId').value;
    const body = {
      label: val('addrLabel'), recipient: val('addrRecipient'), phone: val('addrPhone'),
      city: val('addrCity'), street: val('addrStreet'),
      house: val('addrHouse'), apt: val('addrApt'), zip: val('addrZip'),
      is_default: document.getElementById('addrDefault').checked,
    };
    try {
      const res = await apiFetch('/account/addresses' + (id ? `/${id}` : ''), {
        method: id ? 'PUT' : 'POST',
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { showToast(data.detail || 'Ошибка'); return; }
      closeAddrForm();
      loadAddresses();
      showToast('Адрес сохранён');
    } catch (err) { showToast('Ошибка соединения'); }
  });
}

function val(id) { const v = document.getElementById(id).value.trim(); return v || null; }

async function loadAddresses() {
  const list = document.getElementById('addressesList');
  list.innerHTML = '<div class="state-box"><div class="state-sub">Загрузка…</div></div>';
  try {
    const res = await apiFetch('/account/addresses');
    const data = await res.json();
    if (!data.length) {
      list.innerHTML = '<div class="state-box"><div class="state-icon">📍</div><div class="state-title">Адресов нет</div><div class="state-sub">Добавьте адрес для быстрого оформления</div></div>';
      return;
    }
    list.innerHTML = data.map(addrCard).join('');
    list.querySelectorAll('[data-addr-id]').forEach(el => {
      const id = el.dataset.addrId;
      el.querySelector('.addr-edit').addEventListener('click', () => editAddr(id));
      el.querySelector('.addr-del').addEventListener('click', () => delAddr(id));
    });
  } catch (e) { list.innerHTML = '<div class="state-box"><div class="state-sub">Ошибка</div></div>'; }
}

function addrCard(a) {
  const parts = [a.city, a.street, a.house, a.apt ? 'кв. ' + a.apt : null].filter(Boolean).join(', ');
  return `
    <div class="addr-card" data-addr-id="${a.id}">
      <div class="addr-card-head">
        <span class="addr-label">${escapeHtml(a.label || 'Адрес')}${a.is_default ? ' · по умолчанию' : ''}</span>
        <span class="addr-actions">
          <button class="addr-edit">✏️</button>
          <button class="addr-del">🗑</button>
        </span>
      </div>
      <div class="addr-line">${escapeHtml(parts || '—')}</div>
      ${a.recipient || a.phone ? `<div class="addr-line">${[a.recipient, a.phone].filter(Boolean).map(escapeHtml).join(' · ')}</div>` : ''}
    </div>`;
}

let _addressesCache = [];
async function openAddrForm(prefill) {
  document.getElementById('addrFormWrap').style.display = '';
  if (!prefill) document.getElementById('addrForm').reset();
  document.getElementById('addrId').value = prefill?.id || '';
}
function closeAddrForm() {
  document.getElementById('addrFormWrap').style.display = 'none';
  document.getElementById('addrForm').reset();
}
async function editAddr(id) {
  const res = await apiFetch('/account/addresses');
  const data = await res.json();
  const a = data.find(x => x.id == id);
  if (!a) return;
  document.getElementById('addrId').value = a.id;
  document.getElementById('addrLabel').value = a.label || '';
  document.getElementById('addrRecipient').value = a.recipient || '';
  document.getElementById('addrPhone').value = a.phone || '';
  document.getElementById('addrCity').value = a.city || '';
  document.getElementById('addrStreet').value = a.street || '';
  document.getElementById('addrHouse').value = a.house || '';
  document.getElementById('addrApt').value = a.apt || '';
  document.getElementById('addrZip').value = a.zip || '';
  document.getElementById('addrDefault').checked = !!a.is_default;
  openAddrForm(a);
}
async function delAddr(id) {
  if (!confirm('Удалить адрес?')) return;
  await apiFetch('/account/addresses/' + id, { method: 'DELETE' });
  loadAddresses();
}

// ─── Избранное ─────────────────────────────────────────────────────────────
async function setupFavorites() {
  if (!document.getElementById('favoritesList')) return;
  loadFavorites();
}
async function loadFavorites() {
  const list = document.getElementById('favoritesList');
  list.innerHTML = '<div class="state-box"><div class="state-sub">Загрузка…</div></div>';
  try {
    const res = await apiFetch('/account/favorites');
    const data = await res.json();
    const html = (data || []).map(favCard).filter(Boolean).join('');
    if (!html) {
      list.innerHTML = '<div class="state-box"><div class="state-icon">❤️</div><div class="state-title">Избранного нет</div><div class="state-sub">Добавляйте товары в избранное в каталоге</div></div>';
      return;
    }
    list.innerHTML = html;
    list.querySelectorAll('[data-fav-pid]').forEach(el => {
      el.querySelector('.fav-del').addEventListener('click', async () => {
        await apiFetch('/account/favorites/' + el.dataset.favPid, { method: 'DELETE' });
        loadFavorites();
      });
    });
  } catch (e) { list.innerHTML = '<div class="state-box"><div class="state-sub">Ошибка</div></div>'; }
}
function favCard(f) {
  const p = f.product;
  if (!p) return '';
  return `
    <a class="fav-card" data-fav-pid="${p.id}" href="/product.html?id=${p.id}">
      <div class="fav-img" style="${p.primary_image ? `background-image:url('${p.primary_image}')` : ''}">${p.primary_image ? '' : '👕'}</div>
      <div class="fav-info">
        <div class="fav-name">${escapeHtml(p.name)}</div>
        <div class="fav-price">${fmtPrice(p.price)}</div>
      </div>
      <button class="fav-del" onclick="event.preventDefault(); event.stopPropagation();">🗑</button>
    </a>`;
}

// ─── Рефералка ─────────────────────────────────────────────────────────────
function copyText(text, okMsg) {
  const value = (text || '').trim();
  if (!value || value === '—') { showToast('Код ещё загружается, подождите секунду'); return; }
  const done = () => showToast(okMsg);
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(value).then(done, () => {
      try { document.execCommand('copy'); done(); } catch (e) { showToast(value); }
    });
  } else {
    showToast(value);
  }
}

function paintReferral(data) {
  const origin = window.location.origin || '';
  const code = (data.promo_code || data.referral_code || '').toString().trim().toUpperCase();
  const siteLink = data.referral_link || (code ? `${origin}/register.html?ref=${code}` : '');
  const botLink = data.bot_link || (code ? `https://t.me/xtempls_bot?start=${code}` : '');

  const codeEl = document.getElementById('refPromoCode');
  if (codeEl) codeEl.textContent = code || '—';
  const siteEl = document.getElementById('refSiteLink');
  if (siteEl) siteEl.value = siteLink;
  const botEl = document.getElementById('refBotLink');
  if (botEl) botEl.value = botLink;
  const invited = document.getElementById('invitedCount');
  if (invited) invited.textContent = data.invited_count ?? 0;
  const clicks = document.getElementById('refClicks');
  if (clicks) clicks.textContent = data.link_clicks ?? 0;
  const earned = document.getElementById('refEarned');
  if (earned) earned.textContent = fmtPrice(data.earned_total || 0);

  const rules = document.getElementById('refRules');
  if (rules) {
    if (data.program_enabled === false) {
      rules.textContent = 'Реферальная программа сейчас на паузе. Ссылку и код всё равно можно копировать — начисления включит магазин.';
    } else {
      const bits = [];
      if (data.signup_bonus_enabled !== false) {
        bits.push(`за регистрацию друга вам +${fmtPrice(data.registration_bonus)}`);
      }
      if (data.invitee_bonus_enabled) {
        bits.push(`друг тоже получает ${fmtPrice(data.invitee_bonus)}`);
      }
      if (data.purchase_cashback_enabled !== false) {
        bits.push(`с каждой его покупки по вашему коду вам ${data.purchase_cashback_percent}% на бонусы`);
      }
      if (data.buyer_discount_enabled !== false) {
        bits.push(`ему скидка ${data.discount_percent}%`);
      }
      rules.innerHTML = bits.length
        ? `Как это работает: ${bits.join('; ')}. Бонусами можно оплатить заказ в корзине.`
        : 'Делитесь ссылкой и промокодом — бонусы приходят на счёт в этом кабинете.';
    }
  }
}

async function setupReferral(me) {
  const box = document.getElementById('tab-referral');
  if (!box || box.dataset.refReady === '1') return;
  box.dataset.refReady = '1';

  const fallback = {
    referral_code: me?.referral_code || '',
    promo_code: me?.referral_code || '',
    invited_count: 0,
    earned_total: 0,
    program_enabled: true,
    signup_bonus_enabled: true,
    purchase_cashback_enabled: true,
    buyer_discount_enabled: true,
    registration_bonus: 100,
    purchase_cashback_percent: 5,
    discount_percent: 5,
  };
  paintReferral(fallback);

  try {
    const [refRes, cfgRes] = await Promise.all([
      apiFetch('/account/referral'),
      fetch(`${API}/config`).catch(() => null),
    ]);
    const data = refRes.ok ? await refRes.json() : {};
    if (cfgRes && cfgRes.ok) {
      const cfg = await cfgRes.json();
      const botName = (cfg.telegram_bot_username || '').replace(/^@/, '');
      const code = data.promo_code || data.referral_code || fallback.promo_code;
      if (botName && code && !data.bot_link) {
        data.bot_link = `https://t.me/${botName}?start=${code}`;
      }
      if (cfg.referral && typeof cfg.referral === 'object') {
        Object.assign(data, {
          program_enabled: cfg.referral.program_enabled ?? data.program_enabled,
          registration_bonus: cfg.referral.registration_bonus ?? data.registration_bonus,
          purchase_cashback_percent: cfg.referral.purchase_cashback_percent ?? data.purchase_cashback_percent,
          discount_percent: cfg.referral.discount_percent ?? data.discount_percent,
        });
      }
    }
    if (!data.promo_code && !data.referral_code) data.promo_code = fallback.promo_code;
    paintReferral(data);
    if (!refRes.ok) {
      const err = document.getElementById('refLoadError');
      if (err) { err.hidden = false; err.textContent = 'Не удалось обновить статистику, код и ссылки всё равно можно копировать.'; }
    }
  } catch (e) {
    const err = document.getElementById('refLoadError');
    if (err) { err.hidden = false; err.textContent = 'Сеть моргнула — показан ваш код из профиля.'; }
  }

  document.getElementById('copyPromoBtn')?.addEventListener('click', () => {
    copyText(document.getElementById('refPromoCode')?.textContent, 'Промокод скопирован');
  });
  document.getElementById('copyRefBtn')?.addEventListener('click', () => {
    copyText(document.getElementById('refSiteLink')?.value, 'Ссылка на сайт скопирована');
  });
  document.getElementById('copyBotBtn')?.addEventListener('click', () => {
    copyText(document.getElementById('refBotLink')?.value, 'Ссылка на бота скопирована');
  });
}

// ─── Бонусы ────────────────────────────────────────────────────────────────
async function setupBonuses() {
  const box = document.getElementById('bonusList');
  if (!box) return;
  try {
    const res = await apiFetch('/account/bonuses');
    const data = await res.json();
    document.getElementById('bonusBalance').textContent = data.balance || 0;
    if (!data.transactions.length) {
      box.innerHTML = '<div class="state-box"><div class="state-icon">🎁</div><div class="state-title">Бонусов пока нет</div><div class="state-sub">Зарабатывайте бонусы за покупки и по рефералке</div></div>';
      return;
    }
    box.innerHTML = data.transactions.map(t => `
      <div class="bonus-row">
        <div>
          <div class="bonus-reason">${escapeHtml(t.reason || 'Бонус')}</div>
          <div class="bonus-date">${new Date(t.created_at).toLocaleDateString('ru-RU')}</div>
        </div>
        <div class="bonus-amount ${t.type}">${t.type === 'accrual' ? '+' : '−'}${fmtPrice(t.amount)}</div>
      </div>`).join('');
  } catch (e) { box.innerHTML = '<div class="state-box"><div class="state-sub">Ошибка</div></div>'; }
}

// ─── Уведомления ───────────────────────────────────────────────────────────
async function setupNotifications() {
  const form = document.getElementById('notifForm');
  if (!form) return;
  const ordersEl = document.getElementById('notifOrders');
  const promoEl = document.getElementById('notifPromo');
  try {
    const res = await apiFetch('/account/notifications');
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(data.detail || 'Не удалось загрузить уведомления');
    } else {
      if (ordersEl) ordersEl.checked = !!data.order_updates;
      if (promoEl) promoEl.checked = !!data.promo;
    }
  } catch (e) {
    showToast('Ошибка загрузки уведомлений');
  }

  async function savePrefs() {
    try {
      const res = await apiFetch('/account/notifications', {
        method: 'PUT',
        body: JSON.stringify({
          order_updates: !!(ordersEl && ordersEl.checked),
          promo: !!(promoEl && promoEl.checked),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) showToast('Настройки сохранены');
      else showToast(data.detail || 'Не удалось сохранить уведомления');
    } catch (err) {
      showToast('Ошибка соединения');
    }
  }

  if (ordersEl) ordersEl.addEventListener('change', savePrefs);
  if (promoEl) promoEl.addEventListener('change', savePrefs);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await savePrefs();
  });
}

initAccount();
