# Instrucciones de uso

Guía para **instalar, ejecutar y presentar** el *Sistema de Validación de Licencias Postcuántico* (Reto Mayo – Julio 2026).

Esta guía está pensada para que cualquier integrante del equipo pueda descargar el proyecto, levantarlo en su computadora y hacer una demostración completa frente al jurado.

---

## 1. Requisitos previos

- **Python 3.10 o superior** (probado con 3.11 y 3.12).
- Conexión a internet solo para la instalación inicial de dependencias.
- Navegador web (Chrome, Edge, Firefox, etc.).

---

## 2. Instalación (una sola vez)

Desde la carpeta del proyecto.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **IMPORTANTE para la demo:** `requirements.txt` instala `pqcrypto`, que activa la firma postcuántica **real ML-DSA-65**. Si `pqcrypto` no queda instalado, el sistema sigue funcionando pero cae a un modo de respaldo llamado `ML-DSA-65-DEMO` (que **no** es resistente a ataques cuánticos). Antes de presentar, confirma que estás en modo real (ver paso 7).

---

## 3. Iniciar la aplicación

```powershell
python app.py
```

Verás en consola:

```
license API listening on http://127.0.0.1:8090
```

Abre en el navegador:

```
http://127.0.0.1:8090
```

> El puerto por defecto es `8090`. Para cambiarlo: `$env:PQLICENSE_PORT="9000"` antes de `python app.py`.

---

## 4. Guion de la demostración (paso a paso)

Sigue este orden para mostrar el flujo completo del reto.

### Paso 1 — Iniciar sesión como administrador
En el panel **"Acceso administrador"**:
- Usuario: `admin`
- Clave: `admin123`
- Presiona **Entrar**. El estado debe cambiar a **"Sesión admin"** (verde).

> Generar, revocar, listar y regenerar claves requiere esta sesión. Es la protección por token de administrador.

### Paso 2 — Generar una licencia firmada
En **"Crear licencia"**, deja los valores de ejemplo (o personalízalos) y presiona **Generar licencia firmada**.
- Aparece el JSON de la licencia (`pqlicense/v2`) en el cuadro **Licencia JSON**.
- La licencia incluye **dos firmas**: clásica (Ed25519) y postcuántica (ML-DSA-65).

### Paso 3 — Validar la licencia
Presiona **Validar**. Observa el panel de resultado:
- Badge **`valid`** en verde.
- **Redirección**: un link paramétrico con `license_id`, `customer_id`, `product_id` y `plan`.
- **Detalles de verificación**: Firma clásica = *válida*, Firma postcuántica = *válida*, Modo requerido = *hybrid*.

> El link de redirección apunta a `https://app.example.com/...` que es un **dominio de ejemplo** (no abre nada real, es intencional). En producción ese link sería la aplicación real del cliente.

### Paso 4 — Mostrar detección de manipulación (opcional, muy efectivo)
En el cuadro **Licencia JSON**, cambia cualquier dato del `payload` (por ejemplo, el `plan` o la fecha) y presiona **Validar** otra vez.
- Resultado: **`invalid_signature`**. Esto demuestra que cualquier alteración rompe las firmas → no se puede falsificar.

### Paso 5 — Revocar (cancelar) una licencia
Genera/valida una licencia nueva y presiona **Revocar**.
- Resultado: **`revoked`**, y la redirección cambia al **link de error**.
- La licencia aparece en la tabla **"Revocaciones"**.

### Paso 6 — Mostrar las tablas
- **Licencias emitidas**: licencias generadas en la sesión.
- **Revocaciones**: lista firmada de licencias canceladas (revocación verificable offline).

### Paso 7 — Confirmar que la firma postcuántica es REAL
Mira la barra superior de estado: debe decir **`ML-DSA-65`** (no `ML-DSA-65-DEMO`).
Alternativa por consola/navegador, abre:

```
http://127.0.0.1:8090/api/state
```

Y verifica `"pq_algorithm": "ML-DSA-65"`.

---

## 5. Estados de validación que puedes mostrar

