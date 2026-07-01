const adminToken = sessionStorage.getItem("pqlicense_admin_token") || "";
const currentRol = sessionStorage.getItem("pqlicense_rol") || "";
if (!adminToken) window.location.href = "/login";
if (currentRol && currentRol !== "Admin") window.location.href = "/user";

// ─── Elements ─────────────────────────────────────────────────────────────────
const classicStatus  = document.querySelector("#classicStatus");
const pqStatus       = document.querySelector("#pqStatus");
const revokedStatus  = document.querySelector("#revokedStatus");
const logoutButton   = document.querySelector("#logoutButton");
const licenseForm    = document.querySelector("#licenseForm");
const licenseJson    = document.querySelector("#licenseJson");
const resultBadge    = document.querySelector("#resultBadge");
const redirectUrl    = document.querySelector("#redirectUrl");
const eventLog       = document.querySelector("#eventLog");
const classicCheck   = document.querySelector("#classicCheck");
const pqCheck        = document.querySelector("#pqCheck");
const modeCheck      = document.querySelector("#modeCheck");
const statusCheck    = document.querySelector("#statusCheck");

// ─── Auto-generate license fields ────────────────────────────────────────────
function generateLicenseId() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  const seg = () => Array.from({length: 6}, () => chars[Math.floor(Math.random() * chars.length)]).join('');
  return `LIC-${seg()}-${seg()}`;
}

function generateFingerprint() {
  const hex = () => Math.floor(Math.random() * 0xFFFFFF).toString(16).padStart(6, '0');
  return `device-${hex()}-${hex()}-${hex()}`;
}

function refreshLicenseFields() {
  const idField = document.getElementById('licenseIdPreview');
  const fpField = document.getElementById('fingerprintPreview');
  if (idField) idField.value = generateLicenseId();
  if (fpField) fpField.value = generateFingerprint();
}

refreshLicenseFields();
document.querySelector("#regenerarCampos")?.addEventListener("click", refreshLicenseFields);

// ─── API ──────────────────────────────────────────────────────────────────────
async function api(path, payload, useAuth = true) {
  const headers = { "Content-Type": "application/json" };
  if (useAuth && adminToken) headers.Authorization = `Bearer ${adminToken}`;
  const res = await fetch(path, { method: "POST", headers, body: JSON.stringify(payload) });
  const body = await res.json();
  if (!res.ok) {
    if (res.status === 401) { sessionStorage.removeItem("pqlicense_admin_token"); window.location.href = "/login"; }
    throw new Error(body.details || body.error || "Error de API");
  }
  return body;
}

async function getApi(path) {
  const headers = { Authorization: `Bearer ${adminToken}` };
  const res = await fetch(path, { headers });
  const body = await res.json();
  if (!res.ok) {
    if (res.status === 401) { sessionStorage.removeItem("pqlicense_admin_token"); window.location.href = "/login"; }
    throw new Error(body.error || "Error de API");
  }
  return body;
}

