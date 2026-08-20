const moneyFmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const numFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });

const state = {
  selectedService: null,
  activeUf: "SC",
  activeWork: null,
  selectedUnifiedItem: null,
};

function $(selector) {
  return document.querySelector(selector);
}

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Erro na requisicao");
  return data;
}

function money(value) {
  return moneyFmt.format(Number(value || 0));
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setStatus(text) {
  $("#status").textContent = text;
}

async function loadSummary() {
  const data = await api("/api/summary");
  $("#statInputs").textContent = data.inputs;
  $("#statServices").textContent = data.services;
  $("#statProjects").textContent = data.projects;
  $("#statUnified").textContent = data.unified_items || 0;
  state.activeUf = data.active_uf || "SC";
  state.activeWork = data.active_work || null;
  updateActiveUfUi();
  const importedAt = data.metadata.find((item) => item.key === "imported_at")?.value || "-";
  setStatus(`Banco local: ${data.db_path} | Importado em ${importedAt}`);
}

function updateActiveUfUi() {
  const activeUf = state.activeUf || "SC";
  const activeUfSelect = $("#activeUf");
  const activeUfBadge = $("#activeUfBadge");
  if (activeUfSelect) activeUfSelect.value = activeUf;
  if (activeUfBadge) activeUfBadge.textContent = `UF da obra: ${activeUf}`;
}

function activateView(name) {
  document.querySelectorAll(".nav").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === name));
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  $(`#view-${name}`).classList.add("active");
  if (name === "taxes") loadTaxes();
  if (name === "projects") loadProjects();
  if (name === "bases") loadBases();
  if (name === "equivalences") loadEquivalences();
}

async function loadServices() {
  const q = encodeURIComponent($("#serviceSearch").value.trim());
  const rows = await api(`/api/services?q=${q}`);
  $("#serviceList").innerHTML = rows
    .map(
      (row) => `
        <button class="service-row ${state.selectedService === row.code ? "active" : ""}" data-code="${esc(row.code)}">
          <span class="code">${esc(row.code)}</span>
          <span>
            <span class="name">${esc(row.name)}</span>
            <span class="muted">${esc(row.item || "-")} | ${esc(row.access_code || "-")} | ${esc(row.unit || "-")}</span>
          </span>
          <span class="money">${money(row.legacy_price)}</span>
        </button>
      `
    )
    .join("");
  document.querySelectorAll(".service-row").forEach((button) => {
    button.addEventListener("click", () => loadServiceDetail(button.dataset.code));
  });
}

async function loadServiceDetail(code) {
  state.selectedService = code;
  const data = await api(`/api/service?code=${encodeURIComponent(code)}`);
  const diffClass = Math.abs(data.totals.difference) > 0.05 ? "negative" : "";
  $("#serviceDetail").innerHTML = `
    <div class="detail-head">
      <h2>${esc(data.service.code)} - ${esc(data.service.name)}</h2>
      <div class="muted">
        Item ${esc(data.service.item || "-")} | Unidade ${esc(data.service.unit || "-")} |
        Acesso ${esc(data.service.access_code || "-")} | Divisor ${esc(data.parameter.unit)} ${numFmt.format(data.parameter.value)}
      </div>
    </div>
    <div class="totals">
      <div><span class="muted">Material</span><b>${money(data.totals.material)}</b></div>
      <div><span class="muted">Mao de obra</span><b>${money(data.totals.labor)}</b></div>
      <div><span class="muted">Calculado</span><b>${money(data.totals.calculated)}</b></div>
      <div><span class="muted">Antigo / diferenca</span><b class="${diffClass}">${money(data.totals.legacy)} / ${money(data.totals.difference)}</b></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Ref</th>
          <th>Insumo</th>
          <th>Acesso</th>
          <th class="num">Qtd</th>
          <th class="num">Preco</th>
          <th class="num">Taxa</th>
          <th class="num">Total</th>
        </tr>
      </thead>
      <tbody>
        ${data.items
          .map(
            (item) => `
              <tr>
                <td>${item.position}</td>
                <td>
                  <b>${esc(item.code)}</b> ${esc(item.name)}
                  <div>${item.applied_taxes.map((tax) => `<span class="badge">${esc(tax.code)} ${numFmt.format(tax.percent)}%</span>`).join("")}</div>
                </td>
                <td>${esc(item.access_code || "-")}</td>
                <td class="num">${numFmt.format(item.quantity)} ${esc(item.unit || "")}</td>
                <td class="num">${money(item.price)}</td>
                <td class="num">${numFmt.format(item.tax_percent)}%</td>
                <td class="num">${money(item.total)}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
  loadServices();
}

