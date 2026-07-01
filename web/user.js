const userToken = sessionStorage.getItem("pqlicense_admin_token") || "";
const userRol = sessionStorage.getItem("pqlicense_rol") || "";
if (!userToken) window.location.href = "/login";
if (userRol === "Admin") window.location.href = "/app";

function esc(v) {
  return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
}

function estadoBadge(estado) {
  if (estado === 'revocada') return 'background:var(--red-dim);color:var(--red)';
  if (estado === 'vencida') return 'background:var(--amber-dim);color:var(--amber)';
  return 'background:var(--cyan-dim);color:var(--cyan)';
}

function renderLicenseRow(l) {
  const estaRevocada = l.estado === 'revocada';
  const revokeBtn = estaRevocada
    ? ""
    : `<button class="btn revoke-btn" data-code="${esc(l.license_id)}" style="padding:6px 14px;border-radius:8px;font-size:12px;background:var(--red-dim);color:var(--red);border:none;">Revocar</button>`;
  return `
    <tr>
      <td>${esc(l.license_id)}</td>
      <td>${esc(l.issued_at)}</td>
      <td>${esc(l.expires_at)}</td>
      <td><span style="font-size:11px;padding:3px 8px;border-radius:999px;font-weight:600;${estadoBadge(l.estado)}">${esc(l.estado || 'activa')}</span></td>
      <td style="display:flex;gap:8px;">
        <button class="btn validate-btn" data-code="${esc(l.license_id)}" style="padding:6px 14px;border-radius:8px;font-size:12px;">Validar</button>
        ${revokeBtn}
      </td>
    </tr>`;
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
    const licenses = data.licenses || [];
    if (rows) rows.innerHTML = licenses.length
      ? licenses.map(renderLicenseRow).join("")
      : `<tr><td colspan="5" style="color:var(--dp-fg-4);text-align:center;padding:24px;">No tienes licencias registradas.</td></tr>`;

    document.querySelectorAll(".validate-btn").forEach((btn) => {
      btn.addEventListener("click", () => validateLicense(btn.dataset.code));
    });
    document.querySelectorAll(".revoke-btn").forEach((btn) => {
      btn.addEventListener("click", () => confirmRevoke(btn.dataset.code));
    });
  } catch (e) {
    if (rows) rows.innerHTML = `<tr><td colspan="5" style="color:var(--red);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
  }
}

async function validateLicense(code) {
  const resultBox = document.getElementById("validationResult");
  if (!resultBox) return;
  resultBox.style.display = "block";
  resultBox.innerHTML = `<p style="color:var(--dp-fg-4);">Validando ${esc(code)}…</p>`;
  try {
    const res = await fetch("/api/my-licenses/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${userToken}` },
      body: JSON.stringify({ license_id: code }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error al validar la licencia.");
    renderValidationResult(code, data);
  } catch (e) {
    resultBox.innerHTML = `<p style="color:var(--red);">${esc(e.message)}</p>`;
  }
}

function renderValidationResult(code, result) {
  const v = result.verification || {};
  const status = result.status || "unknown";
  const color = status === "valid" ? "var(--cyan)" : (["expired", "revoked"].includes(status) ? "var(--amber)" : "var(--red)");
  document.getElementById("validationResult").innerHTML = `
    <div>
      <p style="margin:0 0 8px;"><strong>${esc(code)}</strong> — Estado:
        <span style="color:${color};font-weight:600;">${esc(status)}</span>
      </p>
      <p style="margin:0;color:var(--dp-fg-4);font-size:13px;">
        Firma clásica: ${v.classical_signature === true ? "válida" : v.classical_signature === false ? "inválida" : "-"}
        · Firma postcuántica: ${v.post_quantum_signature === true ? "válida" : v.post_quantum_signature === false ? "inválida" : "-"}
        · Detalle: ${esc(result.details || result.reason || "-")}
      </p>
    </div>`;
}

function confirmRevoke(code) {
  const resultBox = document.getElementById("validationResult");
  if (!resultBox) return;
  resultBox.style.display = "block";
  resultBox.innerHTML = `
    <div>
      <p style="margin:0 0 12px;color:var(--red);font-weight:600;">
        ¿Seguro que quieres revocar la licencia ${esc(code)}? Esta acción no se puede deshacer.
      </p>
      <button id="confirmRevokeYes" class="btn" style="padding:8px 16px;border-radius:8px;background:var(--red-dim);color:var(--red);border:none;margin-right:8px;">Sí, revocar</button>
      <button id="confirmRevokeNo" class="btn" style="padding:8px 16px;border-radius:8px;">Cancelar</button>
    </div>`;
  document.getElementById("confirmRevokeYes")?.addEventListener("click", () => revokeLicense(code));
  document.getElementById("confirmRevokeNo")?.addEventListener("click", () => {
    resultBox.style.display = "none";
    resultBox.innerHTML = "";
  });
}

async function revokeLicense(code) {
  const resultBox = document.getElementById("validationResult");
  if (!resultBox) return;
  resultBox.innerHTML = `<p style="color:var(--dp-fg-4);">Revocando ${esc(code)}…</p>`;
  try {
    const res = await fetch("/api/my-licenses/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${userToken}` },
      body: JSON.stringify({ license_id: code, reason: "cancelacion solicitada por el usuario desde su panel" }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Error al revocar la licencia.");
    resultBox.innerHTML = `<p style="color:var(--cyan);">Licencia ${esc(code)} revocada correctamente.</p>`;
    await loadMyLicenses();
  } catch (e) {
    resultBox.innerHTML = `<p style="color:var(--red);">${esc(e.message)}</p>`;
  }
}

document.querySelector("#logoutButton")?.addEventListener("click", () => {
  sessionStorage.removeItem("pqlicense_admin_token");
  sessionStorage.removeItem("pqlicense_rol");
  sessionStorage.removeItem("pqlicense_nombre");
  window.location.href = "/login";
});

loadMyLicenses();