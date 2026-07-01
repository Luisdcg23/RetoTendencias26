const userToken = sessionStorage.getItem("pqlicense_admin_token") || "";
const userRol = sessionStorage.getItem("pqlicense_rol") || "";
if (!userToken) window.location.href = "/login";
if (userRol === "Admin") window.location.href = "/app";

// ─── Utils ────────────────────────────────────────────────────────────────────
function esc(v) {
  return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
}

function formatDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" });
}

function computeEstado(l) {
  if (l.estado === "revocada") return "revocada";
  if (l.expires_at && new Date(l.expires_at) < new Date()) return "vencida";
  return "activa";
}

function estadoBadge(estado) {
  if (estado === "revocada") return "background:var(--red-dim);color:var(--red)";
  if (estado === "vencida") return "background:var(--amber-dim);color:var(--amber)";
  return "background:var(--cyan-dim);color:var(--cyan)";
}

// ─── Huella de dispositivo (persistente en este navegador) ───────────────────
function getOrCreateDeviceFingerprint() {
  let fp = localStorage.getItem("pqlicense_device_fp");
  if (!fp) {
    const hex = () => Math.floor(Math.random() * 0xFFFFFF).toString(16).padStart(6, "0");
    fp = `device-${hex()}-${hex()}-${hex()}`;
    localStorage.setItem("pqlicense_device_fp", fp);
  }
  return fp;
}

// ─── Navegación entre secciones ───────────────────────────────────────────────
function navTo(page) {
  document.querySelectorAll(".user-page").forEach(p => p.classList.remove("active"));
  document.getElementById("userpage-" + page)?.classList.add("active");
  window.scrollTo({ top: 0, behavior: "instant" });
}

document.querySelector("#quickActivar")?.addEventListener("click", () => navTo("activar"));
document.querySelector("#backFromActivar")?.addEventListener("click", () => navTo("dashboard"));
document.querySelector("#quickValidar")?.addEventListener("click", () => {
  navTo("dashboard");
  document.getElementById("myLicensesAnchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
});

// ─── Dashboard: cargar licencias ──────────────────────────────────────────────
let currentLicenses = [];

function renderLicenseRow(l) {
  const estado = computeEstado(l);
  const puedeRevocar = estado !== "revocada";
  const revokeBtn = puedeRevocar
    ? `<button class="danger revoke-btn" data-code="${esc(l.license_id)}" style="padding:5px 12px;font-size:11px;min-height:unset;margin-left:6px;">Revocar</button>`
    : "";
  return `
    <tr>
      <td>${esc(l.license_id)}</td>
      <td>${formatDate(l.issued_at)}</td>
      <td>${formatDate(l.expires_at)}</td>
      <td><span style="font-size:11px;padding:3px 8px;border-radius:999px;font-weight:600;${estadoBadge(estado)}">${estado}</span></td>
      <td>
        <button class="secondary validate-btn" data-code="${esc(l.license_id)}" style="padding:5px 12px;font-size:11px;min-height:unset;">Validar</button>
        ${revokeBtn}
      </td>
    </tr>`;
}

function updateSummary() {
  const activas = currentLicenses.filter(l => computeEstado(l) === "activa").length;
  const vencidas = currentLicenses.filter(l => computeEstado(l) === "vencida").length;
  const revocadas = currentLicenses.filter(l => computeEstado(l) === "revocada").length;
  const proximas = currentLicenses
    .filter(l => computeEstado(l) === "activa" && l.expires_at)
    .map(l => new Date(l.expires_at))
    .sort((a, b) => a - b);

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  set("uStatActivas", activas);
  set("uStatVencidas", vencidas);
  set("uStatRevocadas", revocadas);
  set("uStatProximo", proximas.length ? formatDate(proximas[0].toISOString()) : "—");
}

async function loadMyLicenses() {
  const rows = document.getElementById("myLicenseRows");
  const nameEl = document.getElementById("welcomeName");
  try {
    const res = await fetch("/api/my-licenses", {
      headers: { Authorization: `Bearer ${userToken}` },
    });
    const data = await res.json();
    if (!res.ok) {
      sessionStorage.removeItem("pqlicense_admin_token");
      sessionStorage.removeItem("pqlicense_rol");
      window.location.href = "/login";
      return;
    }
    if (nameEl) nameEl.textContent = data.nombre_completo || "";
    currentLicenses = data.licenses || [];
    updateSummary();
    if (rows) rows.innerHTML = currentLicenses.length
      ? currentLicenses.map(renderLicenseRow).join("")
      : `<tr><td colspan="5" style="color:var(--dp-fg-4);text-align:center;padding:24px;">No tienes licencias registradas todavía. Usa "Activar licencia" si ya compraste una.</td></tr>`;

    document.querySelectorAll(".validate-btn").forEach(btn => {
      btn.addEventListener("click", () => validateLicense(btn.dataset.code));
    });
    document.querySelectorAll(".revoke-btn").forEach(btn => {
      btn.addEventListener("click", () => confirmRevoke(btn.dataset.code));
    });
  } catch (e) {
    if (rows) rows.innerHTML = `<tr><td colspan="5" style="color:var(--red);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
  }
}

// ─── Validar (desde la tabla) ──────────────────────────────────────────────────
async function validateLicense(code) {
  try {
    const res = await fetch("/api/my-licenses/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${userToken}` },
      body: JSON.stringify({ license_id: code }),
    });
    const data = await res.json();
    if (!res.ok) {
      renderResultado("invalid", { code, message: data.error === "forbidden" ? "Esta licencia no pertenece a tu cuenta." : "No se pudo validar la licencia." });
    } else {
      renderResultado(data.status, { code, result: data });
    }
    navTo("resultado");
  } catch (e) {
    renderResultado("invalid", { code, message: e.message });
    navTo("resultado");
  }
}

