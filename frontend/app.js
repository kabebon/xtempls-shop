/* ─── Mini App JavaScript ─── */

const API = '/api';
const tg = window.Telegram?.WebApp;

// Public site config (manager username, contacts) loaded from backend — no hardcoding.
let siteConfig = { manager_username: '', contact_telegram: '', metrika_counter_id: '' };

function injectMetrika(id) {
  const counter = String(id || '').replace(/\D/g, '');
  if (!counter || window.__xtemplsYm) return;
  window.__xtemplsYm = counter;
  (function (m, e, t, r, i, k, a) {
    m[i] = m[i] || function () { (m[i].a = m[i].a || []).push(arguments); };
    m[i].l = 1 * new Date();
    for (var j = 0; j < document.scripts.length; j++) {
      if (document.scripts[j].src === r) { return; }
    }
    k = e.createElement(t); a = e.getElementsByTagName(t)[0];
    k.async = 1; k.src = r; a.parentNode.insertBefore(k, a);
  })(window, document, 'script', 'https://mc.yandex.ru/metrika/tag.js', 'ym');
  window.ym(Number(counter), 'init', {
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: false,
  });
}

// Init Telegram WebApp
if (tg) {
  tg.ready();
  tg.expand();
  document.documentElement.style.setProperty('--tg-bg', tg.backgroundColor || '#0a0a0a');
}

// Реферальный код из URL / Telegram start_param — живёт до регистрации.
(function persistRef() {
  try {
    const params = new URLSearchParams(location.search);
    const fromUrl = params.get('ref') || params.get('startapp');
    const fromTg = tg?.initDataUnsafe?.start_param;
    const ref = (fromUrl || fromTg || '').toString().trim().toUpperCase();
    if (ref) {
      localStorage.setItem('xtempls_ref', ref);
      const pingKey = 'xtempls_ref_ping_' + ref;
      try {
        if (!sessionStorage.getItem(pingKey)) {
          sessionStorage.setItem(pingKey, '1');
          fetch(`${API}/ref/click`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: ref, path: location.pathname + location.search }),
          }).catch(() => {});
        }
      } catch (err) {}
    }
  } catch (e) {}
})();

window._favIds = new Set();

async function loadFavoriteIds() {
  const token = localStorage.getItem('xtempls_token');
  if (!token) return;
  try {
    const res = await fetch(`${API}/account/favorites`, {
      headers: { Authorization: 'Bearer ' + token },
    });
    if (!res.ok) return;
    const data = await res.json();
    window._favIds = new Set(
      (data || []).map(f => f.product_id || f.product?.id).filter(Boolean)
    );
  } catch (e) {}
}

window.toggleFavorite = async function(productId, btn) {
  const token = localStorage.getItem('xtempls_token');
  if (!token) {
    showToast('Войдите, чтобы добавить в избранное');
    setTimeout(() => { location.href = '/login.html'; }, 900);
    return;
  }
  const on = btn.classList.contains('is-fav');
  try {
    const res = await fetch(`${API}/account/favorites/${productId}`, {
      method: on ? 'DELETE' : 'POST',
      headers: { Authorization: 'Bearer ' + token },
    });
    if (res.status === 401) {
      showToast('Войдите, чтобы добавить в избранное');
      setTimeout(() => { location.href = '/login.html'; }, 900);
      return;
    }
    if (!res.ok && res.status !== 204) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || 'Не удалось обновить избранное');
      return;
    }
    if (on) {
      btn.classList.remove('is-fav');
      window._favIds.delete(productId);
      if (btn.dataset.label) btn.textContent = btn.dataset.labelOff || '♡ В избранное';
      showToast('Удалено из избранного');
    } else {
      btn.classList.add('is-fav');
      window._favIds.add(productId);
      if (btn.dataset.label) btn.textContent = btn.dataset.labelOn || '♥ В избранном';
      showToast('Добавлено в избранное');
    }
  } catch (e) {
    showToast('Ошибка соединения');
  }
};

function favBtnHtml(productId) {
  const on = window._favIds.has(productId);
  return `<button type="button" class="fav-heart ${on ? 'is-fav' : ''}" data-fav-id="${productId}"
    onclick="event.preventDefault(); event.stopPropagation(); toggleFavorite(${productId}, this);"
    aria-label="В избранное">♥</button>`;
}

function newBadgeHtml(p) {
  return p && p.is_featured ? '<div class="new-badge">Новинка</div>' : '';
}

// Load public config early (non-blocking; links degrade gracefully if it fails)
fetch(`${API}/config`)
  .then(r => r.ok ? r.json() : null)
  .then(data => {
    if (data) {
      siteConfig = data;
      applySiteConfig();
    }
  })
  .catch(() => {});

// Fill footer contact elements from config (elements are optional per page).
function applySiteConfig() {
  const tgEl = document.getElementById('footerTelegram');
  if (tgEl && siteConfig.contact_telegram) {
    tgEl.textContent = `@${siteConfig.contact_telegram.replace(/^@/, '')}`;
  }
  injectMetrika(siteConfig.metrika_counter_id);
}

// ── Cart State (localStorage) ─────────────────────────────────────────────────

let cart = JSON.parse(localStorage.getItem('xtempls_cart') || '[]');

// Re-read cart from storage. Used before rendering so a stale in-memory copy
// (e.g. after the page's framework JS reset state) never shows an empty cart.
function reloadCart() {
  try {
    cart = JSON.parse(localStorage.getItem('xtempls_cart') || '[]');
  } catch (e) {
    cart = [];
  }
}

function saveCart() {
  localStorage.setItem('xtempls_cart', JSON.stringify(cart));
  updateCartBadge();
}

function updateCartBadge() {
  const countEl = document.getElementById('cartCount');
  if (!countEl) return;
  const total = cart.reduce((s, i) => s + i.quantity, 0);
  if (total > 0) {
    countEl.textContent = total;
    countEl.style.display = 'flex';
  } else {
    countEl.style.display = 'none';
  }
}

// ── Burger Menu Logic ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const burger = document.querySelector('.sb-header-default__burger');
  const menu = document.querySelector('.sb-header-default__menu_solid');
  if (burger && menu) {
    burger.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = menu.classList.contains('sb-header-default__menu_open') || menu.classList.contains('burger-menu-open');
      if (isOpen) {
        burger.classList.remove('sb-header-default__burger_open', 'sb-header-default__burger_active');
        menu.classList.remove('sb-header-default__menu_open', 'burger-menu-open');
      } else {
        burger.classList.add('sb-header-default__burger_open', 'sb-header-default__burger_active');
        menu.classList.add('sb-header-default__menu_open', 'burger-menu-open');
      }
    });
    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
      if (!burger.contains(e.target) && !menu.contains(e.target)) {
        burger.classList.remove('sb-header-default__burger_open', 'sb-header-default__burger_active');
        menu.classList.remove('sb-header-default__menu_open', 'burger-menu-open');
      }
    });
  }
});



function addToCart(product, size) {
  const key = `${product.id}_${size || ''}`;
  const existing = cart.find(i => i.key === key);
  if (existing) {
    existing.quantity++;
  } else {
    const primaryImg = product.images
      ? (product.images.find(i => i.is_primary)?.url || product.images[0]?.url || null)
      : (product.primary_image || null);
    cart.push({
      key,
      product_id: product.id,
      product_name: product.name,
      product_price: Number(product.price),
      size: size || null,
      quantity: 1,
      image: primaryImg,
    });
  }
  saveCart();
  showToast(`${product.name} добавлен в корзину 🛒`);
}

function removeFromCart(key) {
  cart = cart.filter(i => i.key !== key);
  saveCart();
  renderCartItems();
}

function changeQty(key, delta) {
  const item = cart.find(i => i.key === key);
  if (!item) return;
  item.quantity = Math.max(0, item.quantity + delta);
  if (item.quantity === 0) {
    cart = cart.filter(i => i.key !== key);
  }
  saveCart();
  renderCartItems();
}

function cartTotal() {
  return cart.reduce((s, i) => s + i.product_price * i.quantity, 0);
}

// ── Cart Modal ────────────────────────────────────────────────────────────────

