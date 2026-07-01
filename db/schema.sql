-- Esquema relacional: Reto Mayo - Julio 2026
-- Sistema de Validacion de Licencias Postcuantico
-- 7 tablas segun "Documentacion BD Reto de Tendencias"

-- Tipos ENUM (sugeridos por el equipo en lugar de varchar libres)
DROP TYPE IF EXISTS estado_usuario_enum CASCADE;
CREATE TYPE estado_usuario_enum AS ENUM ('activo', 'inactivo', 'suspendido');

DROP TYPE IF EXISTS estado_licencia_enum CASCADE;
CREATE TYPE estado_licencia_enum AS ENUM ('activa', 'vencida', 'cancelada', 'revocada', 'invalida');

DROP TYPE IF EXISTS tipo_cancelacion_enum CASCADE;
CREATE TYPE tipo_cancelacion_enum AS ENUM ('manual', 'automatica');

DROP TYPE IF EXISTS modo_validacion_enum CASCADE;
CREATE TYPE modo_validacion_enum AS ENUM ('online', 'offline');

DROP TYPE IF EXISTS resultado_validacion_enum CASCADE;
CREATE TYPE resultado_validacion_enum AS ENUM ('valida', 'invalida', 'vencida', 'revocada');

DROP TYPE IF EXISTS estado_dispositivo_enum CASCADE;
CREATE TYPE estado_dispositivo_enum AS ENUM ('activo', 'desactivado');

-- 1. Tipo_de_usuario
DROP TABLE IF EXISTS tipo_de_usuario CASCADE;
CREATE TABLE tipo_de_usuario (
    id_tipo_usuario SERIAL PRIMARY KEY,
    nombre_rol      VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO tipo_de_usuario (nombre_rol) VALUES ('Individual'), ('Empresa'), ('Admin');

-- 2. Usuarios
DROP TABLE IF EXISTS usuarios CASCADE;
CREATE TABLE usuarios (
    id_usuario        SERIAL PRIMARY KEY,
    id_tipo_usuario   INT NOT NULL REFERENCES tipo_de_usuario(id_tipo_usuario),
    nombre_completo   VARCHAR(150) NOT NULL CHECK (char_length(nombre_completo) >= 5),
    correo            VARCHAR(150) NOT NULL UNIQUE,
    contrasena_hash   VARCHAR(255) NOT NULL,
    fecha_de_registro TIMESTAMP NOT NULL DEFAULT NOW(),
    estado            estado_usuario_enum NOT NULL DEFAULT 'activo'
);

-- 3. Licencias
DROP TABLE IF EXISTS licencias CASCADE;
CREATE TABLE licencias (
    id_licencia       SERIAL PRIMARY KEY,
    id_usuario        INT NOT NULL REFERENCES usuarios(id_usuario),
    codigo_licencia   VARCHAR(255) NOT NULL UNIQUE CHECK (char_length(codigo_licencia) >= 8),
    firma_postcuantica JSON NOT NULL,
    firma_clasica     JSON,
    fecha_emision     TIMESTAMP NOT NULL DEFAULT NOW(),
    fecha_expiracion  TIMESTAMP NOT NULL,
    estado            estado_licencia_enum NOT NULL DEFAULT 'activa'
);

-- 4. Cancelaciones
DROP TABLE IF EXISTS cancelaciones CASCADE;
CREATE TABLE cancelaciones (
    id_cancelacion          SERIAL PRIMARY KEY,
    id_licencia             INT NOT NULL REFERENCES licencias(id_licencia),
    id_usuario_responsable  INT REFERENCES usuarios(id_usuario),
    fecha_cancelacion       TIMESTAMP NOT NULL DEFAULT NOW(),
    tipo_cancelacion        tipo_cancelacion_enum NOT NULL,
    motivo                  VARCHAR(255)
);

-- 5. Historial_validaciones
DROP TABLE IF EXISTS historial_validaciones CASCADE;
CREATE TABLE historial_validaciones (
    id_validacion    SERIAL PRIMARY KEY,
    id_licencia      INT NOT NULL REFERENCES licencias(id_licencia),
    fecha_validacion TIMESTAMP NOT NULL DEFAULT NOW(),
    modo             modo_validacion_enum NOT NULL,
    resultado        resultado_validacion_enum NOT NULL
);

-- 6. Dispositivo_Activacion
DROP TABLE IF EXISTS dispositivo_activacion CASCADE;
CREATE TABLE dispositivo_activacion (
    id_dispositivo   SERIAL PRIMARY KEY,
    id_licencia      INT NOT NULL REFERENCES licencias(id_licencia),
    huella_hardware  VARCHAR(255) NOT NULL,
    fecha_activacion TIMESTAMP NOT NULL DEFAULT NOW(),
    estado           estado_dispositivo_enum NOT NULL DEFAULT 'activo'
);

-- 7. Revocaciones_offline
DROP TABLE IF EXISTS revocaciones_offline CASCADE;
CREATE TABLE revocaciones_offline (
    id_revocacion     SERIAL PRIMARY KEY,
    id_licencia       INT NOT NULL REFERENCES licencias(id_licencia),
    codigo_licencia   VARCHAR(255) NOT NULL,
    fecha_revocacion  TIMESTAMP NOT NULL DEFAULT NOW(),
    version_lista     INT NOT NULL
);

-- Indices recomendados
CREATE INDEX idx_licencias_usuario ON licencias(id_usuario);
CREATE INDEX idx_licencias_estado ON licencias(estado);
CREATE INDEX idx_historial_licencia ON historial_validaciones(id_licencia);
CREATE INDEX idx_dispositivo_licencia ON dispositivo_activacion(id_licencia);
CREATE INDEX idx_revocaciones_codigo ON revocaciones_offline(codigo_licencia);