async function loadInputs() {
  const q = encodeURIComponent($("#inputSearch").value.trim());
  const rows = await api(`/api/inputs?q=${q}`);
  $("#inputList").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Codigo</th>
          <th>Nome</th>
          <th>Acesso</th>
          <th>Un</th>
          <th class="num">Preco</th>
          <th>Data</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <td><b>${esc(row.code)}</b></td>
                <td>${esc(row.name)}</td>
                <td>${esc(row.access_code || "-")}</td>
                <td>${esc(row.unit || "-")}</td>
                <td class="num">${money(row.price)}</td>
                <td>${esc(row.price_date || "-")}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function loadTaxes() {
  const rows = await api("/api/taxes");
  $("#taxList").innerHTML = `
    <table>
      <thead><tr><th>Codigo</th><th>Nome</th><th>Acesso</th><th class="num">Percentual</th></tr></thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <td><b>${esc(row.code)}</b></td>
                <td>${esc(row.name)}</td>
                <td>${esc(row.access_code || "-")}</td>
                <td class="num">${numFmt.format(row.percent)}%</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function loadProjects() {
  const context = await api("/api/app-context");
  state.activeUf = context.active_uf || "SC";
  updateActiveUfUi();
  await loadWorks();
  const rows = await api("/api/projects");
  $("#projectList").innerHTML = `
    <table>
      <thead>
        <tr><th>Cod</th><th>Obra</th><th>Cliente</th><th>Cidade</th><th>Data</th><th class="num">Valor</th></tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <td><b>${row.id}</b></td>
                <td>${esc(row.name)}</td>
                <td>${esc(row.client)}</td>
                <td>${esc(row.city)} ${esc(row.state || "")}</td>
                <td>${esc(row.budget_date || "-")}</td>
                <td class="num">${money(row.total_value)}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function loadWorks() {
  const data = await api("/api/works");
  state.activeWork = data.active;
  if (!data.active) {
    $("#activeWork").innerHTML = "Nenhuma obra moderna criada ainda.";
    $("#workItems").innerHTML = "";
    return;
  }
  state.activeUf = data.active.uf || state.activeUf;
  updateActiveUfUi();
  $("#activeWork").innerHTML = `
    <b>${esc(data.active.name)}</b>
    <span class="muted"> | Cliente: ${esc(data.active.client || "-")} | UF: ${esc(data.active.uf)}</span>
  `;
  const items = await api(`/api/work-items?work_id=${data.active.id}`);
  $("#workItems").innerHTML = `
    <table>
      <thead><tr><th>Codigo</th><th>Descricao</th><th>Base</th><th class="num">Qtd</th><th class="num">Unitario</th><th class="num">Total</th></tr></thead>
      <tbody>
        ${items.items.map((row) => `
          <tr>
            <td><b>${esc(row.external_code)}</b></td>
            <td>${esc(row.description)} <span class="muted">(${esc(row.unit || "-")})</span></td>
            <td>${esc(row.source_name)}</td>
            <td class="num">${numFmt.format(row.quantity)}</td>
            <td class="num">${money(row.unit_price)}</td>
            <td class="num">${money(row.total_price)}</td>
          </tr>
        `).join("")}
        <tr><td colspan="5" class="num"><b>Total</b></td><td class="num"><b>${money(items.total)}</b></td></tr>
      </tbody>
    </table>
  `;
}

async function createWork() {
  const name = $("#newWorkName").value.trim();
  const client = $("#newWorkClient").value.trim();
  const uf = $("#activeUf").value;
  if (!name) {
    setStatus("Digite o nome da obra.");
    return;
  }
  const result = await api("/api/works", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, client, uf }),
  });
  state.activeWork = result.work;
  state.activeUf = result.work.uf;
  updateActiveUfUi();
  $("#newWorkName").value = "";
  $("#newWorkClient").value = "";
  await loadWorks();
  setStatus(`Obra criada: ${result.work.name} (${result.work.uf})`);
}

async function saveActiveUf() {
  const activeUf = $("#activeUf").value;
  const result = await api("/api/app-context", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active_uf: activeUf }),
  });
  state.activeUf = result.active_uf;
  updateActiveUfUi();
  setStatus(`UF da obra definida como ${state.activeUf}. As composicoes serao calculadas por esta UF.`);
}

async function loadBases() {
  updateActiveUfUi();
  const sources = await api("/api/sources");
  $("#sourceFilter").innerHTML = `<option value="">Todas as bases</option>` + sources.map((row) => (
    `<option value="${row.id}">${esc(row.name)} (${row.items})</option>`
  )).join("");
  $("#sourceList").innerHTML = `
    <table>
      <thead><tr><th>Base</th><th>Tipo</th><th>Referencia</th><th class="num">Itens</th></tr></thead>
      <tbody>
        ${sources.map((row) => `
          <tr>
            <td><b>${esc(row.name)}</b><div class="muted">${esc(row.code)}</div></td>
            <td>${esc(row.kind)}</td>
            <td>${esc(row.reference || "-")}</td>
            <td class="num">${row.items}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  await loadUnifiedItems();
}