window.openCart = function() {
  reloadCart(); // always read fresh state in case other tabs/pages changed it
  renderCartItems();
  const modal = document.getElementById('cartModal');
  const backdrop = document.getElementById('cartBackdrop');
  if (modal) modal.classList.add('open');
  if (backdrop) backdrop.classList.add('open');
  document.body.style.overflow = 'hidden';
};

window.closeCart = function() {
  const modal = document.getElementById('cartModal');
  const backdrop = document.getElementById('cartBackdrop');
  if (modal) modal.classList.remove('open');
  if (backdrop) backdrop.classList.remove('open');
  document.body.style.overflow = '';
};

// ── Support dialog ────────────────────────────────────────────────────────────
// The store owner wants a support button next to the cart that opens an
// in-site dialog and forwards the user to the manager's Telegram account.
window.openSupport = function() {
  const modal = document.getElementById('supportModal');
  const backdrop = document.getElementById('supportBackdrop');
  if (modal) modal.classList.add('open');
  if (backdrop) backdrop.classList.add('open');
  document.body.style.overflow = 'hidden';
  // Populate the Telegram link from config (manager_username/contact_telegram),
  // falling back to the default store account.
  const username = (siteConfig.manager_username || siteConfig.contact_telegram || 'xtempls_wear').replace(/^@/, '');
  const link = document.getElementById('supportTgLink');
  if (link) {
    link.href = `https://t.me/${username}`;
    // Rewrite the whole label so we don't depend on fragile child-node lookups.
    link.innerHTML = `
      <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
        <path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/>
      </svg>
      Написать в Telegram @${username}`;
  }
};

window.closeSupport = function() {
  const modal = document.getElementById('supportModal');
  const backdrop = document.getElementById('supportBackdrop');
  if (modal) modal.classList.remove('open');
  if (backdrop) backdrop.classList.remove('open');
  document.body.style.overflow = '';
};

window.openCheckout = function() {
  if (cart.length === 0) return;
  const cartModal = document.getElementById('cartModal');
  const backdrop = document.getElementById('cartBackdrop');
  if (cartModal) cartModal.classList.remove('open');
  if (backdrop) backdrop.classList.remove('open');
  document.body.style.overflow = '';
  // Populate checkout summary
  const summary = document.getElementById('checkoutSummary');
  const totalEl = document.getElementById('checkoutTotal');
  if (summary) {
    summary.innerHTML = cart.map(i => `
      <div class="checkout-summary-item">
        <span class="summary-name">${i.product_name}${i.size ? ' (' + i.size + ')' : ''} × ${i.quantity}</span>
        <span class="summary-price">${fmt(i.product_price * i.quantity)}</span>
      </div>
    `).join('');
  }
  if (totalEl) totalEl.textContent = fmt(cartTotal());
  // Pre-fill name from Telegram
  const nameEl = document.getElementById('chkName');
  if (nameEl && tg?.initDataUnsafe?.user) {
    const u = tg.initDataUnsafe.user;
    nameEl.value = [u.first_name, u.last_name].filter(Boolean).join(' ');
  }
  // Pre-fill Telegram username (if available)
  const telegramEl = document.getElementById('chkTelegram');
  if (telegramEl && tg?.initDataUnsafe?.user?.username) {
    telegramEl.value = '@' + tg.initDataUnsafe.user.username;
  }
  // Reset promo / bonuses
  const promoInput = document.getElementById('chkPromo');
  const promoMsg = document.getElementById('promoMsg');
  if (promoInput) promoInput.value = '';
  if (promoMsg) { promoMsg.textContent = ''; promoMsg.className = 'promo-msg'; }
  window._appliedPromo = null;
  window._bonusSpend = 0;
  window._bonusBalance = 0;
  const spendInput = document.getElementById('chkBonusSpend');
  if (spendInput) spendInput.value = '';
  const bonusMsg = document.getElementById('bonusSpendMsg');
  if (bonusMsg) { bonusMsg.textContent = ''; bonusMsg.className = 'promo-msg'; }
  loadCheckoutBonuses();
  updateCheckoutTotal();
  const checkoutModal = document.getElementById('checkoutModal');
  const checkoutBackdrop = document.getElementById('checkoutBackdrop');
  if (checkoutModal) checkoutModal.classList.add('open');
  if (checkoutBackdrop) checkoutBackdrop.classList.add('open');
  document.body.style.overflow = 'hidden';
};

window.backToCart = function() {
  const checkoutModal = document.getElementById('checkoutModal');
  const checkoutBackdrop = document.getElementById('checkoutBackdrop');
  if (checkoutModal) checkoutModal.classList.remove('open');
  if (checkoutBackdrop) checkoutBackdrop.classList.remove('open');
  document.body.style.overflow = '';
  openCart();
};

function checkoutBaseAfterPromo() {
  const promo = window._appliedPromo;
  const base = cartTotal();
  if (!promo || !promo.discount_percent) return base;
  const disc = Math.round(base * promo.discount_percent / 100);
  return Math.max(0, base - disc);
}

function updateCheckoutTotal() {
  const totalEl = document.getElementById('checkoutTotal');
  const discEl = document.getElementById('checkoutDiscount');
  const promo = window._appliedPromo;
  const base = cartTotal();
  const afterPromo = checkoutBaseAfterPromo();
  const spend = Math.min(Number(window._bonusSpend || 0), afterPromo, Number(window._bonusBalance || 0));
  window._bonusSpend = spend;
  const lines = [];
  if (promo && promo.discount_percent) {
    const disc = Math.round(base * promo.discount_percent / 100);
    lines.push(`<span class="promo-discount-line">Скидка ${promo.discount_percent}%: −${fmt(disc)}</span>`);
  }
  if (spend > 0) {
    lines.push(`<span class="promo-discount-line">Бонусы: −${fmt(spend)}</span>`);
  }
  if (discEl) discEl.innerHTML = lines.join('<br>');
  if (totalEl) totalEl.textContent = fmt(Math.max(0, afterPromo - spend));
}

async function loadCheckoutBonuses() {
  const box = document.getElementById('bonusSpendBox');
  if (!box) return;
  const token = localStorage.getItem('xtempls_token');
  if (!token) {
    box.style.display = 'none';
    return;
  }
  try {
    const res = await fetch(`${API}/account/bonuses`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) { box.style.display = 'none'; return; }
    const data = await res.json();
    window._bonusBalance = Number(data.balance || 0);
    const avail = document.getElementById('bonusAvailable');
    if (avail) avail.textContent = fmt(window._bonusBalance);
    box.style.display = window._bonusBalance > 0 ? '' : 'none';
  } catch (e) {
    box.style.display = 'none';
  }
}

window.toggleBonusSpend = function() {
  const controls = document.getElementById('bonusSpendControls');
  if (!controls) return;
  const open = controls.style.display === 'none' || !controls.style.display;
  controls.style.display = open ? 'flex' : 'none';
  if (open) {
    const input = document.getElementById('chkBonusSpend');
    const max = Math.min(Number(window._bonusBalance || 0), checkoutBaseAfterPromo());
    if (input && !input.value) input.value = String(Math.floor(max));
  }
};

window.applyBonusSpend = function() {
  const input = document.getElementById('chkBonusSpend');
  const msg = document.getElementById('bonusSpendMsg');
  let val = Number(input?.value || 0);
  if (Number.isNaN(val) || val < 0) val = 0;
  const max = Math.min(Number(window._bonusBalance || 0), checkoutBaseAfterPromo());
  if (val > max) val = max;
  window._bonusSpend = Math.round(val * 100) / 100;
  if (input) input.value = String(window._bonusSpend);
  if (msg) {
    msg.textContent = window._bonusSpend > 0
      ? `Спишем ${fmt(window._bonusSpend)} с бонусного счёта`
      : 'Бонусы не списываются';
    msg.className = 'promo-msg promo-ok';
  }
  updateCheckoutTotal();
};

