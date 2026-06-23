# Sistema de Validacion de Licencias Postcuantico

Prototipo en Python para el reto "Sistema de Validacion PostCuantico". Implementa generacion de licencias, validacion offline/online, revocacion manual y redireccion segun estado de la licencia.

## Enfoque

El sistema usa una arquitectura de firma hibrida:

- Firma clasica: Ed25519.
- Firma postcuantica real: `ML-DSA-65` mediante `pqcrypto`.
- Fallback documentado: `ML-DSA-65-DEMO` solo si `pqcrypto` no esta disponible.

La licencia puede validarse en tres modos:

- `hybrid`: recomendado; exige firma clasica y firma postcuantica.
- `classical_only`: modo legado para compatibilidad.
- `post_quantum_only`: modo futuro para migracion.

El modo recomendado es `hybrid`, porque mantiene compatibilidad con sistemas actuales mientras agrega una defensa postcuantica.

Importante: en instalaciones normales con `requirements.txt`, el provider postcuantico usa `pqcrypto.sign.ml_dsa_65`. El fallback `ML-DSA-65-DEMO` existe solo para que el proyecto siga abriendo en entornos donde no pueda instalarse `pqcrypto`; ese fallback no debe usarse en produccion.

## Computacion cuantica vs criptografia postcuantica

Este proyecto no usa qubits para validar licencias. Eso es intencional.

La computacion cuantica, con algoritmos como Shor, amenaza criptografia clasica como RSA/ECC. La criptografia postcuantica es la respuesta defensiva: algoritmos que corren en computadoras normales, pero estan disenados para resistir ataques de computadoras cuanticas futuras.

Por eso la validacion de licencias permanece como software clasico y no requiere Qiskit, Q#, Azure Quantum ni simuladores cuanticos.

## Arquitectura

```text
Frontend web
    |
    v
LicenseController
    |
    +--> LicenseService ---------> CryptoService
    |                               |
    |                               +--> ClassicalSignatureProvider
    |                               +--> PostQuantumSignatureProvider
    |                               +--> HybridSignatureProvider
    |
    +--> OfflineValidationService -> RedirectService
    |
    +--> RevocationService
```

Modulos principales:

- `src/pqlicense/license_controller.py`: endpoints HTTP y aliases de compatibilidad.
- `src/pqlicense/license_service.py`: creacion de payloads `pqlicense/v2`.
- `src/pqlicense/crypto_service.py`: orquestacion de firmas.
- `src/pqlicense/classical_provider.py`: provider Ed25519.
- `src/pqlicense/post_quantum_provider.py`: provider postcuantico intercambiable.
- `src/pqlicense/hybrid_provider.py`: reglas de `hybrid`, `classical_only`, `post_quantum_only`.
- `src/pqlicense/offline_validation_service.py`: validacion sin base de datos.
- `src/pqlicense/revocation_service.py`: listas de revocacion firmadas.
- `src/pqlicense/redirect_service.py`: links parametrizados.
- `src/pqlicense/canonical.py`: JSON canonico para datos firmados.
- `src/pqlicense/core.py`: fachada compatible con la API anterior.
- `src/pqlicense/cli.py`: comandos de consola.
- `src/pqlicense/server.py`: API HTTP online.
- `tests/test_license_system.py`: pruebas del flujo principal.

## Requisitos

Usa Python 3.10 o superior.

Dependencias principales:

- `cryptography`: firma clasica Ed25519.
- `pqcrypto`: firma postcuantica ML-DSA-65.

Instalacion recomendada en cualquier computadora:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

En macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Frontend presentable

Iniciar la aplicacion web:

```powershell
python app.py
```

Abrir en el navegador:

```text
http://127.0.0.1:8090
```

Guia rapida de uso:

1. Entra con el administrador demo:
   - Usuario: `admin`
   - Clave: `admin123`
2. Genera una licencia firmada.
3. Presiona `Validar` para comprobar firmas, expiracion, revocacion y redireccion.
4. Revisa la tabla `Licencias emitidas`.
5. Presiona `Revocar` para cancelar la licencia.
6. Revisa la tabla `Revocaciones`.

Desde el panel puedes:

- Iniciar sesion como administrador.
- Generar una licencia firmada.
- Validar la licencia.
- Revocar la licencia.
- Regenerar claves.
- Ver tabla de licencias emitidas.
- Ver tabla de revocaciones.
- Seleccionar modo de firma: hibrido, clasico legado o postcuantico futuro.
- Agregar plan y huella de dispositivo.
- Ver el JSON de la licencia y la redireccion resultante.
- Ver detalles de verificacion de firma clasica y firma postcuantica.

El frontend usa el mismo backend de validacion que la API y guarda claves/revocaciones de demostracion en `demo_output/`.

Credenciales admin por defecto para demo:

```text
usuario: admin
clave: admin123
```

Puedes cambiarlas con variables de entorno:

```powershell
$env:PQLICENSE_ADMIN_USER="admin"
$env:PQLICENSE_ADMIN_PASSWORD="una-clave-mas-segura"
python app.py
```