async function loadUnifiedItems() {
  const q = encodeURIComponent($("#unifiedSearch").value.trim());
  const sourceId = encodeURIComponent($("#sourceFilter").value);
  const kind = encodeURIComponent($("#kindFilter").value);
  const rows = await api(`/api/unified-items?q=${q}&source_id=${sourceId}&kind=${kind}`);
  $("#unifiedList").innerHTML = rows.map((row) => `
    <button class="service-row" data-id="${row.id}">
      <span class="code">${esc(row.external_code)}</span>
      <span>
        <span class="name">${esc(row.description)}</span>
        <span class="muted">${esc(row.source_name)} | ${esc(row.kind)} | ${esc(row.group_name || "-")} | ${esc(row.unit || "-")}</span>
      </span>
      <span class="money">${money(row.price)}</span>
    </button>
  `).join("");
  document.querySelectorAll("#unifiedList .service-row").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("#unifiedList .service-row").forEach((row) => row.classList.remove("active"));
      button.classList.add("active");
      loadUnifiedDetail(button.dataset.id);
    });
  });
}

async function loadUnifiedDetail(id) {
  state.selectedUnifiedItem = Number(id);
  const data = await api(`/api/unified-item?id=${encodeURIComponent(id)}`);
  const uf = state.activeUf || "SC";
  const calc = data.item.kind === "COMPOSICAO"
    ? await api(`/api/calculate-composition?id=${encodeURIComponent(id)}`)
    : null;
  const diff = calc ? calc.calculated_total - (calc.direct_price || 0) : 0;
  $("#unifiedDetail").innerHTML = `
    <div class="detail-head">
      <h2>${esc(data.item.external_code)} - ${esc(data.item.description)}</h2>
      <div class="muted">${esc(data.item.source_name)} | ${esc(data.item.kind)} | ${esc(data.item.group_name || "-")} | ${esc(data.item.unit || "-")}</div>
    </div>
    ${calc ? `
      <div class="totals">
        <div><span class="muted">UF de calculo</span><b>${esc(uf)}</b></div>
        <div><span class="muted">Preco tabela</span><b>${money(calc.direct_price)}</b></div>
        <div><span class="muted">Calculado pelos insumos</span><b>${money(calc.calculated_total)}</b></div>
        <div><span class="muted">Diferenca</span><b class="${Math.abs(diff) > 0.05 ? "negative" : ""}">${money(diff)}</b></div>
      </div>
    ` : ""}
    <div class="panel-title">Classificacao gerencial</div>
    <table>
      <tbody>
        ${data.classifications.map((row) => `
          <tr>
            <td><b>${esc(row.dimension)}</b></td>
            <td>${esc(row.option_name)}</td>
            <td class="muted">${esc(row.source)} ${row.confidence ? Math.round(row.confidence * 100) + "%" : ""}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
    <div class="panel-title">Precos</div>
    <table>
      <thead><tr><th>UF</th><th>Referencia</th><th class="num">Preco</th></tr></thead>
      <tbody>
        ${data.prices.slice(0, 12).map((row) => `
          <tr><td>${esc(row.uf || "-")}</td><td>${esc(row.reference || "-")}</td><td class="num">${money(row.price)}</td></tr>
        `).join("")}
      </tbody>
    </table>
    ${calc ? `
      <div class="panel-title">Composicao analitica calculada por ${esc(uf)}</div>
      <table>
        <thead>
          <tr>
            <th>Tipo</th>
            <th>Codigo</th>
            <th>Descricao</th>
            <th class="num">Coef.</th>
            <th class="num">Preco unit.</th>
            <th class="num">Total</th>
          </tr>
        </thead>
        <tbody>
          ${calc.items.map((row) => `
            <tr>
              <td>${esc(row.kind)}</td>
              <td><b>${esc(row.code)}</b></td>
              <td>${esc(row.description)}</td>
              <td class="num">${numFmt.format(row.coefficient || 0)} ${esc(row.unit || "")}</td>
              <td class="num">${money(row.calculated_unit_price)}</td>
              <td class="num">${money(row.line_total)}</td>
            </tr>
            ${row.children && row.children.length ? row.children.map((child) => `
              <tr>
                <td class="muted">↳ ${esc(child.kind)}</td>
                <td class="muted">${esc(child.code)}</td>
                <td class="muted">${esc(child.description)}</td>
                <td class="num muted">${numFmt.format(child.coefficient || 0)} ${esc(child.unit || "")}</td>
                <td class="num muted">${money(child.calculated_unit_price)}</td>
                <td class="num muted">${money(child.line_total)}</td>
              </tr>
            `).join("") : ""}
          `).join("")}
        </tbody>
      </table>
    ` : data.components.length ? `<div class="panel-title">Composicao</div>` : ""}
  `;
}

async function addSelectedToWork() {
  if (!state.selectedUnifiedItem) {
    setStatus("Selecione uma composicao ou insumo antes de adicionar.");
    return;
  }
  if (!state.activeWork) {
    setStatus("Crie uma obra na aba Obras antes de adicionar itens.");
    return;
  }
  const quantity = Number($("#addQuantity").value || 1);
  await api("/api/work-items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ work_id: state.activeWork.id, item_id: state.selectedUnifiedItem, quantity }),
  });
  setStatus("Item adicionado na obra ativa.");
}

async function loadEquivalences() {
  const status = encodeURIComponent($("#equivStatus").value);
  const q = encodeURIComponent($("#equivSearch").value.trim());
  const data = await api(`/api/equivalences?status=${status}&q=${q}`);
  $("#equivSummary").innerHTML = data.summary.length
    ? data.summary.map((row) => `<span class="badge">${esc(row.status)}: ${row.total}</span>`).join("")
    : "Nenhuma equivalencia gerada.";
  $("#equivList").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Status</th>
          <th>SOO antigo</th>
          <th>SINAPI sugerido</th>
          <th class="num">Score</th>
          <th>Escolha</th>
        </tr>
      </thead>
      <tbody>
        ${data.rows.map((row) => `
          <tr>
            <td>${esc(row.status)}</td>
            <td>
              <b>${esc(row.legacy_code)}</b> ${esc(row.legacy_description)}
              <div class="muted">Unidade: ${esc(row.legacy_unit || "-")}</div>
            </td>
            <td>
              <b>${esc(row.sinapi_code || "-")}</b> ${esc(row.sinapi_description || row.notes || "Sem sugestao")}
              <div class="muted">Unidade: ${esc(row.sinapi_unit || "-")}</div>
            </td>
            <td class="num">${row.match_score == null ? "-" : Math.round(row.match_score * 100) + "%"}</td>
            <td>
              <input class="equiv-code" data-id="${row.id}" value="${esc(row.sinapi_code || "")}" placeholder="Codigo SINAPI">
              <button class="equiv-approve" data-id="${row.id}">Aprovar</button>
              <button class="equiv-reject" data-id="${row.id}">Rejeitar</button>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  document.querySelectorAll(".equiv-approve").forEach((button) => {
    button.addEventListener("click", () => updateEquivalence(button.dataset.id, "approved"));
  });
  document.querySelectorAll(".equiv-reject").forEach((button) => {
    button.addEventListener("click", () => updateEquivalence(button.dataset.id, "rejected"));
  });
}