window.applyPromo = async function() {
  const code = document.getElementById('chkPromo')?.value.trim();
  const msg = document.getElementById('promoMsg');
  if (!code) return;
  if (msg) msg.textContent = 'Проверяем...';
  try {
    const token = localStorage.getItem('xtempls_token');
    const res = await fetch(`${API}/promo/validate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ code })
    });
    const data = await res.json();
    if (data.valid) {
      window._appliedPromo = { code, discount_percent: data.discount_percent || 0 };
      if (msg) { msg.textContent = data.message; msg.className = 'promo-msg promo-ok'; }
    } else {
      window._appliedPromo = null;
      if (msg) { msg.textContent = data.message; msg.className = 'promo-msg promo-err'; }
    }
    updateCheckoutTotal();
  } catch(e) {
    if (msg) { msg.textContent = 'Ошибка проверки промокода'; msg.className = 'promo-msg promo-err'; }
  }
};

function renderCartItems() {
  const body = document.getElementById('cartBody');
  const footer = document.getElementById('cartFooter');
  const totalEl = document.getElementById('cartTotal');
  if (!body) return;

  if (cart.length === 0) {
    body.innerHTML = '<div class="cart-empty">🛒 Корзина пуста</div>';
    if (footer) footer.style.display = 'none';
    return;
  }

  if (footer) footer.style.display = 'flex';
  if (totalEl) totalEl.textContent = fmt(cartTotal());

  body.innerHTML = cart.map(item => `
    <div class="cart-item">
      ${item.image
        ? `<img class="cart-item-img" src="${item.image}" alt="${item.product_name}" />`
        : `<div class="cart-item-img-placeholder">🛍</div>`}
      <div class="cart-item-info">
        <div class="cart-item-name">${item.product_name}</div>
        <div class="cart-item-meta">${item.size ? 'Размер: ' + item.size : 'Один размер'}</div>
        <div class="cart-item-price">${fmt(item.product_price * item.quantity)}</div>
      </div>
      <div class="cart-item-qty">
        <button class="qty-btn" onclick="changeQty('${item.key}', -1)">−</button>
        <span class="qty-num">${item.quantity}</span>
        <button class="qty-btn" onclick="changeQty('${item.key}', 1)">+</button>
      </div>
    </div>
  `).join('');
}

// ── Order Submission ──────────────────────────────────────────────────────────

window.submitOrder = async function(e) {
  if (e) e.preventDefault();
  const name = document.getElementById('chkName')?.value.trim();
  const phone = document.getElementById('chkPhone')?.value.trim();
  const telegramRaw = document.getElementById('chkTelegram')?.value.trim();
  const address = document.getElementById('chkAddress')?.value.trim();
  const comment = document.getElementById('chkComment')?.value.trim();
  const consent = document.getElementById('chkConsent')?.checked;

  // Client-side validation mirrors the server-side rules so the user gets
  // immediate feedback instead of a generic "send error".
  if (!name || name.length < 2) {
    showToast('Введите имя и фамилию (минимум 2 символа)');
    return;
  }
  // Валидация телефона: + (опц.), затем 7+ цифр, допустимы пробелы/дефисы/скобки.
  const phoneClean = (phone || '').replace(/[^\d+]/g, '');
  const phoneDigits = phoneClean.replace(/\D/g, '');
  if (!phone || phoneDigits.length < 7) {
    showToast('Введите корректный номер телефона (минимум 7 цифр)');
    return;
  }
  // Валидация Telegram (если заполнен): @username, 4–32 символа, латиница/цифры/_.
  let telegram = telegramRaw;
  if (telegram) {
    telegram = telegram.replace(/^@/, '');
    if (!/^[a-zA-Z][a-zA-Z0-9_]{3,31}$/.test(telegram)) {
      showToast('Telegram-ник: 4–32 символа, латиница, цифры, подчёркивание');
      return;
    }
  }
  if (!address || address.length < 5) {
    showToast('Укажите адрес доставки (минимум 5 символов)');
    return;
  }
  if (!consent) {
    showToast('Необходимо согласие с офертой и политикой конфиденциальности');
    return;
  }
  if (cart.length === 0) {
    showToast('Корзина пуста');
    return;
  }

  // Проверка авторизации: когда пользователь заполнил все поля и переходит
  // к подтверждению заказа, проверяем авторизацию. Если не залогинен,
  // сохраняем введённые данные формы и отправляем на страницу входа/регистрации.
  if (!localStorage.getItem('xtempls_token')) {
    try {
      const checkoutData = {
        name,
        phone,
        telegram: telegramRaw,
        address,
        comment,
        consent,
        promo: window._appliedPromo ? window._appliedPromo.code : (document.getElementById('chkPromo')?.value.trim() || null),
        bonus_spend: window._bonusSpend || 0,
        return_url: window.location.pathname + window.location.search,
        from_checkout: true,   // флаг: переход именно из оформления заказа
        ts: Date.now()
      };
      localStorage.setItem('xtempls_checkout_intent', JSON.stringify(checkoutData));
    } catch (e) {}
    showToast('Для завершения оформления заказа войдите или зарегистрируйтесь');
    setTimeout(() => { location.href = '/login.html'; }, 1000);
    return;
  }

  const btn = document.getElementById('submitOrderBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Отправка...'; }

  try {
    const body = {
      customer_name: name,
      customer_phone: phone,
      customer_telegram: telegram || null,
      delivery_address: address,
      comment: comment || null,
      tg_init_data: tg?.initData || null,
      promo_code: window._appliedPromo?.code || null,
      bonus_spend: window._bonusSpend > 0 ? window._bonusSpend : null,
      consent_accepted: true,
      items: cart.map(i => ({
        product_id: i.product_id,
        size: i.size,
        quantity: i.quantity,
      }))
    };

    const res = await fetch(`${API}/orders/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(localStorage.getItem('xtempls_token')
          ? { 'Authorization': `Bearer ${localStorage.getItem('xtempls_token')}` } : {}),
      },
      body: JSON.stringify(body)
    });

    // Сначала проверяем статус, парсим JSON безопасно (как в дизайновой форме),
    // иначе при не-JSON ответе (500 HTML) юзер видел «Ошибка соединения»
    // вместо реальной причины.
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('xtempls_token');
        try {
          const checkoutData = {
            name,
            phone,
            telegram: telegramRaw,
            address,
            comment,
            consent,
            promo: window._appliedPromo ? window._appliedPromo.code : (document.getElementById('chkPromo')?.value.trim() || null),
            bonus_spend: window._bonusSpend || 0,
            return_url: window.location.pathname + window.location.search,
            from_checkout: true,   // флаг: переход именно из оформления заказа
            ts: Date.now()
          };
          localStorage.setItem('xtempls_checkout_intent', JSON.stringify(checkoutData));
        } catch (e) {}
        showToast('Ваш сеанс истёк. Пожалуйста, войдите снова');
        setTimeout(() => { location.href = '/login.html'; }, 1200);
        return;
      }
      const err = await res.json().catch(() => ({}));
      console.error('Order submit failed:', res.status, err);
      showToast(err.detail || 'Ошибка отправки заказа');
      return;
    }
    const orderData = await res.json();

    // Clear cart completely (in memory + localStorage + badge + drawer body).
    cart = [];
    localStorage.removeItem('xtempls_cart');
    window._appliedPromo = null;
    updateCartBadge();

    if (orderData.payment_url) {
      // Сразу редирект на оплату
      window.location.href = orderData.payment_url;
      return;
    }

    // Если нет payment_url (например, дизайн), показываем success screen
    const contactDisplay = phone + (telegram ? ' · @' + telegram : '');
    const checkoutBody = document.getElementById('checkoutModal')?.querySelector('.cart-body');
    const checkoutFooter = document.getElementById('checkoutModal')?.querySelector('.cart-footer');
    if (checkoutBody) {
      checkoutBody.innerHTML = `
        <div class="order-success">
          <div class="success-icon">✅</div>
          <div class="success-title">Спасибо за заказ!</div>
          <div class="success-text">
            ${name}, ваш заказ принят.<br/>
            Мы свяжемся с вами по контакту<br/>
            <strong>${contactDisplay}</strong><br/><br/>
            Менеджер скоро ответит вам.
          </div>
          <div class="success-actions" style="margin-top: 24px;">
            <button class="btn-success-close" onclick="closeSuccessAndGo('close')">Закрыть</button>
            <button class="btn-success-home" onclick="closeSuccessAndGo('home')">На главную</button>
          </div>
        </div>
      `;
    }
    if (checkoutFooter) checkoutFooter.style.display = 'none';

  } catch (e) {
    showToast('Ошибка соединения');
    console.error(e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Отправить заказ'; }
  }
};

