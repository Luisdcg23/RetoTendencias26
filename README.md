# Sistema de Validacion de Licencias Postcuantico

Prototipo en Python para el reto "Sistema de Validacion PostCuantico". Implementa generacion de licencias, validacion offline/online, revocacion manual (por admin y por el propio usuario), y redireccion segun estado de la licencia. Incluye persistencia real en PostgreSQL, autenticacion con JWT/bcrypt, y control de acceso por rol.

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

## Persistencia y autenticacion

El sistema usa **PostgreSQL 18** (base `reto_tendencias`) como almacenamiento real, con 7 tablas relacionadas:

- `usuarios`, `tipo_de_usuario`: cuentas y roles (Admin, Individual, Empresa).
- `licencias`: nucleo del sistema, incluye el documento firmado completo (`payload` JSON) ademas de las columnas individuales usadas para listados rapidos.
- `cancelaciones`, `historial_validaciones`: auditoria de cancelaciones y de cada intento de validacion.
- `dispositivo_activacion`: control de activaciones por huella de hardware.
- `revocaciones_offline`: snapshot versionado (CRL) para validacion sin conexion.

La autenticacion usa:

- **bcrypt** para hashear contrasenas (nunca en texto plano).
- **JWT** (PyJWT) firmado con `PQLICENSE_JWT_SECRET`, con expiracion configurable (`PQLICENSE_JWT_EXPIRES_MINUTES`, default 120 minutos).
- El payload del JWT incluye `sub` (id de usuario), `correo`, `rol` y `nombre_completo`, lo que permite identificar y filtrar datos por usuario sin ir a la base de datos en cada peticion.

Si PostgreSQL no esta disponible al arrancar, el sistema cae a un modo de almacenamiento en memoria (no persistente) para no bloquear el desarrollo, e imprime un aviso en consola.

## Roles y vistas

El sistema tiene dos vistas separadas segun el rol del usuario autenticado:

- **Admin** (`/app`): panel completo — generar licencias, validar, revocar, ver historial de validaciones, cancelaciones, y descargar la lista de revocacion (CRL).
- **Individual / Empresa** (`/user`): panel de cliente final — ver solo las licencias propias, validarlas, y revocarlas.

El login (`POST /api/admin/login`, a pesar del nombre historico, autentica cualquier rol) devuelve el `rol` del usuario junto con el token; el frontend usa ese valor para redirigir a `/app` o `/user` segun corresponda. Si un usuario no-admin intenta acceder a `/app` (o a cualquier endpoint que requiera admin), es redirigido automaticamente a `/user`.

## Arquitectura

```text
Frontend web (/app admin, /user cliente)
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
    |
    +--> db/repository.py --------> PostgreSQL (persistencia real)
    +--> db/auth.py ---------------> bcrypt + JWT (autenticacion y roles)
```

Modulos principales:

- `src/pqlicense/license_controller.py`: endpoints HTTP, aliases de compatibilidad, y logica de autorizacion por rol/duenio (`is_admin_token`, `identify_token`, `my_licenses`, `validate_owned_license`, `revoke_owned_license`).
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
- `src/pqlicense/server.py`: API HTTP online, rutas estaticas (`/app`, `/user`, `/login`) y endpoints REST.
- `db/connection.py`: pool de conexion SQLAlchemy a PostgreSQL.
- `db/repository.py`: capa de acceso a datos (licencias, historial, cancelaciones, revocaciones, dispositivos).
- `db/auth.py`: registro, login, hash de contrasenas y JWT.
- `db/schema.sql`: DDL de las 7 tablas.
- `tests/test_license_system.py`: pruebas del flujo principal.

## Requisitos

Usa Python 3.10 o superior.

Dependencias principales:

- `cryptography`: firma clasica Ed25519.
- `pqcrypto`: firma postcuantica ML-DSA-65.
- `sqlalchemy` + `psycopg2` (o driver equivalente): conexion a PostgreSQL.
- `bcrypt`: hash de contrasenas.
- `pyjwt`: generacion y verificacion de tokens JWT.

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

### Base de datos

Se requiere PostgreSQL 18 corriendo localmente con una base llamada `reto_tendencias`. Aplica el esquema:

```powershell
psql -U postgres -d reto_tendencias -f db/schema.sql
```

Variables de entorno relevantes (ver `.env.example`):

