/* ─── Mini App JavaScript ─── */

const API = '/api';
const tg = window.Telegram?.WebApp;

// Public site config (manager username, contacts) loaded from backend — no hardcoding.
let siteConfig = { manager_username: '', contact_telegram: '' };

// Init Telegram WebApp
if (tg) {
  tg.ready();
  tg.expand();
  document.documentElement.style.setProperty('--tg-bg', tg.backgroundColor || '#0a0a0a');
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
}

// ── Cart State (localStorage) ─────────────────────────────────────────────────

let cart = JSON.parse(localStorage.getItem('xtempls_cart') || '[]');

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
  // Pre-fill username
  const contactEl = document.getElementById('chkContact');
  if (contactEl && tg?.initDataUnsafe?.user?.username) {
    contactEl.value = '@' + tg.initDataUnsafe.user.username;
  }
  // Reset promo
  const promoInput = document.getElementById('chkPromo');
  const promoMsg = document.getElementById('promoMsg');
  if (promoInput) promoInput.value = '';
  if (promoMsg) { promoMsg.textContent = ''; promoMsg.className = 'promo-msg'; }
  window._appliedPromo = null;
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

function updateCheckoutTotal() {
  const totalEl = document.getElementById('checkoutTotal');
  const discEl = document.getElementById('checkoutDiscount');
  const promo = window._appliedPromo;
  const base = cartTotal();
  if (promo) {
    const disc = Math.round(base * promo.discount_percent / 100);
    const final = base - disc;
    if (discEl) discEl.innerHTML = `<span class="promo-discount-line">Скидка ${promo.discount_percent}%: −${fmt(disc)}</span>`;
    if (totalEl) totalEl.textContent = fmt(final);
  } else {
    if (discEl) discEl.innerHTML = '';
    if (totalEl) totalEl.textContent = fmt(base);
  }
}

window.applyPromo = async function() {
  const code = document.getElementById('chkPromo')?.value.trim();
  const msg = document.getElementById('promoMsg');
  if (!code) return;
  if (msg) msg.textContent = 'Проверяем...';
  try {
    const res = await fetch(`${API}/promo/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });
    const data = await res.json();
    if (data.valid) {
      window._appliedPromo = { code, discount_percent: data.discount_percent };
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

window.submitOrder = async function() {
  const name = document.getElementById('chkName')?.value.trim();
  const contact = document.getElementById('chkContact')?.value.trim();
  const comment = document.getElementById('chkComment')?.value.trim();

  if (!name || !contact) {
    showToast('Заполните имя и контакт');
    return;
  }

  if (cart.length === 0) {
    showToast('Корзина пуста');
    return;
  }

  const btn = document.getElementById('submitOrderBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Отправка...'; }

  try {
    const body = {
      customer_name: name,
      customer_contact: contact,
      comment: comment || null,
      tg_init_data: tg?.initData || null,
      promo_code: window._appliedPromo?.code || null,
      items: cart.map(i => ({
        product_id: i.product_id,
        size: i.size,
        quantity: i.quantity,
      }))
    };

    const res = await fetch(`${API}/orders/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || 'Ошибка отправки заказа');
      return;
    }

    // Clear cart
    cart = [];
    saveCart();
    window._appliedPromo = null;

    // Show success
    const checkoutBody = document.getElementById('checkoutModal')?.querySelector('.cart-body');
    const checkoutFooter = document.getElementById('checkoutModal')?.querySelector('.cart-footer');
    if (checkoutBody) {
      checkoutBody.innerHTML = `
        <div class="order-success">
          <div class="success-icon">✅</div>
          <div class="success-title">Заказ принят!</div>
          <div class="success-text">
            Спасибо, ${name}!<br/>
            Менеджер свяжется с вами по контакту<br/>
            <strong>${contact}</strong>
          </div>
        </div>
      `;
    }
    if (checkoutFooter) checkoutFooter.style.display = 'none';

    // Auto-close after 3s
    setTimeout(() => {
      const checkoutModal = document.getElementById('checkoutModal');
      const checkoutBackdrop = document.getElementById('checkoutBackdrop');
      if (checkoutModal) checkoutModal.classList.remove('open');
      if (checkoutBackdrop) { checkoutBackdrop.classList.remove('open'); checkoutBackdrop.style.display = '';
      }
      document.body.style.overflow = '';
    }, 3500);

  } catch (e) {
    showToast('Ошибка соединения');
    console.error(e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Отправить заказ'; }
  }
};