// Close the success screen either to the underlying page or to the home page.
window.closeSuccessAndGo = function(action) {
  const checkoutModal = document.getElementById('checkoutModal');
  const checkoutBackdrop = document.getElementById('checkoutBackdrop');
  if (checkoutModal) checkoutModal.classList.remove('open');
  if (checkoutBackdrop) {
    checkoutBackdrop.classList.remove('open');
    checkoutBackdrop.style.display = '';
  }
  document.body.style.overflow = '';
  if (action === 'home') {
    window.location.href = '/';
  }
};

// ── UI Injection ──────────────────────────────────────────────────────────────

function injectCartUI() {
  if (document.getElementById('cartModal')) return;

  const html = `
    <!-- Cart Backdrop -->
    <div id="cartBackdrop" class="cart-backdrop" onclick="closeCart()"></div>

    <!-- Support Backdrop -->
    <div id="supportBackdrop" class="cart-backdrop" onclick="closeSupport()"></div>

    <!-- Support FAB (above the cart FAB) -->
    <div class="support-fab" onclick="openSupport()" title="Поддержка" aria-label="Поддержка">
      <svg width="22" height="22" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/>
        <path stroke-linecap="round" stroke-linejoin="round" d="M13.73 21a2 2 0 01-3.46 0"/>
      </svg>
    </div>

    <!-- FAB -->
    <div class="cart-btn" onclick="openCart()" style="position:fixed; bottom:20px; right:20px; z-index:999999;">
      <svg width="28" height="28" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"></path>
      </svg>
      <span class="cart-count" id="cartCount" style="display:none;">0</span>
    </div>

    <!-- Cart Drawer -->
    <div id="cartModal" class="cart-drawer">
      <div class="cart-drawer-inner">
        <div class="cart-header">
          <h2 class="cart-title" style="margin:0;">Корзина</h2>
          <button class="modal-close-btn" onclick="closeCart()">×</button>
        </div>
        <div class="cart-body" id="cartBody"></div>
        <div class="cart-footer" id="cartFooter" style="display:none;">
          <div class="cart-total-row">
            <span>Итого:</span>
            <span class="cart-total-price" id="cartTotal">0 ₽</span>
          </div>
          <button class="checkout-btn" onclick="openCheckout()">К оформлению →</button>
        </div>
      </div>
    </div>

    <!-- Checkout Backdrop -->
    <div id="checkoutBackdrop" class="cart-backdrop" onclick=""></div>

    <!-- Checkout Modal -->
    <div id="checkoutModal" class="cart-drawer">
      <div class="cart-drawer-inner">
        <div class="cart-header">
          <button class="back-icon-btn" onclick="backToCart()">
            <svg width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
          </button>
          <h2>Оформление</h2>
          <button class="modal-close-btn" onclick="document.getElementById('checkoutModal').classList.remove('open'); document.getElementById('checkoutBackdrop').classList.remove('open'); document.body.style.overflow='';">×</button>
        </div>
        <div class="cart-body">
          <div id="checkoutSummary" class="checkout-summary"></div>
          <div id="checkoutDiscount" class="checkout-discount-wrap"></div>
          <div class="checkout-total-line">
            <span>Сумма заказа:</span>
            <span id="checkoutTotal">0 ₽</span>
          </div>
          <form id="checkoutForm" class="checkout-form" onsubmit="submitOrder(event)">
            <label class="chk-label">Имя и Фамилия</label>
            <input type="text" id="chkName" class="chk-input" required minlength="2" placeholder="Иван Иванов" />
            <label class="chk-label">Телефон *</label>
            <input type="tel" id="chkPhone" class="chk-input" required placeholder="+7 999 123-45-67" inputmode="tel" />
            <label class="chk-label">Telegram (необязательно)</label>
            <input type="text" id="chkTelegram" class="chk-input" placeholder="@username" inputmode="text" />
            <label class="chk-label">Адрес доставки *</label>
            <textarea id="chkAddress" class="chk-input" required minlength="5" rows="2" placeholder="Город, улица, дом, квартира"></textarea>
            <label class="chk-label">Промокод</label>
            <div class="promo-row">
              <input type="text" id="chkPromo" class="chk-input promo-input" placeholder="Введите промокод" />
              <button type="button" class="promo-apply-btn" onclick="applyPromo()">Применить</button>
            </div>
            <div id="promoMsg" class="promo-msg"></div>
            <div id="bonusSpendBox" class="bonus-spend-box" style="display:none;">
              <div class="bonus-spend-head">
                <span>На бонусном счёте: <b id="bonusAvailable">0 ₽</b></span>
                <button type="button" class="promo-apply-btn" onclick="toggleBonusSpend()">Списать бонусы</button>
              </div>
              <div id="bonusSpendControls" class="promo-row" style="display:none;margin-top:8px;">
                <input type="number" id="chkBonusSpend" class="chk-input promo-input" min="0" step="1" placeholder="Сколько списать" />
                <button type="button" class="promo-apply-btn" onclick="applyBonusSpend()">Применить</button>
              </div>
              <div id="bonusSpendMsg" class="promo-msg"></div>
            </div>
            <label class="chk-label">Комментарий к заказу</label>
            <textarea id="chkComment" class="chk-input" placeholder="Пожелания и т.д." rows="2"></textarea>
            <label class="chk-consent-row">
              <input type="checkbox" id="chkConsent" />
              <span class="chk-consent-text">
                Я согласен с <a href="/public.html" target="_blank" class="chk-consent-link">офертой</a>
                и <a href="/public.html" target="_blank" class="chk-consent-link">политикой конфиденциальности</a>
              </span>
            </label>
            <button type="submit" id="submitOrderBtn" class="checkout-submit-btn">Отправить заказ</button>
          </form>
        </div>
      </div>
    </div>

    <!-- Support Drawer -->
    <div id="supportModal" class="cart-drawer">
      <div class="cart-drawer-inner">
        <div class="cart-header">
          <h2 class="cart-title" style="margin:0;">Поддержка</h2>
          <button class="modal-close-btn" onclick="closeSupport()">×</button>
        </div>
        <div class="cart-body" style="padding:24px;">
          <div style="font-size:14px;line-height:1.6;color:var(--text-secondary,#444);margin-bottom:20px;">
            Есть вопрос по заказу, размеру или доставке?<br/>
            Напишите нам — обычно отвечаем в течение нескольких часов.
          </div>
          <div style="display:flex;flex-direction:column;gap:12px;">
            <a id="supportTgLink" class="support-cta" href="https://t.me/xtempls_wear" target="_blank" rel="noopener">
              <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                <path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/>
              </svg>
              Написать в Telegram @xtempls_wear
            </a>
          </div>
          <div style="margin-top:24px;padding-top:20px;border-top:1px solid var(--border,#eee);font-size:13px;color:var(--text-muted,#777);">
            Или откройте <a href="/public.html" style="color:var(--accent,#2E3359);">уголок покупателя</a> — там оферта, политика конфиденциальности и реквизиты.
          </div>
        </div>
      </div>
    </div>

    <!-- Lightbox -->
    <div id="lightbox" class="lightbox" onclick="closeLightbox()">
      <button class="lightbox-close" onclick="closeLightbox()">×</button>
      <button class="lightbox-arrow lightbox-prev" onclick="event.stopPropagation(); lightboxNav(-1)">‹</button>
      <img id="lightboxImg" class="lightbox-img" onclick="event.stopPropagation()" />
      <button class="lightbox-arrow lightbox-next" onclick="event.stopPropagation(); lightboxNav(1)">›</button>
    </div>
  `;
  const div = document.createElement('div');
  div.innerHTML = html;
  document.body.appendChild(div);
}

// Inject cart UI as soon as <body> is available, then refresh the badge.
// On the catalog page the framework CSS is heavy and <body> can still be
// parsing when this script (deferred) runs — so wait for DOMContentLoaded
// if body isn't ready, otherwise the injected FAB and badge don't appear
// and the cart looks "empty" there.
function initCartUI() {
  injectCartUI();
  reloadCart();
  updateCartBadge();
  resumeCheckoutIfRequested();
}