// ─── State ────────────────────────────────────────────────────────────────────
async function loadState() {
  try {
    const state = await (await fetch("/api/state")).json();
    if (classicStatus) classicStatus.textContent = state.classic_algorithm;
    if (pqStatus) pqStatus.textContent = state.pq_algorithm;
    if (revokedStatus) revokedStatus.textContent = `${state.revoked_count} revocadas`;
  } catch (_) {}
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
function estadoBadge(estado) {
  if (estado === 'revocada') return 'background:var(--red-dim);color:var(--red)';
  if (estado === 'vencida') return 'background:var(--amber-dim);color:var(--amber)';
  return 'background:var(--cyan-dim);color:var(--cyan)';
}

async function loadDashboard() {
  try {
    const data = await getApi("/api/licenses");
    const licenses = data.licenses || [];
    const activas = licenses.filter(l => (l.estado || "activa") === "activa").length;
    const vencidas = licenses.filter(l => l.estado === "vencida").length;
    const revocadas = licenses.filter(l => l.estado === "revocada").length;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set("statActivas", activas);
    set("statVencidas", vencidas);
    set("statRevocadas", revocadas);
    set("statTotal", licenses.length);

    const rows = document.getElementById("dashboardRows");
    if (rows) rows.innerHTML = licenses.length
      ? licenses.slice(0, 10).map(l => `
          <tr>
            <td>${esc(l.license_id)}</td>
            <td>${esc(l.customer_id)}</td>
            <td>${esc(l.plan)}</td>
            <td>${esc(l.validation_mode)}</td>
            <td>${esc(l.expires_at)}</td>
            <td><span style="font-size:11px;padding:3px 8px;border-radius:999px;font-weight:600;${estadoBadge(l.estado)}">${esc(l.estado||'activa')}</span></td>
          </tr>`).join("")
      : `<tr><td colspan="6" style="color:var(--dp-fg-4);text-align:center;padding:24px;">No hay licencias emitidas.</td></tr>`;
  } catch (e) {
    const rows = document.getElementById("dashboardRows");
    if (rows) rows.innerHTML = `<tr><td colspan="6" style="color:var(--red);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
  }
}

// ─── Licencias emitidas ───────────────────────────────────────────────────────
async function loadLicenses() {
  const rows = document.getElementById("licenseRows");
  if (!rows) return;
  try {
    const data = await getApi("/api/licenses");
    const licenses = data.licenses || [];
    rows.innerHTML = licenses.length
      ? licenses.map(l => `
          <tr>
            <td>${esc(l.license_id)}</td>
            <td>${esc(l.customer_id)}</td>
            <td>${esc(l.plan)}</td>
            <td>${esc(l.validation_mode)}</td>
            <td>${esc(l.expires_at)}</td>
            <td><span style="font-size:11px;padding:3px 8px;border-radius:999px;font-weight:600;${estadoBadge(l.estado)}">${esc(l.estado||'activa')}</span></td>
          </tr>`).join("")
      : `<tr><td colspan="6" style="color:var(--dp-fg-4);text-align:center;padding:24px;">No hay licencias emitidas.</td></tr>`;
  } catch (e) {
    rows.innerHTML = `<tr><td colspan="6" style="color:var(--red);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
  }
}

document.querySelector("#refreshLicenses")?.addEventListener("click", loadLicenses);

// ─── Set result ───────────────────────────────────────────────────────────────
function setResult(result) {
  if (!resultBadge) return;
  resultBadge.textContent = result.status;
  resultBadge.className = "badge";
  if (result.status === "valid" || result.status === "created") resultBadge.classList.add("valid");
  else if (["expired", "revoked"].includes(result.status)) resultBadge.classList.add("warning");
  else resultBadge.classList.add("invalid");
  if (redirectUrl) { redirectUrl.textContent = result.redirect_url || "-"; redirectUrl.href = result.redirect_url || "#"; }
  const v = result.verification || {};
  if (classicCheck) classicCheck.textContent = v.classical_signature === true ? "válida" : v.classical_signature === false ? "inválida" : "-";
  if (pqCheck) pqCheck.textContent = v.post_quantum_signature === true ? "válida" : v.post_quantum_signature === false ? "inválida" : "-";
  if (modeCheck) modeCheck.textContent = v.required_mode || "-";
  if (statusCheck) statusCheck.textContent = result.details || result.reason || result.status;
  if (eventLog) eventLog.textContent = JSON.stringify(result, null, 2);
}

// ─── License form ─────────────────────────────────────────────────────────────
licenseForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(licenseForm).entries());
  data.days = Number(data.days);
  data.allowed_devices = 3;
  data.features = ["offline", "reports"];
  data.license_id = document.getElementById('licenseIdPreview')?.value || generateLicenseId();
  data.device_fingerprint = document.getElementById('fingerprintPreview')?.value || generateFingerprint();
  data.validation_mode = "hybrid";
  data.redirect_url = "https://app.example.com/start";
  data.error_url = "https://app.example.com/license-error";
  try {
    const created = await api("/api/licenses/generate", data);
    if (licenseJson) licenseJson.value = JSON.stringify(created.license, null, 2);
    setResult({ status: "created", redirect_url: created.license.payload.redirect_url, details: "Licencia generada correctamente." });
    await loadState();
    await loadDashboard();
    refreshLicenseFields();
  } catch (err) {
    setResult({ status: "error", redirect_url: "", details: err.message });
  }
});

// ─── Validar ──────────────────────────────────────────────────────────────────
document.querySelector("#validateLicense")?.addEventListener("click", async () => {
  try {
    const raw = licenseJson?.value.trim();
    if (!raw) throw new Error("Primero genera una licencia.");
    const license = JSON.parse(raw);
    const result = await api("/api/licenses/validate", {
      license,
      product_id: license.payload?.product_id || "",
      device_fingerprint: license.payload?.device_fingerprint || ""
    }, false);
    setResult(result);
  } catch (e) {
    setResult({ status: "error", redirect_url: "", details: e.message });
  }
});

