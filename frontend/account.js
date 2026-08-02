/* ===========================================================================
   XTEMPLS — Личный кабинет (frontend logic)
   Подключается на register / login / verify-email / account страницах.
   Токен хранится в localStorage под ключом 'xtempls_token'.
   =========================================================================== */

const API = '/api';
const TOKEN_KEY = 'xtempls_token';
const tg = window.Telegram?.WebApp;

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
// Реферальный код из URL → скрытое поле
(() => {
  const refInput = document.getElementById('refCode');
  if (!refInput) return;
  const ref = new URLSearchParams(location.search).get('ref');
  if (ref) refInput.value = ref;
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
    };
    btn.disabled = true; btn.textContent = 'Регистрируем…';
    try {
      const res = await fetch(`${API}/account/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { showToast(data.detail || 'Ошибка регистрации'); return; }
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
  setupReferral();
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
function setupTabs() {
  const tabs = document.querySelectorAll('.account-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.account-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.account-section').forEach(s => s.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
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
  return `
    <div class="order-card">
      <div class="order-card-head">
        <span class="order-num">№${o.id}</span>
        <span class="order-status-badge status-${o.status}">${STATUS_LABELS[o.status] || o.status}</span>
      </div>
      <div class="order-date">${new Date(o.created_at).toLocaleString('ru-RU')}</div>
      <div class="order-items">${itemsHtml}</div>
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
    if (!data.length) {
      list.innerHTML = '<div class="state-box"><div class="state-icon">❤️</div><div class="state-title">Избранного нет</div><div class="state-sub">Добавляйте товары в избранное в каталоге</div></div>';
      return;
    }
    list.innerHTML = data.map(favCard).join('');
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
async function setupReferral() {
  const refLink = document.getElementById('refLink');
  if (!refLink) return;
  try {
    const res = await apiFetch('/account/referral');
    const data = await res.json();
    refLink.value = data.referral_link;
    document.getElementById('refCode').textContent = data.referral_code;
    document.getElementById('invitedCount').textContent = data.invited_count;
  } catch (e) {}
  document.getElementById('copyRefBtn').addEventListener('click', () => {
    refLink.select();
    navigator.clipboard?.writeText(refLink.value).then(
      () => showToast('Ссылка скопирована'),
      () => { document.execCommand('copy'); showToast('Ссылка скопирована'); }
    );
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
  try {
    const res = await apiFetch('/account/notifications');
    const data = await res.json();
    document.getElementById('notifOrders').checked = !!data.order_updates;
    document.getElementById('notifPromo').checked = !!data.promo;
  } catch (e) {}
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/account/notifications', {
        method: 'PUT',
        body: JSON.stringify({
          order_updates: document.getElementById('notifOrders').checked,
          promo: document.getElementById('notifPromo').checked,
        }),
      });
      if (res.ok) showToast('Настройки сохранены'); else showToast('Ошибка');
    } catch (err) { showToast('Ошибка соединения'); }
  });
}

initAccount();
