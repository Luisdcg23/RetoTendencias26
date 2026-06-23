const form = document.querySelector("#licenseForm");
const licenseJson = document.querySelector("#licenseJson");
const resultBadge = document.querySelector("#resultBadge");
const redirectUrl = document.querySelector("#redirectUrl");
const eventLog = document.querySelector("#eventLog");
const classicStatus = document.querySelector("#classicStatus");
const pqStatus = document.querySelector("#pqStatus");
const revokedStatus = document.querySelector("#revokedStatus");
const loginForm = document.querySelector("#loginForm");
const adminStatus = document.querySelector("#adminStatus");
const licenseRows = document.querySelector("#licenseRows");
const revocationRows = document.querySelector("#revocationRows");
const classicCheck = document.querySelector("#classicCheck");
const pqCheck = document.querySelector("#pqCheck");
const modeCheck = document.querySelector("#modeCheck");
const statusCheck = document.querySelector("#statusCheck");

let adminToken = sessionStorage.getItem("pqlicense_admin_token") || "";

const licenseIdInput = form.querySelector('input[name="license_id"]');
if (licenseIdInput && licenseIdInput.value === "LIC-001") {
  licenseIdInput.value = `LIC-${Date.now().toString().slice(-8)}`;
}

async function api(path, payload, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (options.admin && adminToken) {
    headers.Authorization = `Bearer ${adminToken}`;
  }
  const response = await fetch(path, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.details || body.error || "Error de API");
  }
  return body;
}

async function getApi(path, options = {}) {
  const headers = {};
  if (options.admin && adminToken) {
    headers.Authorization = `Bearer ${adminToken}`;
  }
  const response = await fetch(path, { headers });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || "Error de API");
  }
  return body;
}

async function loadState() {
  const response = await fetch("/api/state");
  const state = await response.json();
  classicStatus.textContent = state.classic_algorithm;
  pqStatus.textContent = state.pq_algorithm;
  revokedStatus.textContent = `${state.revoked_count} revocadas`;
}

function requireAdmin() {
  if (!adminToken) {
    throw new Error("Inicia sesion como administrador para esta accion.");
  }
}

function currentLicense() {
  const raw = licenseJson.value.trim();
  if (!raw) {
    throw new Error("Primero genera o pega una licencia JSON.");
  }
  return JSON.parse(raw);
}

function setResult(result) {
  resultBadge.textContent = result.status;
  resultBadge.className = "badge";
  if (result.status === "valid") {
    resultBadge.classList.add("valid");
  } else if (["expired", "revoked", "wrong_product"].includes(result.status)) {
    resultBadge.classList.add("warning");
  } else {
    resultBadge.classList.add("invalid");
  }
  redirectUrl.textContent = result.redirect_url || "-";
  redirectUrl.href = result.redirect_url || "#";
  const verification = result.verification || {};
  classicCheck.textContent = formatCheck(verification.classical_signature);
  pqCheck.textContent = formatCheck(verification.post_quantum_signature);
  modeCheck.textContent = verification.required_mode || "-";
  statusCheck.textContent = result.details || result.reason || result.status;
  eventLog.textContent = JSON.stringify(result, null, 2);
}

function formatCheck(value) {
  if (value === true) return "valida";
  if (value === false) return "invalida";
  return "-";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
  data.days = Number(data.days);
  data.allowed_devices = Number(data.device_limit);
  data.features = data.features
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  try {
    requireAdmin();
    const created = await api("/api/licenses/generate", data, { admin: true });
    licenseJson.value = JSON.stringify(created.license, null, 2);
    setResult({
      status: "created",
      redirect_url: created.license.payload.redirect_url,
      details: "Licencia firmada generada.",
    });
    await loadState();
    await loadLists();
  } catch (error) {
    setResult({ status: "invalid_format", redirect_url: "", details: error.message });
  }
});

document.querySelector("#validateLicense").addEventListener("click", async () => {
  try {
    const license = currentLicense();
    const result = await api("/api/licenses/validate", {
      license,
      device_fingerprint: license.payload.device_fingerprint || "",
    });
    setResult(result);
  } catch (error) {
    setResult({ status: "invalid_format", redirect_url: "", details: error.message });
  }
});

document.querySelector("#revokeLicense").addEventListener("click", async () => {
  try {
    requireAdmin();
    const license = currentLicense();
    const result = await api(`/api/licenses/${license.payload.license_id}/cancel`, {
      reason: "cancelacion manual desde frontend",
    }, { admin: true });
    setResult({ ...result, redirect_url: license.payload.metadata?.error_url || license.payload.error_url });
    await loadState();
    await loadLists();
  } catch (error) {
    setResult({ status: "invalid_format", redirect_url: "", details: error.message });
  }
});

document.querySelector("#resetKeys").addEventListener("click", async () => {
  try {
    requireAdmin();
    const result = await api("/api/reset-keys", {}, { admin: true });
    licenseJson.value = "";
    setResult({ status: result.status, redirect_url: "", details: "Claves regeneradas." });
    await loadState();
    await loadLists();
  } catch (error) {
    setResult({ status: "invalid_format", redirect_url: "", details: error.message });
  }
});

loadState();

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(loginForm).entries());
  try {
    const result = await api("/api/admin/login", data);
    adminToken = result.token;
    sessionStorage.setItem("pqlicense_admin_token", adminToken);
    adminStatus.textContent = "Sesion admin";
    adminStatus.className = "badge valid";
    eventLog.textContent = JSON.stringify({ status: "authenticated" }, null, 2);
    await loadLists();
  } catch (error) {
    adminToken = "";
    sessionStorage.removeItem("pqlicense_admin_token");
    adminStatus.textContent = "Acceso denegado";
    adminStatus.className = "badge invalid";
    setResult({ status: "invalid_format", redirect_url: "", details: error.message });
  }
});

async function loadLists() {
  await loadRevocations();
  if (!adminToken) {
    licenseRows.innerHTML = '<tr><td colspan="5">Inicia sesion para ver licencias.</td></tr>';
    return;
  }
  try {
    const data = await getApi("/api/licenses", { admin: true });
    licenseRows.innerHTML = data.licenses.length
      ? data.licenses.map((license) => `
          <tr>
            <td>${escapeHtml(license.license_id)}</td>
            <td>${escapeHtml(license.customer_id)}</td>
            <td>${escapeHtml(license.plan)}</td>
            <td>${escapeHtml(license.validation_mode)}</td>
            <td>${escapeHtml(license.expires_at)}</td>
          </tr>
        `).join("")
      : '<tr><td colspan="5">No hay licencias emitidas.</td></tr>';
  } catch (error) {
    licenseRows.innerHTML = `<tr><td colspan="5">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function loadRevocations() {
  try {
    const data = await getApi("/api/licenses/revocations");
    const revoked = data.payload?.revoked || [];
    revocationRows.innerHTML = revoked.length
      ? revoked.map((item) => `
          <tr>
            <td>${escapeHtml(item.license_id)}</td>
            <td>${escapeHtml(item.reason)}</td>
            <td>${escapeHtml(item.revoked_at)}</td>
          </tr>
        `).join("")
      : '<tr><td colspan="3">Sin revocaciones.</td></tr>';
  } catch (error) {
    revocationRows.innerHTML = `<tr><td colspan="3">${escapeHtml(error.message)}</td></tr>`;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.querySelector("#refreshLicenses").addEventListener("click", loadLists);
document.querySelector("#refreshRevocations").addEventListener("click", loadRevocations);

if (adminToken) {
  adminStatus.textContent = "Sesion admin";
  adminStatus.className = "badge valid";
}

loadLists();
