const loginForm = document.querySelector("#loginForm");
const registerForm = document.querySelector("#registerForm");
const loginError = document.querySelector("#loginError");
const registerError = document.querySelector("#registerError");
const registerSuccess = document.querySelector("#registerSuccess");

document.querySelectorAll(".auth-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".auth-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".auth-tab-content").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.tab + "Tab").classList.add("active");
  });
});

async function api(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.details || body.error || "Error de API");
  return body;
}

function redirectByRol(rol) {
  window.location.href = rol === "Admin" ? "/app" : "/user";
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.style.display = "none";
  const data = Object.fromEntries(new FormData(loginForm).entries());
  try {
    const result = await api("/api/admin/login", data);
    sessionStorage.setItem("pqlicense_admin_token", result.token);
    sessionStorage.setItem("pqlicense_rol", result.rol || "");
    sessionStorage.setItem("pqlicense_nombre", result.nombre_completo || "");
    redirectByRol(result.rol);
  } catch (error) {
    loginError.style.display = "flex";
    loginError.textContent = "Credenciales incorrectas. Verifica tu correo y contraseña.";
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  registerError.style.display = "none";
  registerSuccess.style.display = "none";
  const data = Object.fromEntries(new FormData(registerForm).entries());
  try {
    await api("/api/auth/register", data);
    registerSuccess.style.display = "flex";
    registerSuccess.textContent = "Cuenta creada exitosamente. Ya puedes iniciar sesión.";
    registerForm.reset();
  } catch (error) {
    registerError.style.display = "flex";
    registerError.textContent = error.message === "correo_ya_registrado"
      ? "Ese correo ya está registrado."
      : "Error al crear la cuenta. Intenta de nuevo.";
  }
});

if (sessionStorage.getItem("pqlicense_admin_token")) {
  redirectByRol(sessionStorage.getItem("pqlicense_rol"));
}