async function updateEquivalence(id, status) {
  const input = document.querySelector(`.equiv-code[data-id="${id}"]`);
  const sinapiCode = input ? input.value.trim() : "";
  await api("/api/equivalence-status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, status, sinapi_code: sinapiCode }),
  });
  setStatus(`Equivalencia ${status === "approved" ? "aprovada" : "atualizada"}.`);
  await loadEquivalences();
}

async function reimport() {
  setStatus("Reimportando DBFs...");
  await api("/api/reimport", { method: "POST" });
  await loadSummary();
  await loadServices();
  await loadInputs();
}

function bindEvents() {
  document.querySelectorAll(".nav").forEach((button) => {
    button.addEventListener("click", () => activateView(button.dataset.view));
  });
  $("#serviceSearchBtn").addEventListener("click", loadServices);
  $("#serviceSearch").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadServices();
  });
  $("#inputSearchBtn").addEventListener("click", loadInputs);
  $("#inputSearch").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadInputs();
  });
  $("#reimport").addEventListener("click", reimport);
  $("#unifiedSearchBtn").addEventListener("click", loadUnifiedItems);
  $("#unifiedSearch").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadUnifiedItems();
  });
  $("#sourceFilter").addEventListener("change", loadUnifiedItems);
  $("#kindFilter").addEventListener("change", loadUnifiedItems);
  $("#createWorkBtn").addEventListener("click", createWork);
  $("#activeUf").addEventListener("change", () => {
    state.activeUf = $("#activeUf").value;
    updateActiveUfUi();
  });
  $("#addToWorkBtn").addEventListener("click", addSelectedToWork);
  $("#equivSearchBtn").addEventListener("click", loadEquivalences);
  $("#equivSearch").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadEquivalences();
  });
  $("#equivStatus").addEventListener("change", loadEquivalences);
}

async function boot() {
  bindEvents();
  await loadSummary();
  await loadServices();
  await loadInputs();
}

boot().catch((error) => {
  console.error(error);
  setStatus(error.message);
});
