const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const state = { products: [], cart: new Map(), mode: "demo", pendingKey: null };
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    if (char === "&") return "&amp;";
    if (char === "<") return "&lt;";
    if (char === ">") return "&gt;";
    if (char.charCodeAt(0) === 34) return "&quot;";
    return "&#39;";
  });
}

function formatMoney(cents) {
  return money.format((Number(cents) || 0) / 100);
}

function showNotice(message, isError = false) {
  const node = $("#storeNotice");
  node.textContent = message;
  node.classList.toggle("error", isError);
}

function sortedProducts() {
  const query = $("#productSearch").value.trim().toLocaleLowerCase("pt-BR");
  const products = state.products.filter((product) =>
    `${product.name} ${product.category} ${product.description}`.toLocaleLowerCase("pt-BR").includes(query),
  );
  const sort = $("#sortProducts").value;
  if (sort === "price-asc") products.sort((a, b) => a.price_cents - b.price_cents);
  if (sort === "duration-desc") products.sort((a, b) => b.duration_days - a.duration_days);
  if (sort === "featured") products.sort((a, b) => Number(b.featured) - Number(a.featured));
  return products;
}

function productCard(product, index) {
  const stock = Math.max(0, Number(product.stock) || 0);
  const artClass = ["art-standard", "art-plus", "art-family", "art-pro"][index % 4];
  const stockClass = stock === 0 ? "stock-empty" : stock <= 5 ? "stock-low" : "";
  const stockText = stock === 0 ? "Indisponível" : `${stock} un. demo`;
  return `<article class="product-card">
    <div class="product-art ${artClass}"><span class="product-badge">${escapeHtml(product.badge || "Plano demo")}</span><span class="product-glyph" aria-hidden="true">${escapeHtml(String(product.name).slice(0, 1).toUpperCase())}</span></div>
    <div class="product-content">
      <div class="product-meta"><span>${escapeHtml(product.category || "Assinatura")}</span><span>${Number(product.duration_days) || 0} dias</span></div>
      <h3>${escapeHtml(product.name)}</h3>
      <p class="product-description">${escapeHtml(product.description)}</p>
      <div class="product-price-row"><strong class="product-price">${formatMoney(product.price_cents)}<small>/ unidade demo</small></strong><span class="stock-tag ${stockClass}">${stockText}</span></div>
      <div class="product-actions"><input class="quantity-input" type="number" min="1" max="${stock}" value="1" ${stock === 0 ? "disabled" : ""} aria-label="Quantidade de ${escapeHtml(product.name)}"><button class="add-button" type="button" data-add="${escapeHtml(product.id)}" ${stock === 0 ? "disabled" : ""}>${stock === 0 ? "Sem estoque" : "Adicionar +"}</button></div>
    </div>
  </article>`;
}

function renderProducts() {
  const products = sortedProducts();
  const grid = $("#productGrid");
  grid.innerHTML = products.length
    ? products.map(productCard).join("")
    : '<div class="no-results">Nenhum plano encontrado. Tente outro termo.</div>';
  grid.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".product-card");
      const product = state.products.find((item) => item.id === button.dataset.add);
      const requested = Math.max(1, Number(card.querySelector(".quantity-input").value) || 1);
      const current = state.cart.get(product.id)?.quantity || 0;
      const quantity = Math.min(product.stock, current + requested);
      if (quantity === current) {
        showNotice("A quantidade selecionada já atingiu o saldo demo disponível.", true);
        return;
      }
      state.cart.set(product.id, { product, quantity });
      showNotice(`${product.name} adicionado ao carrinho demo.`);
      renderCart();
    });
  });
}