// Возврат к оформлению после входа или регистрации. После успешного входа
// пользователя возвращают обратно с ?checkout=1. Открываем форму и восстанавливаем
// все поля, которые пользователь заполнил до авторизации.
function resumeCheckoutIfRequested() {
  const params = new URLSearchParams(window.location.search);
  if (params.get('checkout') !== '1') return;
  // Чистим параметр из URL, чтобы при перезагрузке форма не открывалась снова.
  params.delete('checkout');
  const clean = params.toString();
  history.replaceState(null, '', window.location.pathname + (clean ? '?' + clean : ''));
  // Возобновляем только если залогинен и корзина не пуста.
  if (!localStorage.getItem('xtempls_token') || cart.length === 0) return;
  openCheckout();

  // Восстанавливаем сохранённые данные полей формы оформления заказа
  const raw = localStorage.getItem('xtempls_checkout_intent');
  if (raw) {
    try {
      const intent = JSON.parse(raw);
      const fresh = intent && intent.ts && (Date.now() - intent.ts) < 24 * 3600 * 1000;
      if (fresh) {
        const nameEl = document.getElementById('chkName');
        const phoneEl = document.getElementById('chkPhone');
        const tgEl = document.getElementById('chkTelegram');
        const addrEl = document.getElementById('chkAddress');
        const commEl = document.getElementById('chkComment');
        const consEl = document.getElementById('chkConsent');
        const promoEl = document.getElementById('chkPromo');

        if (nameEl && intent.name) nameEl.value = intent.name;
        if (phoneEl && intent.phone) phoneEl.value = intent.phone;
        if (tgEl && intent.telegram !== undefined) tgEl.value = intent.telegram || '';
        if (addrEl && intent.address) addrEl.value = intent.address;
        if (commEl && intent.comment !== undefined) commEl.value = intent.comment || '';
        if (consEl && intent.consent !== undefined) consEl.checked = !!intent.consent;
        if (promoEl && intent.promo) {
          promoEl.value = intent.promo;
          setTimeout(() => {
            if (typeof window.applyPromo === 'function') window.applyPromo();
          }, 100);
        }
        if (intent.bonus_spend) {
          window._bonusSpend = Number(intent.bonus_spend) || 0;
          const spendEl = document.getElementById('chkBonusSpend');
          if (spendEl) spendEl.value = String(window._bonusSpend);
          const controls = document.getElementById('bonusSpendControls');
          if (controls) controls.style.display = 'flex';
          setTimeout(() => {
            if (typeof window.applyBonusSpend === 'function') window.applyBonusSpend();
          }, 150);
        }
      }
    } catch (e) {}
    localStorage.removeItem('xtempls_checkout_intent');
  }
}

if (document.body) {
  initCartUI();
} else {
  document.addEventListener('DOMContentLoaded', initCartUI);
}

// Keep the badge in sync if another tab modifies the cart.
window.addEventListener('storage', (e) => {
  if (e.key === 'xtempls_cart') {
    reloadCart();
    updateCartBadge();
  }
});

// Re-sync when the tab becomes visible (user returns from another page/tab).
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    reloadCart();
    updateCartBadge();
  }
});


// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(price) {
  return Number(price).toLocaleString('ru-RU') + ' ₽';
}

function discount(price, oldPrice) {
  if (!oldPrice || Number(oldPrice) <= Number(price)) return null;
  return Math.round((1 - Number(price) / Number(oldPrice)) * 100);
}

function stockBadge(status) {
  if (status === 'out_of_stock') return '<span class="stock-badge badge-out">Нет в наличии</span>';
  if (status === 'preorder') return '<span class="stock-badge badge-preorder">Предзаказ</span>';
  return '';
}

function showToast(msg, duration = 2500) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

function slugify(str) {
  return str.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '');
}

// ── Router: detect current page ───────────────────────────────────────────────

const isProductPage = window.location.pathname.includes('product.html');
const isCatalogPage = window.location.pathname.includes('catalog.html') || window.location.pathname === '/catalog';
const isIndexPage = window.location.pathname === '/' || window.location.pathname.includes('index.html');

if (isIndexPage && tg && tg.BackButton.isVisible) {
  tg.BackButton.hide();
}
// ── CATALOG PAGE ────────────────────────────────────────────────────────────────