// ─── Revocar ──────────────────────────────────────────────────────────────────
document.querySelector("#revokeLicense")?.addEventListener("click", async () => {
  try {
    const raw = licenseJson?.value.trim();
    if (!raw) throw new Error("Primero genera una licencia.");
    const license = JSON.parse(raw);
    const result = await api(`/api/licenses/${license.payload.license_id}/cancel`, { reason: "cancelacion manual desde frontend" });
    setResult({ ...result, redirect_url: license.payload.metadata?.error_url || "" });
    await loadState();
    await loadDashboard();
  } catch (e) {
    setResult({ status: "error", redirect_url: "", details: e.message });
  }
});

// ─── Revocaciones ─────────────────────────────────────────────────────────────
async function loadRevocations() {
  const rows = document.getElementById("revocationRows");
  if (!rows) return;
  try {
    const data = await getApi("/api/licenses/revocations");
    const revoked = data.payload?.revoked || [];
    const version = data.payload?.revocation_epoch;
    const versionEl = document.getElementById("revListVersion");
    if (versionEl && version) versionEl.textContent = `# Versión: ${version}`;
    rows.innerHTML = revoked.length
      ? revoked.map(r => `<tr><td>${esc(r.license_id)}</td><td>${esc(r.reason)}</td><td>${esc(r.revoked_at)}</td></tr>`).join("")
      : `<tr><td colspan="3" style="color:var(--dp-fg-4);text-align:center;padding:24px;">Sin revocaciones.</td></tr>`;
  } catch (e) {
    rows.innerHTML = `<tr><td colspan="3" style="color:var(--red);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
  }
}

document.querySelector("#refreshRevocaciones")?.addEventListener("click", loadRevocations);

document.querySelector("#downloadCRL")?.addEventListener("click", async () => {
  try {
    const data = await getApi("/api/licenses/revocations");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "crl-snapshot.json"; a.click();
  } catch (e) { alert("Error al descargar: " + e.message); }
});

// ─── Historial ────────────────────────────────────────────────────────────────
async function loadHistorial() {
  const rows = document.getElementById("historialRows");
  if (!rows) return;
  try {
    const data = await getApi("/api/historial");
    const historial = data.historial || [];
    rows.innerHTML = historial.length
      ? historial.map(h => `
          <tr>
            <td>${esc(h.codigo_licencia)}</td>
            <td>${esc(h.fecha_validacion)}</td>
            <td>${esc(h.modo)}</td>
            <td><span style="font-size:11px;padding:3px 8px;border-radius:999px;font-weight:600;${h.resultado==='valida'?'background:var(--cyan-dim);color:var(--cyan)':h.resultado==='revocada'?'background:var(--red-dim);color:var(--red)':'background:var(--amber-dim);color:var(--amber)'}">${esc(h.resultado)}</span></td>
          </tr>`).join("")
      : `<tr><td colspan="4" style="color:var(--dp-fg-4);text-align:center;padding:24px;">Sin registros de validación.</td></tr>`;
  } catch (e) {
    rows.innerHTML = `<tr><td colspan="4" style="color:var(--red);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
  }
}

document.querySelector("#refreshHistorial")?.addEventListener("click", loadHistorial);

// ─── Cancelaciones ────────────────────────────────────────────────────────────
async function loadCancelaciones() {
  const rows = document.getElementById("cancelRows");
  if (!rows) return;
  try {
    const data = await getApi("/api/cancelaciones");
    const cancelaciones = data.cancelaciones || [];
    rows.innerHTML = cancelaciones.length
      ? cancelaciones.map(c => `
          <tr>
            <td>${esc(c.codigo_licencia)}</td>
            <td>${esc(c.fecha_cancelacion)}</td>
            <td><span style="font-size:11px;padding:3px 8px;border-radius:999px;font-weight:600;${c.tipo_cancelacion==='manual'?'background:var(--red-dim);color:var(--red)':'background:var(--amber-dim);color:var(--amber)'}">${esc(c.tipo_cancelacion)}</span></td>
            <td>${esc(c.motivo || '—')}</td>
          </tr>`).join("")
      : `<tr><td colspan="4" style="color:var(--dp-fg-4);text-align:center;padding:24px;">Sin cancelaciones registradas.</td></tr>`;
  } catch (e) {
    rows.innerHTML = `<tr><td colspan="4" style="color:var(--red);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
  }
}

document.querySelector("#refreshCancelaciones")?.addEventListener("click", loadCancelaciones);

// ─── Logout ───────────────────────────────────────────────────────────────────
logoutButton?.addEventListener("click", () => {
  sessionStorage.removeItem("pqlicense_admin_token");
  sessionStorage.removeItem("pqlicense_rol");
  window.location.href = "/login";
});

// ─── Utils ────────────────────────────────────────────────────────────────────
function esc(v) {
  return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
}

// ─── Init ─────────────────────────────────────────────────────────────────────
loadState();
loadDashboard();