// ─── Revocar (desde la tabla, con confirmacion inline) ────────────────────────
function confirmRevoke(code) {
  if (!confirm(`¿Seguro que quieres revocar la licencia ${code}? Esta acción no se puede deshacer.`)) return;
  revokeLicense(code);
}

async function revokeLicense(code) {
  try {
    const res = await fetch("/api/my-licenses/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${userToken}` },
      body: JSON.stringify({ license_id: code, reason: "cancelacion solicitada por el usuario desde su panel" }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error al revocar la licencia.");
    await loadMyLicenses();
  } catch (e) {
    alert("No se pudo revocar: " + e.message);
  }
}

// ─── Activar licencia ──────────────────────────────────────────────────────────
const activateForm = document.getElementById("activateForm");
const activateCode = document.getElementById("activateCode");
const devicePreview = document.getElementById("devicePreview");
const activateError = document.getElementById("activateError");
const activateErrorText = document.getElementById("activateErrorText");
const activateSubmit = document.getElementById("activateSubmit");

if (devicePreview) devicePreview.value = getOrCreateDeviceFingerprint();

function formatLicenseCodeInput(raw) {
  let clean = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (clean.startsWith("LIC")) clean = clean.slice(3);
  clean = clean.slice(0, 12);
  const part1 = clean.slice(0, 6);
  const part2 = clean.slice(6, 12);
  let out = "LIC";
  if (part1) out += "-" + part1;
  if (part2) out += "-" + part2;
  return out;
}

activateCode?.addEventListener("input", (e) => {
  const formatted = formatLicenseCodeInput(e.target.value);
  e.target.value = formatted;
  e.target.classList.toggle("valid-ready", formatted.length >= 17);
  if (activateError) activateError.style.display = "none";
});

activateForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const code = activateCode.value.trim();
  if (code.length < 17) {
    activateErrorText.textContent = "Ingresa un código de licencia completo (LIC-XXXXXX-XXXXXX).";
    activateError.style.display = "flex";
    return;
  }
  activateSubmit.disabled = true;
  activateSubmit.textContent = "Verificando…";
  try {
    const res = await fetch("/api/my-licenses/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${userToken}` },
      body: JSON.stringify({ license_id: code, device_fingerprint: getOrCreateDeviceFingerprint() }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (data.error === "license_not_found") {
        renderResultado("not_found", { code });
      } else if (data.error === "license_owned_by_other") {
        renderResultado("forbidden", { code });
      } else {
        renderResultado("invalid", { code, message: data.error || "No se pudo activar la licencia." });
      }
    } else {
      renderResultado(data.status, { code, result: data, activated: true });
      await loadMyLicenses();
    }
    navTo("resultado");
    activateCode.value = "";
    activateCode.classList.remove("valid-ready");
  } catch (err) {
    renderResultado("invalid", { code, message: err.message });
    navTo("resultado");
  } finally {
    activateSubmit.disabled = false;
    activateSubmit.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> Activar licencia`;
  }
});

// ─── Pantallas de resultado ────────────────────────────────────────────────────

const ICONS = {
  check: '<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke-width="1.6"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
  clock: '<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  x: '<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke-width="1.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  mail: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.6 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
  retry: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
};

const RESULT_CONFIG = {
  valid: {
    color: "var(--cyan)", ring: "var(--cyan-dim)", icon: ICONS.check,
    title: "¡Licencia válida!",
    sub: "Tu licencia ha sido verificada correctamente.",
    badge: "Estado: Activa", errorCode: null,
  },
  expired: {
    color: "var(--amber)", ring: "var(--amber-dim)", icon: ICONS.clock,
    title: "Tu licencia ha vencido",
    sub: "El período de validez de tu licencia expiró.",
    badge: "Estado: Vencida", errorCode: "LICENSE_EXPIRED",
  },
  revoked: {
    color: "var(--red)", ring: "var(--red-dim)", icon: ICONS.x,
    title: "Licencia revocada",
    sub: "Esta licencia fue desactivada y ya no permite acceso.",
    badge: "Estado: Revocada", errorCode: "LICENSE_REVOKED",
  },
  invalid: {
    color: "var(--red)", ring: "var(--red-dim)", icon: ICONS.x,
    title: "Licencia inválida",
    sub: "No se pudo verificar esta licencia.",
    badge: "Estado: Inválida", errorCode: "LICENSE_INVALID",
  },
  not_found: {
    color: "var(--red)", ring: "var(--red-dim)", icon: ICONS.x,
    title: "Licencia no encontrada",
    sub: "El código introducido no existe en el sistema.",
    badge: "Estado: No encontrada", errorCode: "LICENSE_NOT_FOUND",
  },
  forbidden: {
    color: "var(--red)", ring: "var(--red-dim)", icon: ICONS.x,
    title: "Esta licencia ya está en uso",
    sub: "El código pertenece a otra cuenta. Si es un error, contacta a soporte.",
    badge: "Estado: No disponible", errorCode: "LICENSE_OWNED_BY_OTHER",
  },
};

function statusToKey(status) {
  if (status === "valid") return "valid";
  if (status === "expired") return "expired";
  if (status === "revoked") return "revoked";
  if (status === "not_found" || status === "forbidden") return status;
  return "invalid";
}

function renderResultado(status, opts = {}) {
  const key = statusToKey(status);
  const cfg = RESULT_CONFIG[key];
  const code = opts.code || (opts.result && opts.result.license_id) || "";
  const result = opts.result || {};
  const v = result.verification || {};

  let detailRows = "";
  if (key === "valid") {
    detailRows = `
      <div class="result-badges">
        <span class="chip active" style="color:var(--cyan);border-color:rgba(34,211,238,0.3);background:var(--cyan-dim);">Firma clásica ✓</span>
        <span class="chip active" style="color:var(--cyan);border-color:rgba(34,211,238,0.3);background:var(--cyan-dim);">Firma postcuántica ✓</span>
      </div>
      <div class="result-detail-box">
        <div class="row"><span>Código</span><span>${esc(code)}</span></div>
        <div class="row"><span>Modo</span><span>${esc(v.required_mode || "hybrid")}</span></div>
        ${opts.activated ? '<div class="row"><span>Activación</span><span>Dispositivo vinculado</span></div>' : ""}
      </div>`;
  } else if (code) {
    detailRows = `
      <div class="result-detail-box">
        <div class="row"><span>Código</span><span>${esc(code)}</span></div>
        ${opts.message ? `<div class="row"><span>Detalle</span><span>${esc(opts.message)}</span></div>` : ""}
      </div>`;
  } else if (opts.message) {
    detailRows = `
      <div class="result-detail-box">
        <div class="row"><span>Detalle</span><span>${esc(opts.message)}</span></div>
      </div>`;
  }

  let actions = "";
  if (key === "valid") {
    actions = `<button class="primary" onclick="navTo('dashboard')" style="width:100%;display:flex;align-items:center;justify-content:center;gap:8px;">${ICONS.check} Continuar</button>`;
  } else if (key === "expired") {
    actions = `
      <a href="mailto:soporte@digipermit.com?subject=Renovación de licencia ${encodeURIComponent(code)}" class="primary" style="width:100%;text-decoration:none;display:flex;align-items:center;justify-content:center;gap:8px;">${ICONS.retry} Renovar licencia</a>
      <a href="mailto:soporte@digipermit.com" class="secondary" style="width:100%;text-decoration:none;display:flex;align-items:center;justify-content:center;gap:8px;margin-top:10px;">${ICONS.mail} Contactar soporte</a>`;
  } else if (key === "not_found" || key === "invalid") {
    actions = `
      <button class="primary" onclick="navTo('activar')" style="width:100%;display:flex;align-items:center;justify-content:center;gap:8px;">${ICONS.retry} Intentar de nuevo</button>
      <a href="mailto:soporte@digipermit.com" class="result-secondary" style="margin-top:10px;">Contactar soporte</a>`;
  } else {
    // revoked, forbidden
    actions = `<a href="mailto:soporte@digipermit.com" class="primary" style="width:100%;text-decoration:none;display:flex;align-items:center;justify-content:center;gap:8px;">${ICONS.mail} Contactar soporte</a>`;
  }

  document.getElementById("resultShell").innerHTML = `
    <div class="result-card">
      <div class="status-ring">
        <div class="status-ring-outer" style="background:${cfg.ring};">
          <div class="status-ring-inner" style="background:${cfg.ring};">
            <span style="color:${cfg.color};">${cfg.icon}</span>
          </div>
        </div>
        <div class="status-ring-border" style="border-color:${cfg.ring};"></div>
      </div>
      <div>
        <h1 class="status-title" style="color:${cfg.color};">${cfg.title}</h1>
        <p class="status-sub">${cfg.sub}</p>
      </div>
      <span class="chip active" style="color:${cfg.color};border-color:${cfg.ring};background:${cfg.ring};">${cfg.badge}</span>
      ${detailRows}
      <div style="width:100%;height:1px;background:var(--dp-border);"></div>
      <div style="width:100%;">${actions}</div>
      ${cfg.errorCode ? `<p class="result-error-code">Código de error: ${cfg.errorCode}</p>` : ""}
      <button class="result-secondary" onclick="navTo('dashboard')">← Volver a mis licencias</button>
    </div>`;
}

// ─── Logout ───────────────────────────────────────────────────────────────────
document.querySelector("#logoutButton")?.addEventListener("click", () => {
  sessionStorage.removeItem("pqlicense_admin_token");
  sessionStorage.removeItem("pqlicense_rol");
  sessionStorage.removeItem("pqlicense_nombre");
  window.location.href = "/login";
});

// ─── Init ─────────────────────────────────────────────────────────────────────
loadMyLicenses();