if (isCatalogPage) {
  // Telegram hardware/swipe back button → go to the home page.
  // We navigate explicitly to "/" rather than history.back(), because on
  // phones the catalog is often opened as the first entry in the WebApp
  // history (history.length === 1), where history.back() does nothing and
  // the back button appears "broken".
  if (tg?.BackButton) {
    tg.BackButton.show();
    const goHome = () => { window.location.href = '/'; };
    tg.BackButton.offClick(goHome);
    tg.BackButton.onClick(goHome);
  }

  let currentCategory = '';
  let currentFeatured = false;
  let currentSearch = '';
  let searchTimeout;
  let currentPage = 1;
  let totalPages = 1;
  let allProducts = [];

  const grid = document.getElementById('products-container');
  const catList = document.getElementById('categories-container');
  const searchInput = document.getElementById('searchInput');
  const loadMoreBtn = document.getElementById('loadMoreBtn');
  const loadMoreWrap = document.getElementById('loadMoreWrap');
  const featuredRow = document.getElementById('featuredRow');
  const featuredSection = document.getElementById('featuredSection');
  const titleEl = document.getElementById('titleEl');
  const countEl = document.getElementById('countEl');

  // Skeleton loader
  function showSkeletons(count = 6) {
    if (!grid) return;
    grid.innerHTML = Array(count).fill(0).map(() => `
      <div class="s-services-type-5__item js-catalog__item sb-m-3-top sb-col_lg-4 sb-col_md-6 sb-col_sm-6 sb-col_xs-12 sb-skeleton">
        <div class="s-services-type-5__item-content sb-m-clear-bottom">
          <div class="s-services-type-5__image sb-image-square sb-skeleton__image"></div>
          <h3 class="s-services-type-5__subtitle sb-font-p2 sb-font-title sb-pre-wrap sb-skeleton__title sb-align-center"></h3>
          <div class="s-services-type-5__price sb-font-p3 sb-skeleton__price sb-align-center"></div>
        </div>
      </div>
    `).join('');
  }

  // Render product card (Tinkoff Style)
  function renderCard(p, delay = 0) {
    const imgHtml = p.primary_image
      ? `<img src="${p.primary_image}" alt="${p.name}" loading="lazy" class="sb-image-crop sb-image-crop_loaded lazy js-cart-goods-image" />`
      : `<div class="card-placeholder" style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; background:#f0f0f0;">🛍</div>`;

    return `
      <div class="s-services-type-5__item js-catalog__item sb-m-3-top sb-col_lg-4 sb-col_md-6 sb-col_sm-6 sb-col_xs-12" style="animation-delay:${delay}ms">
        <div class="s-services-type-5__item-content sb-m-clear-bottom" style="cursor: pointer; position:relative;" onclick="openProduct('${p.slug}', ${p.id})">
          <div class="s-services-type-5__image sb-image-square" style="position:relative;">
            ${newBadgeHtml(p)}${favBtnHtml(p.id)}${imgHtml}
          </div>
          <h3 class="s-services-type-5__subtitle sb-font-p2 sb-font-title sb-pre-wrap sb-align-center">${p.name}</h3>
          ${p.old_price ? `<div class="s-services-type-5__old-price sb-font-p3 sb-crossed sb-text-opacity sb-align-center">${fmt(p.old_price)}</div>` : ''}
          <div class="s-services-type-5__price sb-font-p3 sb-align-center">${fmt(p.price)}</div>
        </div>
      </div>
    `;
  }

  function openProduct(slug, id) {
    window.location.href = `product.html?id=${id}`;
  }
  window.openProduct = openProduct;

  // Compact card for the "featured" recommendations row.
  function renderFeaturedCard(p) {
    const imgHtml = p.primary_image
      ? `<img src="${p.primary_image}" alt="${p.name}" loading="lazy" class="sb-image-crop sb-image-crop_loaded lazy js-cart-goods-image" />`
      : `<div class="card-placeholder" style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; background:#f0f0f0;">🛍</div>`;

    const badge = p.old_price && Number(p.old_price) > Number(p.price)
      ? `<div style="position:absolute; top:8px; left:8px; background:#FFDD2D; color:#000; font-size:11px; font-weight:700; padding:3px 8px; border-radius:6px;">−${Math.round((1 - Number(p.price) / Number(p.old_price)) * 100)}%</div>`
      : '';

    return `
      <div class="s-services-type-5__item sb-m-3-top sb-col_lg-3 sb-col_md-4 sb-col_sm-6 sb-col_xs-12">
        <div class="s-services-type-5__item-content sb-m-clear-bottom" style="cursor: pointer; position:relative;" onclick="openProduct('${p.slug}', ${p.id})">
          <div class="s-services-type-5__image sb-image-square" style="position:relative;">
            ${newBadgeHtml(p)}${badge}${favBtnHtml(p.id)}${imgHtml}
          </div>
          <h3 class="s-services-type-5__subtitle sb-font-p2 sb-font-title sb-pre-wrap sb-align-center">${p.name}</h3>
          ${p.old_price ? `<div class="s-services-type-5__old-price sb-font-p3 sb-crossed sb-text-opacity sb-align-center">${fmt(p.old_price)}</div>` : ''}
          <div class="s-services-type-5__price sb-font-p3 sb-align-center">${fmt(p.price)}</div>
        </div>
      </div>
    `;
  }

  // Load categories
  async function loadCategories() {
    try {
      const res = await fetch(`${API}/categories/`);
      const cats = await res.json();
      
      const allBtn = document.createElement('button');
      allBtn.className = 'sb-button-secondary sb-font-p3 cat-btn active';
      allBtn.style.margin = '0 5px 10px';
      allBtn.style.padding = '8px 16px';
      allBtn.dataset.id = '';
      allBtn.textContent = 'Все';
      allBtn.onclick = () => selectCategory('');
      if (catList) catList.appendChild(allBtn);

      const newBtn = document.createElement('button');
      newBtn.className = 'sb-button-secondary sb-font-p3 cat-btn';
      newBtn.style.margin = '0 5px 10px';
      newBtn.style.padding = '8px 16px';
      newBtn.dataset.id = 'featured';
      newBtn.textContent = 'Новинки';
      newBtn.onclick = () => selectFeatured();
      if (catList) catList.appendChild(newBtn);

      cats.forEach(cat => {
        const btn = document.createElement('button');
        btn.className = 'sb-button-secondary sb-font-p3 cat-btn';
        btn.style.margin = '0 5px 10px';
        btn.style.padding = '8px 16px';
        btn.dataset.id = cat.id;
        btn.textContent = cat.name;
        if (cat.product_count > 0) btn.textContent += ` (${cat.product_count})`;
        btn.onclick = () => selectCategory(cat.id);
        if (catList) catList.appendChild(btn);
      });
    } catch (e) {
      console.error('Failed to load categories', e);
    }
  }

  function markActiveChip(id) {
    document.querySelectorAll('.cat-btn').forEach(b => {
      if (String(b.dataset.id) === String(id)) b.classList.add('active');
      else b.classList.remove('active');
    });
  }

  function selectCategory(id) {
    currentCategory = id;
    currentFeatured = false;
    currentPage = 1;
    allProducts = [];
    markActiveChip(id);
    const showFeatured = !currentCategory && !currentSearch && !currentFeatured;
    if (featuredSection) featuredSection.style.display = showFeatured ? 'block' : 'none';
    loadProducts(true);
  }

  function selectFeatured() {
    currentCategory = '';
    currentFeatured = true;
    currentPage = 1;
    allProducts = [];
    markActiveChip('featured');
    if (featuredSection) featuredSection.style.display = 'none';
    loadProducts(true);
  }

  // Load products
  async function loadProducts(reset = false) {
    if (reset) {
      showSkeletons();
      if (loadMoreWrap) loadMoreWrap.style.display = 'none';
    }

    try {
      const params = new URLSearchParams({
        page: currentPage,
        per_page: 20,
      });
      if (currentCategory) params.append('category_id', currentCategory);
      if (currentFeatured) params.append('featured', 'true');
      if (currentSearch) params.append('search', currentSearch);

      const res = await fetch(`${API}/products/?${params}`);
      if (!res.ok) throw new Error('API error');
      const data = await res.json();

      totalPages = data.pages;
      allProducts = reset ? data.items : [...allProducts, ...data.items];

      if (reset) {
        if (titleEl) {
          let activeCatName = 'Каталог';
          if (currentFeatured) {
            activeCatName = 'Новинки';
          } else if (currentCategory) {
            const activeBtn = document.querySelector(`.cat-btn[data-id="${currentCategory}"]`);
            if (activeBtn) {
              activeCatName = activeBtn.textContent.replace(/\s*\(\d+\)\s*$/, '').trim();
            } else {
              activeCatName = 'Товары';
            }
          }
          titleEl.textContent = activeCatName;
        }
        if (countEl) countEl.textContent = data.total > 0 ? `${data.total} товаров` : '';
      }

      if (reset) {
        if (allProducts.length === 0) {
          if (grid) grid.innerHTML = `
            <div class="state-box" style="grid-column:1/-1; width:100%; text-align:center; padding:40px;">
              <div class="state-icon" style="font-size:40px; margin-bottom:10px;">🔍</div>
              <div class="state-title" style="font-size:20px; font-weight:bold;">Ничего не найдено</div>
              <div class="state-sub">Попробуйте выбрать другую категорию</div>
            </div>`;
        } else {
          if (grid) grid.innerHTML = allProducts.map((p, i) => renderCard(p, i * 50)).join('');
        }
      } else {
        const existing = allProducts.slice(-data.items.length);
        existing.forEach((p, i) => {
          if (grid) grid.insertAdjacentHTML('beforeend', renderCard(p, i * 50));
        });
      }

      if (loadMoreWrap) loadMoreWrap.style.display = currentPage < totalPages ? 'flex' : 'none';
    } catch (e) {
      console.error(e);
      if (grid) grid.innerHTML = `
        <div class="state-box" style="grid-column:1/-1; width:100%; text-align:center; padding:40px;">
          <div class="state-icon" style="font-size:40px; margin-bottom:10px;">😕</div>
          <div class="state-title" style="font-size:20px; font-weight:bold;">Ошибка загрузки</div>
          <div class="state-sub">Проверьте соединение</div>
        </div>`;
    }
  }

  // Load featured
  async function loadFeatured() {
    try {
      const res = await fetch(`${API}/products/?featured=true&per_page=10`);
      const data = await res.json();
      if (data.items.length > 0 && featuredRow && featuredSection) {
        // We do not have renderFeaturedCard function defined here safely, but let's assume it works or just skip it if it doesn't exist
        if (typeof renderFeaturedCard === 'function') {
           featuredRow.innerHTML = data.items.map(renderFeaturedCard).join('');
           const showFeatured = !currentCategory && !currentSearch && !currentFeatured;
           featuredSection.style.display = showFeatured ? 'block' : 'none';
        }
      }
    } catch (e) {
      console.error('Failed to load featured', e);
    }
  }

  // Search debounce
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        currentSearch = searchInput.value.trim();
        currentPage = 1;
        allProducts = [];
        const showFeatured = !currentCategory && !currentSearch && !currentFeatured;
        if (featuredSection) featuredSection.style.display = showFeatured ? 'block' : 'none';
        loadProducts(true);
      }, 400);
    });
  }

  // Load more
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', () => {
      if (currentPage < totalPages) {
        currentPage++;
        loadProducts(false);
      }
    });
  }

  // Init
  (async () => {
    const qs = new URLSearchParams(location.search);
    if (qs.get('featured') === '1') currentFeatured = true;
    await loadFavoriteIds();
    await loadCategories();
    if (currentFeatured) markActiveChip('featured');
    await loadFeatured();
    await loadProducts(true);
  })();
}