function renderCart() {
  const entries = [...state.cart.values()];
  const totalQuantity = entries.reduce((sum, entry) => sum + entry.quantity, 0);
  const total = entries.reduce((sum, entry) => sum + entry.quantity * entry.product.price_cents, 0);
  $("#headerCartCount").textContent = String(totalQuantity);
  $("#cartCount").textContent = String(totalQuantity);
  $("#cartTotal").textContent = formatMoney(total);
  $("#createOrder").disabled = entries.length === 0;
  $("#cartItems").innerHTML = entries.length ? entries.map(({ product, quantity }) => `
    <div class="cart-line" data-cart-line="${escapeHtml(product.id)}">
      <div><div class="cart-line-title">${escapeHtml(product.name)}</div><div class="cart-line-subtotal">${formatMoney(product.price_cents * quantity)} · ${quantity} un.</div></div>
      <div class="cart-line-controls"><button class="qty-step" type="button" data-action="minus" aria-label="Diminuir quantidade de ${escapeHtml(product.name)}">−</button><span class="cart-line-qty">${quantity}</span><button class="qty-step" type="button" data-action="plus" aria-label="Aumentar quantidade de ${escapeHtml(product.name)}">+</button><button class="remove-line" type="button" data-action="remove" aria-label="Remover ${escapeHtml(product.name)} do carrinho">×</button></div>
    </div>`).join("") : '<div class="empty-cart"><span class="empty-cart-icon">＋</span><strong>Seu carrinho está vazio</strong><p>Adicione um plano para ver o resumo.</p></div>';
  $("#cartItems").querySelectorAll("[data-cart-line]").forEach((line) => {
    line.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
      const id = line.dataset.cartLine;
      const entry = state.cart.get(id);
      if (!entry) return;
      if (button.dataset.action === "remove" || (button.dataset.action === "minus" && entry.quantity === 1)) state.cart.delete(id);
      else if (button.dataset.action === "minus") entry.quantity -= 1;
      else if (button.dataset.action === "plus" && entry.quantity < entry.product.stock) entry.quantity += 1;
      else if (button.dataset.action === "plus") return showNotice("Saldo demo máximo atingido.", true);
      renderCart();
    }));
  });
}

async function submitDemoOrder() {
  if (!state.cart.size) return;
  const button = $("#createOrder");
  button.disabled = true;
  button.textContent = "Registrando demonstração…";
  state.pendingKey ||= crypto.randomUUID();
  try {
    const response = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: state.pendingKey,
        items: [...state.cart.values()].map(({ product, quantity }) => ({ product_id: product.id, quantity })),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Não foi possível registrar o pedido demo.");
    state.cart.clear();
    state.pendingKey = null;
    renderCart();
    showNotice(`Pedido ${result.id} registrado só para demonstração. Nenhuma cobrança ou entrega foi feita.`);
  } catch (error) {
    showNotice(error.message || "Falha ao registrar o pedido demo.", true);
  } finally {
    button.innerHTML = 'Registrar pedido demo <span aria-hidden="true">→</span>';
    button.disabled = state.cart.size === 0;
  }
}

async function loadCatalog() {
  const status = $("#catalogStatus");
  try {
    const response = await fetch("/api/products", { cache: "no-store" });
    const catalog = await response.json();
    if (!response.ok || catalog.mode !== "demo" || catalog.is_demo !== true) throw new Error("O catálogo demo não está disponível.");
    state.products = catalog.products.filter((product) => product.active);
    $("#heroProductCount").textContent = String(state.products.length);
    $("#heroStockCount").textContent = String(state.products.reduce((sum, product) => sum + Number(product.stock || 0), 0));
    status.textContent = `${state.products.length} planos de demonstração · sem integração de fornecedor`;
    renderProducts();
  } catch (error) {
    status.textContent = error.message;
    $("#productGrid").innerHTML = '<div class="no-results">Não foi possível carregar o catálogo local.</div>';
  }
}

$("#productSearch").addEventListener("input", renderProducts);
$("#sortProducts").addEventListener("change", renderProducts);
$("#createOrder").addEventListener("click", submitDemoOrder);
$("#year").textContent = String(new Date().getFullYear());
renderCart();
loadCatalog();