| Estado | Significado |
|--------|-------------|
| `valid` | Licencia aceptada; devuelve link de acceso. |
| `expired` | Licencia vencida. |
| `revoked` | Licencia cancelada. |
| `invalid_signature` | Licencia alterada o falsificada. |
| `wrong_product` | Licencia emitida para otro producto. |
| `wrong_device` | Licencia ligada a otro dispositivo. |
| `invalid_format` | Documento mal formado. |

---

## 6. Subproblemas del reto resueltos

El reto planteaba 5 subproblemas. Así los resuelve el sistema:

1. **¿Qué algoritmos postcuánticos usar para firmas?**
   → **ML-DSA-65** (nombre estándar NIST de *Dilithium*), uno de los algoritmos sugeridos en el reto, mediante la librería `pqcrypto`.

2. **¿Cómo implementar validación híbrida (clásica + postcuántica)?**
   → Cada licencia se firma con **Ed25519 (clásica) + ML-DSA-65 (postcuántica)**. Hay tres modos: `hybrid` (recomendado, exige ambas), `classical_only` y `post_quantum_only`.

3. **¿Cómo minimizar impacto en rendimiento y tamaño de claves?**
   → Arquitectura de *providers* intercambiables y firma sobre JSON canónico; el modo `classical_only` permite operar liviano cuando no se requiere PQC, y solo se agrega la firma PQ cuando hace falta.

4. **¿Cómo garantizar compatibilidad con sistemas existentes?**
   → Modo `classical_only` y **aliases de API heredada** (`/api/validate`, `/api/create-license`, `/api/revoke`, etc.) para integrarse con sistemas clásicos actuales.

5. **¿Cómo asegurar revocación en entornos offline?**
   → **Lista de revocación firmada**: el cliente verifica la firma de la lista y comprueba la membresía sin conexión a base de datos. La validación offline es íntegra y verificable.

### Requisitos funcionales cubiertos
1. ✅ Generar licencias válidas.
2. ✅ Validar licencias (online y offline, mismo motor).
3. ✅ Cancelar licencias (manual mediante revocación; automática por vencimiento).
4. ✅ Redirección a link paramétrico cuando la licencia es válida.
5. ✅ Redirección a link de error cuando es inválida o vencida.

---

## 7. Demo por consola (opcional, sin navegador)

Para mostrar el flujo desde terminal:

```powershell
# Generar claves
python run.py init-keys --out keys.json --public-out public_keys.json

# Generar licencia
python run.py generate-license --keys keys.json --out license.json --license-id LIC-001 --customer-id cliente-demo --product-id app-pro --days 365 --redirect-url "https://app.example.com/start" --error-url "https://app.example.com/license-error"

# Validar offline
python run.py validate --keys public_keys.json --license license.json --product-id app-pro
```

---

## 8. Detener la aplicación

- En la terminal donde corre `python app.py`, presiona **Ctrl + C**.
- Si quedó un proceso colgado en el puerto 8090 (PowerShell):

```powershell
Get-NetTCPConnection -LocalPort 8090 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

> **Tip:** Si cambias código de Python (`.py`), debes **reiniciar** la app (Ctrl+C y volver a `python app.py`). Los archivos web (HTML/JS/CSS) sí se recargan solos al refrescar el navegador.

---

## 9. Probar que todo funciona (antes de presentar)

```powershell
python -m unittest discover -s tests -v
```

Deben pasar todas las pruebas (licencia válida, alterada, vencida, revocación firmada, login admin, ML-DSA-65, etc.).

---

## 10. Notas de seguridad

- Las **claves privadas** se guardan localmente en `demo_output/` y **están ignoradas por Git** (no se suben al repositorio).
- Las credenciales `admin / admin123` son **solo para la demo**. Para un entorno real, defínelas por variable de entorno:
  ```powershell
  $env:PQLICENSE_ADMIN_PASSWORD="una-clave-mas-segura"
  python app.py
  ```
- El archivo `.env` real nunca se sube; solo se comparte `.env.example` como plantilla.