El puerto por defecto es `8090`. Para cambiarlo:

```powershell
$env:PQLICENSE_PORT="9000"
python app.py
```

## Preparado para GitHub

Este proyecto esta preparado para publicarse sin datos locales:

- `demo_output/` queda ignorado porque contiene claves, licencias y revocaciones generadas al correr la app.
- `__pycache__/`, entornos virtuales y archivos de editor quedan ignorados.
- `.env.example` muestra variables configurables sin incluir secretos reales.
- No se requiere ninguna ruta local especifica de la computadora original.
- `requirements.txt` instala `pqcrypto` para activar ML-DSA-65 real.

Antes de subir, ejecuta:

```powershell
python -m unittest discover -s tests -v
```

## Demo por consola opcional

Generar claves:

```powershell
python run.py init-keys --out keys.json --public-out public_keys.json
```

Generar licencia:

```powershell
python run.py generate-license `
  --keys keys.json `
  --out license.json `
  --license-id LIC-001 `
  --customer-id cliente-demo `
  --product-id app-pro `
  --days 365 `
  --feature offline `
  --feature reports `
  --device-limit 3 `
  --redirect-url "https://app.example.com/start" `
  --error-url "https://app.example.com/license-error"
```

Validar offline:

```powershell
python run.py validate --keys public_keys.json --license license.json --product-id app-pro
```

Revocar licencia:

```powershell
python run.py revoke --keys keys.json --license-id LIC-001 --reason "cancelacion manual" --out revocations.json
```

Validar usando revocaciones:

```powershell
python run.py validate --keys public_keys.json --license license.json --product-id app-pro --revocations revocations.json
```

Iniciar API online:

```powershell
python run.py serve --keys keys.json --product-id app-pro --revocations revocations.json --port 8080
```

Endpoints:

- `POST /api/licenses/generate`: genera licencia `pqlicense/v2`.
- `POST /api/licenses/validate`: valida online/offline con firmas, expiracion, dispositivo y revocacion.
- `POST /api/licenses/{id}/cancel`: revoca manualmente una licencia.
- `GET /api/licenses`: lista licencias emitidas, requiere admin.
- `GET /api/licenses/revocations`: devuelve la lista de revocacion firmada.
- `GET /api/licenses/state`: devuelve estado publico del sistema sin claves privadas.
- `POST /api/admin/login`: autentica administrador y devuelve token temporal.

Aliases de compatibilidad:

- `POST /api/create-license`
- `POST /api/validate`
- `POST /api/revoke`
- `GET /api/revocations`
- `GET /api/state`

## Estados de validacion

- `valid`: licencia aceptada; devuelve link de acceso parametrizado.
- `expired`: licencia vencida.
- `revoked`: licencia cancelada manual o automaticamente.
- `invalid_signature`: licencia alterada o falsificada.
- `invalid_revocation_signature`: lista de revocacion alterada.
- `invalid_format`: documento incompleto o mal formado.
- `wrong_product`: licencia emitida para otro producto.
- `wrong_device`: licencia ligada a otra huella de dispositivo.

## Formato de licencia

Las licencias usan `pqlicense/v2`:

```json
{
  "schema": "pqlicense/v2",
  "payload": {
    "license_id": "LIC-001",
    "customer_id": "cliente-demo",
    "product_id": "app-pro",
    "plan": "professional",
    "issued_at": "2026-06-23T00:00:00Z",
    "expires_at": "2027-06-23T00:00:00Z",
    "allowed_devices": 3,
    "device_fingerprint": "device-demo-hash",
    "features": ["offline", "reports"],
    "validation_mode": "hybrid",
    "revocation_epoch": 1,
    "metadata": {
      "redirect_url": "https://app.example.com/start",
      "error_url": "https://app.example.com/license-error"
    }
  },
  "signatures": {
    "classical": {},
    "post_quantum": {}
  }
}
```

## Notas de seguridad

- Las claves privadas nunca se envian al frontend.
- Las respuestas de estado solo incluyen claves publicas.
- Generar, listar, revocar y regenerar claves requiere token admin.
- `demo_output/` esta ignorado por Git porque contiene claves y revocaciones locales.
- Para produccion, las claves privadas deben vivir en un almacén seguro o HSM/KMS.
- La revocacion offline depende de una lista firmada reciente; si el cliente nunca vuelve a conectarse, no puede conocer cancelaciones nuevas.
- El provider `ML-DSA-65` usa `pqcrypto`; para produccion formal se debe validar la libreria, version, plataforma y politica de manejo de claves.
- Se recomienda rotacion de claves y versionado por `key_id`.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas cubren licencia valida, licencia alterada, vencimiento, revocacion firmada, lista de revocacion manipulada, endpoints nuevos, aliases anteriores, modos de firma, ML-DSA-65 con `pqcrypto`, login admin, listados y proteccion contra exposicion de claves privadas.

## Siguiente paso para produccion

Endurecer despliegue: usar HTTPS, una base de datos real, almacenamiento seguro de claves, rotacion por `key_id`, logs de auditoria y credenciales admin fuera del codigo mediante un gestor de secretos.