// ── DESIGN REQUEST (design.html) ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const designForm = document.querySelector('.s-form-type-2__main');
  if (designForm) {
    // Fix floating labels manually
    designForm.querySelectorAll('.sb-input__field').forEach(input => {
      const updateLabel = () => {
        const label = input.nextElementSibling;
        if (label && label.classList.contains('sb-input__placeholder')) {
          if (input.value.trim() !== '' || document.activeElement === input) {
            label.style.transform = 'translateY(-20px) scale(0.85)';
            label.style.color = '#424242';
            label.style.transition = '0.2s ease all';
          } else {
            label.style.transform = '';
            label.style.color = '';
          }
        }
      };
      input.addEventListener('input', updateLabel);
      input.addEventListener('focus', updateLabel);
      input.addEventListener('blur', updateLabel);
      
      // Initialize after a short delay to catch browser auto-fills
      setTimeout(updateLabel, 100);
    });

    designForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const nameInput = document.getElementById('form/0');
      const phoneInput = document.getElementById('form/1');
      const consentCheckbox = designForm.querySelector('input[type="checkbox"][data-agreement]');
      const submitBtn = designForm.querySelector('input[type="submit"]');

      if (!nameInput || !phoneInput) return;

      const name = nameInput.value.trim();
      const phone = phoneInput.value.trim();

      // Minimum length checks (was previously only "filled").
      if (name.length < 2) {
        showToast('Введите имя (минимум 2 символа)');
        nameInput.focus();
        return;
      }
      if (phone.length < 5) {
        showToast('Введите корректный телефон');
        phoneInput.focus();
        return;
      }
      // Consent must be ticked before a design request can be sent.
      if (!consentCheckbox || !consentCheckbox.checked) {
        showToast('Необходимо согласие с офертой и политикой конфиденциальности');
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.value = 'Отправка...';
      }

      try {
        const body = {
          customer_name: name,
          customer_contact: phone,
          comment: 'Заявка на индивидуальный дизайн',
          order_type: 'design',
          tg_init_data: tg?.initData || null,
          consent_accepted: true,
          items: [] // Empty items for design request
        };

        const res = await fetch(`${API}/orders/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Server error');
        }

        // Show success msg
        const successMsg = document.querySelector('[data-status-success]');
        if (successMsg) successMsg.style.display = 'block';

        const errorMsg = document.querySelector('[data-status-error]');
        if (errorMsg) errorMsg.style.display = 'none';

        designForm.reset();

      } catch (err) {
        console.error(err);
        const errorMsg = document.querySelector('[data-status-error]');
        if (errorMsg) {
          errorMsg.style.display = 'block';
          // Surface the actual server-side reason if we have one.
          const reason = err && err.message ? err.message : '';
          if (reason) errorMsg.textContent = 'Ошибка: ' + reason;
        }
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.value = 'Отправить';
        }
      }
    });
  }
});


// ── PRODUCT PAGE ──────────────────────────────────────────────────────────────

if (isProductPage) {
  const params = new URLSearchParams(window.location.search);
  const productId = params.get('id');

  const backBtn = document.getElementById('backBtn');
  const galleryMain = document.getElementById('galleryMain');
  const galleryPlaceholder = document.getElementById('galleryPlaceholder');
  const galleryDots = document.getElementById('galleryDots');
  const galleryThumbs = document.getElementById('galleryThumbs');
  const productName = document.getElementById('productName');
  const detailPrices = document.getElementById('detailPrices');
  const stockIndicator = document.getElementById('stockIndicator');
  const sizesBlock = document.getElementById('sizesBlock');
  const sizesGrid = document.getElementById('sizesGrid');
  const descBlock = document.getElementById('descBlock');
  const productDesc = document.getElementById('productDesc');
  const contactBtn = document.getElementById('contactBtn');
  const categoryChip = document.getElementById('categoryChip');
  const categoryName = document.getElementById('categoryName');

  let images = [];
  let currentImg = 0;
  let selectedSize = null;
  // Размеры, доступные для выбора на витрине: по умолчанию берём из
  // product_sizes, а если их нет — из ключей size_chart, чтобы покупатель
  // всё равно мог выбрать размер (размерная сетка выступает источником).
  let effectiveSizes = [];

  // Back navigation. Prefer history.back() when there's somewhere to go back
  // to, otherwise fall back to the catalog. This fixes "back button does
  // nothing" on phones when a product link was opened directly.
  const goBack = () => {
    if (tg?.BackButton?.isVisible) {
      tg.BackButton.hide();
    }
    if (window.history.length > 1 && document.referrer && document.referrer !== window.location.href) {
      window.history.back();
    } else {
      window.location.href = '/catalog.html';
    }
  };

  backBtn.addEventListener('click', goBack);

  // Telegram hardware/swipe back button — same behavior.
  if (tg?.BackButton) {
    tg.BackButton.show();
    tg.BackButton.offClick(goBack);
    tg.BackButton.onClick(goBack);
  }

  // Gallery navigation
  function showImage(idx) {
    if (!images.length) return;
    currentImg = Math.max(0, Math.min(idx, images.length - 1));
    galleryMain.src = images[currentImg];
    galleryMain.style.display = 'block';
    galleryPlaceholder.style.display = 'none';

    // Update dots
    document.querySelectorAll('.gallery-dot').forEach((d, i) => {
      d.classList.toggle('active', i === currentImg);
    });
    // Update thumbs
    document.querySelectorAll('.thumb').forEach((t, i) => {
      t.classList.toggle('active', i === currentImg);
    });
  }

  // Swipe support
  let touchStartX = 0;
  const galleryEl = document.getElementById('gallery');
  galleryEl.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; }, { passive: true });
  galleryEl.addEventListener('touchend', e => {
    const diff = touchStartX - e.changedTouches[0].clientX;
    if (Math.abs(diff) > 40) {
      showImage(currentImg + (diff > 0 ? 1 : -1));
    }
  });

  // Keyboard navigation
  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowLeft') showImage(currentImg - 1);
    if (e.key === 'ArrowRight') showImage(currentImg + 1);
    if (e.key === 'Escape') closeLightbox();
  });

  // Lightbox
  window.openLightbox = function(idx) {
    const lb = document.getElementById('lightbox');
    const lbImg = document.getElementById('lightboxImg');
    if (!lb || !lbImg || !images.length) return;
    lbImg.src = images[idx];
    lb.dataset.idx = idx;
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
  };

  window.closeLightbox = function() {
    const lb = document.getElementById('lightbox');
    if (lb) lb.classList.remove('open');
    document.body.style.overflow = '';
  };

  window.lightboxNav = function(dir) {
    const lb = document.getElementById('lightbox');
    const lbImg = document.getElementById('lightboxImg');
    if (!lb || !lbImg) return;
    const idx = ((Number(lb.dataset.idx) + dir) + images.length) % images.length;
    lb.dataset.idx = idx;
    lbImg.src = images[idx];
  };

  // Размерная сетка
  window.openSizeChart = function(chart) {
    const modal = document.getElementById('sizeChartModal');
    const body = document.getElementById('sizeChartBody');
    if (!modal || !body || !chart) return;
    let chartObj = chart;
    if (typeof chartObj === 'string') {
      try { chartObj = JSON.parse(chartObj); } catch (e) { return; }
    }
    const rows = Object.entries(chartObj).map(([size, desc]) =>
      `<tr><td class="sc-size">${size}</td><td class="sc-desc">${desc}</td></tr>`
    ).join('');
    body.innerHTML = `<table class="size-chart-table"><thead><tr><th>Размер</th><th>Параметры</th></tr></thead><tbody>${rows}</tbody></table>`;
    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
  };

  window.closeSizeChart = function() {
    document.getElementById('sizeChartModal')?.classList.remove('open');
    document.body.style.overflow = '';
  };

  // Inject size chart modal if not present
  if (!document.getElementById('sizeChartModal')) {
    const scm = document.createElement('div');
    scm.innerHTML = `
      <div id="sizeChartModal" class="lightbox" onclick="closeSizeChart()">
        <div class="size-chart-modal-inner" onclick="event.stopPropagation()">
          <div class="size-chart-header">
            <span>📏 Размерная сетка</span>
            <button class="lightbox-close-sm" onclick="closeSizeChart()">×</button>
          </div>
          <div id="sizeChartBody"></div>
        </div>
      </div>
    `;
    document.body.appendChild(scm);
  }

  // Stock indicator
  function renderStock(status) {
    const map = {
      'in_stock': ['stock-in', 'В наличии'],
      'out_of_stock': ['stock-out', 'Нет в наличии'],
      'preorder': ['stock-pre', 'Предзаказ'],
    };
    const [cls, label] = map[status] || map['in_stock'];
    stockIndicator.className = `stock-indicator ${cls}`;
    stockIndicator.innerHTML = `<span class="stock-dot"></span>${label}`;
  }

  // Sizes
  function renderSizes(sizes) {
    if (!sizes || sizes.length === 0) {
      sizesBlock.style.display = 'none';
      return;
    }
    sizesBlock.style.display = 'block';
    
    // Normalize in case they are strings somehow
    const normSizes = sizes.map(s => {
      if (typeof s === 'string') return { size: s, is_available: true, sort_order: 0 };
      return s;
    });

    sizesGrid.innerHTML = normSizes
      .sort((a, b) => a.sort_order - b.sort_order)
      .map(s => `
        <button class="size-btn ${!s.is_available ? 'unavailable' : ''}"
          data-size="${s.size}"
          ${!s.is_available ? 'disabled' : ''}
          onclick="selectSize(this, '${s.size}')">
          ${s.size}
        </button>
      `).join('');
  }

  window.selectSize = function(btn, size) {
    if (btn.classList.contains('unavailable')) return;
    document.querySelectorAll('.size-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    selectedSize = size;
  };

  // Load product
  async function loadProduct() {
    if (!productId) {
      productName.textContent = 'Товар не найден';
      return;
    }

    try {
      const res = await fetch(`${API}/products/${productId}`);
      if (!res.ok) throw new Error('Not found');
      const p = await res.json();

      document.title = `${p.name} — XTEMPLS`;
      productName.textContent = p.name;
      if (p.is_featured) {
        const exist = document.getElementById('newBadgeDetail');
        if (!exist && productName.parentElement) {
          const badge = document.createElement('span');
          badge.id = 'newBadgeDetail';
          badge.className = 'new-badge new-badge-inline';
          badge.textContent = 'Новинка';
          productName.insertAdjacentElement('afterend', badge);
        }
      }

      // Category
      if (p.category) {
        categoryName.textContent = p.category.name;
        categoryChip.style.display = 'flex';
      }

      // Prices
      const disc = discount(p.price, p.old_price);
      detailPrices.innerHTML = `
        <span class="detail-price">${fmt(p.price)}</span>
        ${p.old_price ? `<span class="detail-old-price">${fmt(p.old_price)}</span>` : ''}
        ${disc ? `<span class="detail-discount">-${disc}%</span>` : ''}
      `;

      // Stock
      renderStock(p.stock_status);

      // Images
      images = p.images
        .sort((a, b) => (b.is_primary ? 1 : 0) - (a.is_primary ? 1 : 0) || a.sort_order - b.sort_order)
        .map(i => i.url);

      if (images.length > 0) {
        showImage(0);

        // Arrows (desktop) — injected into #gallery
        if (images.length > 1) {
          const galleryWrap = document.getElementById('gallery');
          if (galleryWrap && !galleryWrap.querySelector('.gallery-arrow-prev')) {
            const prevBtn = document.createElement('button');
            prevBtn.className = 'gallery-arrow gallery-arrow-prev';
            prevBtn.innerHTML = '‹';
            prevBtn.onclick = () => showImage(currentImg - 1);
            const nextBtn = document.createElement('button');
            nextBtn.className = 'gallery-arrow gallery-arrow-next';
            nextBtn.innerHTML = '›';
            nextBtn.onclick = () => showImage(currentImg + 1);
            galleryWrap.appendChild(prevBtn);
            galleryWrap.appendChild(nextBtn);
          }
        }

        // Click on main image → lightbox
        if (galleryMain) {
          galleryMain.onclick = () => openLightbox(currentImg);
        }

        // Dots
        if (images.length > 1) {
          galleryDots.innerHTML = images.map((_, i) =>
            `<div class="gallery-dot ${i === 0 ? 'active' : ''}" onclick="showImage(${i})"></div>`
          ).join('');
          window.showImage = showImage;
        }

        // Thumbs
        if (images.length > 1) {
          galleryThumbs.innerHTML = images.map((url, i) => `
            <div class="thumb ${i === 0 ? 'active' : ''}" onclick="showImage(${i})">
              <img src="${url}" alt="" loading="lazy" />
            </div>
          `).join('');
        }
      }

      // Размеры для выбора: product_sizes имеют приоритет. Если их нет, но
      // задана размерная сетка — строим кнопки из её ключей (S, M, L ...).
      // Так покупатель всегда может выбрать размер, даже если менеджер
      // заполнил только размерную сетку.
      let chart = p.size_chart;
      if (typeof chart === 'string') {
        try { chart = JSON.parse(chart); } catch (e) { chart = null; }
      }
      const hasChart = chart && Object.keys(chart).length > 0;

      if (p.sizes && p.sizes.length > 0) {
        effectiveSizes = p.sizes;
      } else if (hasChart) {
        effectiveSizes = Object.keys(chart).map((size, i) => ({
          size, is_available: true, sort_order: i,
        }));
      } else {
        effectiveSizes = [];
      }
      renderSizes(effectiveSizes);

      // Size chart link
      const sizeChartLink = document.getElementById('sizeChartLink');
      if (sizeChartLink) {
        if (hasChart) {
          sizeChartLink.style.display = 'inline-flex';
          sizeChartLink.onclick = () => openSizeChart(chart);
        } else {
          sizeChartLink.style.display = 'none';
        }
      }

      // Description
      if (p.description) {
        productDesc.textContent = p.description;
        descBlock.style.display = 'block';
      }

      // CTA buttons
      const ctaBlock = document.getElementById('ctaBlock');
      const addToCartBtn = document.getElementById('addToCartBtn');
      const contactBtn = document.getElementById('contactBtn');

      if (ctaBlock) ctaBlock.style.display = 'block';

      if (addToCartBtn) {
        addToCartBtn.onclick = () => {
          if (p.stock_status === 'out_of_stock') {
            showToast('Товар отсутствует в наличии');
            return;
          }
          if (effectiveSizes.length > 0 && !selectedSize) {
            showToast('Пожалуйста, выберите размер');
            return;
          }
          addToCart(p, selectedSize);
        };
      }

      const favDetail = document.getElementById('favDetailBtn');
      if (favDetail) {
        await loadFavoriteIds();
        const on = window._favIds.has(p.id);
        favDetail.dataset.label = '1';
        favDetail.dataset.labelOff = '♡ В избранное';
        favDetail.dataset.labelOn = '♥ В избранном';
        favDetail.classList.toggle('is-fav', on);
        favDetail.textContent = on ? favDetail.dataset.labelOn : favDetail.dataset.labelOff;
        favDetail.onclick = () => toggleFavorite(p.id, favDetail);
      }

      // contactBtn removed — manager contact is available via Telegram button in cart

    } catch (e) {
      productName.textContent = 'Товар не найден';
      console.error(e);
    }
  }

  loadProduct();
}

// ── Homepage novelties ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const section = document.getElementById('homeNovelties');
  const row = document.getElementById('homeNoveltiesRow');
  if (!section || !row) return;
  try {
    await loadFavoriteIds();
    const res = await fetch(`${API}/products/?featured=true&per_page=8`);
    if (!res.ok) return;
    const data = await res.json();
    if (!data.items || !data.items.length) return;
    section.style.display = '';
    row.innerHTML = data.items.map(p => {
      const img = p.primary_image
        ? `<img src="${p.primary_image}" alt="${p.name}" loading="lazy">`
        : `<div class="card-placeholder" style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:#f0f0f0;">🛍</div>`;
      return `<a class="home-new-card" href="/product.html?id=${p.id}">
        <div class="home-new-img">${newBadgeHtml(p)}${favBtnHtml(p.id)}${img}</div>
        <div class="home-new-name">${p.name}</div>
        <div class="home-new-price">${fmt(p.price)}</div>
      </a>`;
    }).join('');
  } catch (e) {
    console.error('Failed to load novelties', e);
  }
});