```text
PQLICENSE_JWT_SECRET=una-clave-larga-y-secreta
PQLICENSE_JWT_EXPIRES_MINUTES=120
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

Guia rapida de uso (como administrador):

1. Entra con el administrador demo:
   - Correo: `admin@reto-tendencias.local`
   - Clave: `admin123`
2. Genera una licencia firmada, asociando el correo real de un cliente registrado en el campo "Cliente" para que quede ligada a su cuenta.
3. Presiona `Validar` para comprobar firmas, expiracion, revocacion y redireccion.
4. Revisa la tabla `Licencias emitidas`.
5. Presiona `Revocar` para cancelar la licencia.
6. Revisa las tablas `Historial` y `Cancelaciones`.

Guia rapida de uso (como cliente final, rol Individual/Empresa):

1. Registra una cuenta desde `/login` (pestana de registro), o usa una ya creada.
2. Inicia sesion — el sistema te redirige automaticamente a `/user`.
3. Consulta tus licencias propias en la tabla "Mis licencias".
4. Presiona `Validar` sobre cualquiera de tus licencias para revisar el estado de sus firmas.
5. Presiona `Revocar` si deseas cancelar una licencia activa (pide confirmacion antes de ejecutar).

Desde el panel de administrador puedes:

- Iniciar sesion como administrador.
- Generar una licencia firmada.
- Validar la licencia.
- Revocar la licencia.
- Regenerar claves.
- Ver tabla de licencias emitidas, historial de validaciones y cancelaciones (conectadas a PostgreSQL).
- Descargar la lista de revocacion (CRL) para validacion offline.
- Seleccionar modo de firma: hibrido, clasico legado o postcuantico futuro.
- Agregar plan y huella de dispositivo.
- Ver el JSON de la licencia y la redireccion resultante.
- Ver detalles de verificacion de firma clasica y firma postcuantica.

Desde el panel de usuario final puedes:

- Ver unicamente las licencias propias (filtradas por duenio real en la base de datos).
- Validar cualquiera de tus licencias sin necesidad de pegar JSON manualmente.
- Revocar una licencia propia, con confirmacion previa.

El frontend usa el mismo backend de validacion que la API y guarda claves/revocaciones de demostracion en `demo_output/`.

Credenciales admin por defecto para demo:

```text
correo: admin@reto-tendencias.local
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
- `.env.example` muestra variables configurables sin incluir secretos reales, incluyendo `PQLICENSE_JWT_SECRET`.
- No se requiere ninguna ruta local especifica de la computadora original.
- `requirements.txt` instala `pqcrypto` para activar ML-DSA-65 real, ademas de `sqlalchemy`, `bcrypt` y `pyjwt`.
- Ninguna contrasena ni clave privada se sube al repositorio; las contrasenas de usuarios se almacenan como hash bcrypt en la base de datos local de cada quien.

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

## Endpoints

Autenticacion y registro:

- `POST /api/auth/register`: registra un usuario nuevo (Individual, Empresa o Admin).
- `POST /api/admin/login`: autentica cualquier rol y devuelve token JWT, rol y nombre.

Panel administrador (requieren token con rol Admin):

- `POST /api/licenses/generate`: genera licencia `pqlicense/v2` y la persiste en PostgreSQL, ligada al usuario correspondiente por correo.
- `POST /api/licenses/{id}/cancel`: revoca manualmente una licencia (cualquiera, no solo propias).
- `GET /api/licenses`: lista todas las licencias emitidas.
- `GET /api/historial`: historial de validaciones.
- `GET /api/cancelaciones`: historial de cancelaciones.
- `GET /api/licenses/revocations`: devuelve la lista de revocacion firmada (CRL).
- `POST /api/reset-keys`: regenera el par de claves del sistema.

Panel de usuario final (requieren token valido de cualquier rol; el sistema verifica duenio):

- `GET /api/my-licenses`: lista las licencias del usuario autenticado.
- `POST /api/my-licenses/validate`: revalida una licencia propia por su codigo, usando el documento completo guardado al emitirla.
- `POST /api/my-licenses/cancel`: revoca una licencia propia (verifica duenio antes de ejecutar; queda registrada la cancelacion con el usuario responsable).

Publicos (sin autenticacion):

- `POST /api/licenses/validate`: valida online/offline con firmas, expiracion, dispositivo y revocacion, a partir del JSON completo de la licencia.
- `GET /api/licenses/state`: devuelve estado publico del sistema sin claves privadas.

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

El documento completo (`schema` + `payload` + `signatures`) se persiste integro en la columna `payload` de la tabla `licencias`, ademas de guardarse por separado en `firma_postcuantica` y `firma_clasica` para consultas rapidas. Esto permite revalidar una licencia despues de emitida sin depender de que el cliente conserve el archivo original.

## Notas de seguridad

- Las claves privadas nunca se envian al frontend.
- Las respuestas de estado solo incluyen claves publicas.
- Generar, listar, revocar (por admin) y regenerar claves requiere token con rol Admin.
- Un usuario Individual/Empresa solo puede ver, validar y revocar licencias de las que es duenio; cualquier intento sobre licencias de otro usuario responde con error de autorizacion.
- Las contrasenas se almacenan con hash bcrypt; nunca en texto plano.
- Los tokens JWT expiran automaticamente segun `PQLICENSE_JWT_EXPIRES_MINUTES`.
- `demo_output/` esta ignorado por Git porque contiene claves y revocaciones locales.
- Para produccion, las claves privadas deben vivir en un almacén seguro o HSM/KMS, y `PQLICENSE_JWT_SECRET` debe definirse fuera del codigo mediante un gestor de secretos.
- La revocacion offline depende de una lista firmada reciente; si el cliente nunca vuelve a conectarse, no puede conocer cancelaciones nuevas.
- El provider `ML-DSA-65` usa `pqcrypto`; para produccion formal se debe validar la libreria, version, plataforma y politica de manejo de claves.
- Se recomienda rotacion de claves y versionado por `key_id`.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas cubren licencia valida, licencia alterada, vencimiento, revocacion firmada, lista de revocacion manipulada, endpoints nuevos, aliases anteriores, modos de firma, ML-DSA-65 con `pqcrypto`, login admin, listados y proteccion contra exposicion de claves privadas.

## Siguiente paso para produccion

Endurecer despliegue: usar HTTPS, migraciones formales de base de datos, almacenamiento seguro de claves, rotacion por `key_id`, logs de auditoria, y credenciales/secretos fuera del codigo mediante un gestor de secretos dedicado (HSM/KMS/vault). Evaluar tambien si el flujo de autoservicio (usuarios generando sus propias licencias) se incorpora, y bajo que reglas de limite y validacion.