// ── UI Injection ──────────────────────────────────────────────────────────────

function injectCartUI() {
  if (document.getElementById('cartModal')) return;

  const html = `
    <!-- Cart Backdrop -->
    <div id="cartBackdrop" class="cart-backdrop" onclick="closeCart()"></div>

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
            <input type="text" id="chkName" class="chk-input" required placeholder="Иван Иванов" />
            <label class="chk-label">Телефон или Telegram</label>
            <input type="text" id="chkContact" class="chk-input" required placeholder="@username или +7..." />
            <label class="chk-label">Промокод</label>
            <div class="promo-row">
              <input type="text" id="chkPromo" class="chk-input promo-input" placeholder="Введите промокод" />
              <button type="button" class="promo-apply-btn" onclick="applyPromo()">Применить</button>
            </div>
            <div id="promoMsg" class="promo-msg"></div>
            <label class="chk-label">Комментарий к заказу</label>
            <textarea id="chkComment" class="chk-input" placeholder="Город доставки, пожелания и т.д." rows="2"></textarea>
            <button type="submit" id="submitOrderBtn" class="checkout-submit-btn">Отправить заказ</button>
          </form>
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

injectCartUI();
updateCartBadge();


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
  if (tg) {
    tg.BackButton.show();
    tg.BackButton.onClick(() => {
      window.location.href = '/';
    });
  }

  let currentCategory = '';
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
        <div class="s-services-type-5__item-content sb-m-clear-bottom" style="cursor: pointer;" onclick="openProduct('${p.slug}', ${p.id})">
          <div class="s-services-type-5__image sb-image-square">
            ${imgHtml}
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
            ${badge}${imgHtml}
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

  function selectCategory(id) {
    currentCategory = id;
    currentPage = 1;
    allProducts = [];
    document.querySelectorAll('.cat-btn').forEach(b => {
      if (String(b.dataset.id) === String(id)) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });
    const showFeatured = !currentCategory && !currentSearch;
    if (featuredSection) featuredSection.style.display = showFeatured ? 'block' : 'none';
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
      if (currentSearch) params.append('search', currentSearch);

      const res = await fetch(`${API}/products/?${params}`);
      if (!res.ok) throw new Error('API error');
      const data = await res.json();

      totalPages = data.pages;
      allProducts = reset ? data.items : [...allProducts, ...data.items];

      if (reset) {
        if (titleEl) {
          let activeCatName = 'Каталог';
          if (currentCategory) {
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
           const showFeatured = !currentCategory && !currentSearch;
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
        const showFeatured = !currentCategory && !currentSearch;
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
    await loadCategories();
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
      const submitBtn = designForm.querySelector('input[type="submit"]');

      if (!nameInput || !phoneInput) return;

      const name = nameInput.value.trim();
      const phone = phoneInput.value.trim();

      if (!name || !phone) {
        showToast('Пожалуйста, заполните все поля');
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
          items: [] // Empty items for design request
        };

        const res = await fetch(`${API}/orders/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });

        if (!res.ok) {
          throw new Error('Server error');
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
        if (errorMsg) errorMsg.style.display = 'block';
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

  // Back navigation
  backBtn.addEventListener('click', () => {
    if (tg?.BackButton?.isVisible) {
      tg.BackButton.hide();
    }
    history.back();
  });

  // Telegram back button
  if (tg) {
    tg.BackButton.show();
    tg.BackButton.onClick(() => history.back());
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

      // Sizes
      renderSizes(p.sizes);

      // Size chart link
      const sizeChartLink = document.getElementById('sizeChartLink');
      if (sizeChartLink) {
        let chart = p.size_chart;
        if (typeof chart === 'string') {
          try { chart = JSON.parse(chart); } catch (e) { chart = null; }
        }
        if (chart && Object.keys(chart).length > 0) {
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
          if (p.sizes && p.sizes.length > 0 && !selectedSize) {
            showToast('Пожалуйста, выберите размер');
            return;
          }
          addToCart(p, selectedSize);
        };
      }

      // contactBtn removed — manager contact is available via Telegram button in cart

    } catch (e) {
      productName.textContent = 'Товар не найден';
      console.error(e);
    }
  }

  loadProduct();
}
