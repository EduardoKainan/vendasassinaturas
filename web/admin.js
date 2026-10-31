const $ = (selector) => document.querySelector(selector);
const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

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

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "data indisponível" : date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function setError(message = "") {
  const node = $("#adminError");
  node.textContent = message;
  node.classList.toggle("hidden", !message);
}

function renderProducts(products) {
  $("#productCountLabel").textContent = `${products.length} produto${products.length === 1 ? "" : "s"}`;
  $("#productsTableBody").innerHTML = products.length ? products.map((product) => {
    const stock = Math.max(0, Number(product.stock) || 0);
    const stockClass = stock === 0 ? "out" : stock <= 5 ? "low" : "";
    const status = stock === 0 ? "Esgotado" : product.active ? "Disponível" : "Inativo";
    return `<tr>
      <td><span class="table-product">${escapeHtml(product.name)}</span><span class="table-sub">${escapeHtml(product.id)}</span></td>
      <td>${escapeHtml(product.category)}</td>
      <td>${Number(product.duration_days) || 0} dias</td>
      <td>${formatMoney(product.price_cents)}</td>
      <td><span class="stock-number ${stockClass}">${stock}</span> un.</td>
      <td><span class="status-pill ${stock === 0 ? "out" : ""}">${status}</span></td>
    </tr>`;
  }).join("") : '<tr><td colspan="6" class="table-loading">Nenhum produto no catálogo demo.</td></tr>';
}

function renderOrders(orders) {
  $("#ordersCountLabel").textContent = `${orders.length} pedido${orders.length === 1 ? "" : "s"}`;
  $("#ordersList").innerHTML = orders.length ? orders.map((order) => {
    const details = order.items.map((item) => `${escapeHtml(item.name)} × ${Number(item.quantity) || 0}`).join(" · ");
    return `<article class="order-card">
      <div><div class="order-id">${escapeHtml(order.id)}<span class="order-date">${formatDate(order.created_at)}</span></div><div class="order-lines">${details}</div></div>
      <div class="order-total"><strong>${formatMoney(order.total_cents)}</strong><span class="order-status">DEMO · NÃO PAGO</span></div>
    </article>`;
  }).join("") : '<div class="orders-empty">Ainda não há pedidos de demonstração. Faça um teste pela loja para ver o fluxo completo.</div>';
}

async function loadDashboard() {
  const button = $("#refreshDashboard");
  button.disabled = true;
  button.querySelector("span").textContent = "Atualizando…";
  setError();
  try {
    const [summaryResponse, ordersResponse] = await Promise.all([
      fetch("/api/admin/dashboard", { cache: "no-store" }),
      fetch("/api/admin/orders", { cache: "no-store" }),
    ]);
    const summaryData = await summaryResponse.json();
    const ordersData = await ordersResponse.json();
    if (!summaryResponse.ok || !ordersResponse.ok) throw new Error("Não foi possível carregar o painel demo.");
    if (summaryData.summary.mode !== "demo" || ordersData.mode !== "demo") throw new Error("Este painel só aceita dados demo nesta versão.");
    const summary = summaryData.summary;
    $("#metricProducts").textContent = String(summary.product_count);
    $("#metricStock").textContent = String(summary.stock_units);
    $("#metricOrders").textContent = String(summary.order_count);
    $("#metricPending").textContent = String(summary.pending_count);
    renderProducts(summaryData.products);
    renderOrders(ordersData.orders);
  } catch (error) {
    setError(error.message || "Falha de comunicação com o painel local.");
    $("#productsTableBody").innerHTML = '<tr><td colspan="6" class="table-loading">Catálogo indisponível.</td></tr>';
    $("#ordersList").innerHTML = '<div class="orders-empty">Não foi possível carregar pedidos.</div>';
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Atualizar";
  }
}

$("#refreshDashboard").addEventListener("click", loadDashboard);
loadDashboard();
