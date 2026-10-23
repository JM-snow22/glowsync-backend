# GlowSync Backend

API REST multitenant para centros de estética. Gestiona clientas, agenda, pagos y recordatorios, y recupera ingresos ofreciendo por WhatsApp los cupos de citas canceladas a la lista de espera.

**Stack:** Python 3.12+ · Django 5 · Django REST Framework · PostgreSQL (Neon) · JWT · Celery · WhatsApp Cloud API · Swagger/OpenAPI

## Contenido

1. [Características](#características)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Variables de entorno](#variables-de-entorno)
5. [Datos de ejemplo](#datos-de-ejemplo)
6. [Referencia de la API](#referencia-de-la-api)
7. [WhatsApp](#whatsapp)
8. [Multilenguaje](#multilenguaje)
9. [Pruebas](#pruebas)
10. [Docker](#docker-opcional)
11. [Solución de problemas](#solución-de-problemas)
12. [Pendientes para producción](#pendientes-para-producción)

## Características

- Inicio de sesión con JWT y tres roles de usuario: `ADMIN_SAAS`, `RECEPCIONISTA` y `ESTETICISTA`.
- Arquitectura multitenant: cada centro solo puede ver y manejar su propia información.
- Agenda sin cruces de horario, respaldada por restricciones de PostgreSQL que devuelven un `409 Conflict` cuando hay conflicto.
- Reasignación exprés: cuando se cancela una cita, el cupo liberado se ofrece por WhatsApp a las clientas de la lista de espera.
- Recordatorios enviados automáticamente 48 h y 24 h antes de cada cita.
- Registro de pagos mediante un webhook idempotente, que evita duplicados.
- Dashboard con indicadores de inasistencia, ingresos y dinero recuperado.
- Disponible en español e inglés.
- Documentación interactiva de la API con Swagger.

## Requisitos

- Python 3.12 o superior
- Git
- Una base de datos PostgreSQL con la extensión `btree_gist` (recomendado: [Neon](https://neon.tech), plan gratuito)


## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/JM-snow22/glowsync-backend.git
cd glowsync_backend
```

### 2. Crear el entorno virtual e instalar dependencias

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configurar el entorno

Cree un archivo `.env` en la raíz del proyecto (junto a `manage.py`). Puede partir de la plantilla:

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Complete las variables según la sección [Variables de entorno](#variables-de-entorno).

### 4. Crear las tablas y cargar los datos

```bash
python manage.py migrate
python manage.py seed_demo --n 100
```

Con una base remota el seed puede tardar varios minutos. No lo interrumpa hasta ver el mensaje `Listo: 100 clientas, 100 citas...`.

> Si la base de datos ya fue cargada (por ejemplo, la instancia compartida del proyecto), omita este paso.

### 5. Iniciar el servidor

```bash
python manage.py runserver
```

| Recurso | URL |
|---|---|
| Health check | http://127.0.0.1:8000/api/health/ |
| Documentación Swagger | http://127.0.0.1:8000/api/docs/ |
| Panel de administración | http://127.0.0.1:8000/admin/ |
| API | http://127.0.0.1:8000/api/ |

### 6. Probar la autenticación

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"recepcion@glowsync.co","password":"Recep12345!"}'

curl http://127.0.0.1:8000/api/clientas/ \
  -H "Authorization: Bearer <access>"
```

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave secreta de Django | cadena larga y aleatoria |
| `DEBUG` | Modo depuración (`False` en producción) | `True` |
| `ALLOWED_HOSTS` | Hosts permitidos, separados por coma | `*` |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos del frontend | `http://localhost:3000` |
| `POSTGRES_DB` | Nombre de la base de datos | `neondb` |
| `POSTGRES_USER` | Usuario | `neondb_owner` |
| `POSTGRES_PASSWORD` | Contraseña | |
| `POSTGRES_HOST` | Host del servidor | `ep-xxxx.us-east-2.aws.neon.tech` |
| `POSTGRES_PORT` | Puerto | `5432` |
| `POSTGRES_SSLMODE` | Modo SSL; `require` para bases en la nube | `require` |
| `REDIS_URL` | Broker de Celery | `redis://localhost:6379/0` |
| `CELERY_EAGER` | `True` ejecuta las tareas de inmediato, sin Redis | `True` |
| `WHATSAPP_ENABLED` | `False` solo registra los mensajes en el log | `False` |
| `WHATSAPP_TOKEN` | Token de la Cloud API de Meta | |
| `WHATSAPP_PHONE_NUMBER_ID` | ID del número de WhatsApp | |
| `WHATSAPP_APP_SECRET` | Secreto de la app (firma del webhook) | |
| `WHATSAPP_VERIFY_TOKEN` | Token de verificación del webhook | `glowsync-verify` |
| `OFERTA_MINUTOS` | Vigencia de una oferta de reasignación | `12` |
| `PAGOS_WEBHOOK_SECRET` | Secreto de firma del webhook de pagos | |

Ejemplo mínimo para desarrollo:

```env
SECRET_KEY=cambia-esto-por-una-clave-larga
DEBUG=True
ALLOWED_HOSTS=*
CORS_ALLOWED_ORIGINS=http://localhost:3000

POSTGRES_DB=neondb
POSTGRES_USER=<usuario>
POSTGRES_PASSWORD=<contraseña>
POSTGRES_HOST=<host>.neon.tech
POSTGRES_PORT=5432
POSTGRES_SSLMODE=require

CELERY_EAGER=True
WHATSAPP_ENABLED=False
PAGOS_WEBHOOK_SECRET=<secreto>
```

El archivo `.env` está en `.gitignore` y no debe subirse al repositorio. Compártalo únicamente por un canal privado.

## Datos de ejemplo

El comando `seed_demo` crea un centro de demostración:

| Elemento | Cantidad |
|---|---|
| Clientas con ficha estética | 100 |
| Citas (60 % pasadas, 40 % futuras, sin cruces) | 100 |
| Pagos | ~140 |
| Recordatorios | ~80 |
| Cabinas | 4 |
| Servicios | 8 |
| Profesionales con horario | 5 |
| Lista de espera | 10 |

Usuarios de prueba (solo desarrollo):

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador SaaS | `admin@glowsync.co` | `Admin12345!` |
| Recepcionista | `recepcion@glowsync.co` | `Recep12345!` |
| Esteticista | `esteticista1@glowsync.co` | `Estet12345!` |

No ejecute el seed en producción. La opción `--reset` falla si ya existen citas y pagos, porque están protegidos por claves foráneas.

## Referencia de la API

Todas las rutas cuelgan de `/api/` y requieren `Authorization: Bearer <access>`, excepto login, health y webhooks.

| Módulo | Ruta | Notas |
|---|---|---|
| Salud | `GET health/` | Público |
| Autenticación | `POST auth/login/`, `POST auth/refresh/`, `GET/PATCH auth/me/` | Login limitado a 20/min |
| Centros | `centros/`, `centros/{id}/usuarios/` | Solo `ADMIN_SAAS` |
| Usuarios | `usuarios/` | La recepcionista gestiona su centro |
| Catálogo | `cabinas/`, `servicios/`, `profesionales/`, `disponibilidades/`, `bloqueos/` | CRUD |
| Clientas | `clientas/`, `fichas/` | La esteticista puede editar fichas |
| Citas | `citas/` | `409` si hay cruce |
| Acciones de cita | `POST citas/{id}/confirmar`, `cancelar`, `completar`, `no-asistio` | Cambio de estado |
| Lista de espera | `espera/`, `ofertas/` | Reasignación |
| Pagos | `pagos/` | Seña = precio × % de seña |
| Dashboard | `GET dashboard/resumen/?desde=&hasta=` | Métricas |
| Webhooks | `POST webhooks/whatsapp/`, `POST webhooks/pagos/` | Validan firma HMAC |
| Documentación | `docs/`, `schema/` | Swagger / OpenAPI |

## WhatsApp

Cree estas plantillas en Meta, en español e inglés y con el mismo nombre:

| Plantilla | Mensaje (es) | Botones |
|---|---|---|
| `recordatorio_cita` | Hola {{1}}, te recordamos tu cita de {{2}} el {{3}} en {{4}}. ¿Confirmas? | Confirmar, Cancelar |
| `oferta_reasignacion` | Hola {{1}}, se liberó un cupo para {{2}} el {{3}}. Tienes {{4}} minutos para tomarlo. | Aceptar, Rechazar |

Configure en Meta el webhook `https://<su-dominio>/api/webhooks/whatsapp/` con su `WHATSAPP_VERIFY_TOKEN`, complete las credenciales y establezca `WHATSAPP_ENABLED=True`. Con `WHATSAPP_ENABLED=False` los mensajes solo se registran en el log.

## Multilenguaje

El idioma de las respuestas se determina en este orden: cabecera `Accept-Language`, idioma del perfil del usuario (`PATCH /api/auth/me/` con `{"idioma": "en"}`) y, por defecto, español. Cada clienta tiene su propio idioma para los mensajes de WhatsApp.

Para agregar o modificar textos, envuélvalos con `_("...")` y ejecute:

```bash
python manage.py makemessages -l en --no-location --no-obsolete
python manage.py compilemessages
```

El contenido que escribe cada centro (nombres de servicios, observaciones) no se traduce.

## Pruebas

```bash
python manage.py test apps
```

Incluye 75 pruebas sobre PostgreSQL real: aislamiento entre centros, `409` por cruce, reasignación completa, vencimiento de ofertas, firmas de webhooks e idempotencia de pagos.

## Docker (opcional)

Levanta PostgreSQL y Redis locales en lugar de usar una base en la nube.

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec web python manage.py seed_demo --n 100
```

## Solución de problemas

| Síntoma | Causa y solución |
|---|---|
| Django se conecta a `localhost` | El `.env` no está junto a `manage.py` o se llama `.env.txt` |
| `seed_demo` parece detenido | Es lento con bases remotas; no lo interrumpa |
| `seed_demo --reset` lanza `ProtectedError` | Ya existen citas y pagos; no use `--reset` |
| `GET /` devuelve `404` | Es normal; use `/api/`, `/api/docs/` o `/admin/` |
| Error de SSL al conectar | Verifique `POSTGRES_SSLMODE=require` |

## Pendientes para producción

1. Pasarela de pago real (checkout con Wompi, ePayco o Bold) y liberación del cupo si no se paga la seña.
2. Adelanto de turno cuando una clienta acepta una oferta.
3. Cifrado de la ficha estética y auditoría de accesos (Ley 1581 de 2012).
4. Endpoint de huecos libres para sugerir horarios.
5. Cobro de la suscripción a los centros.
6. `DEBUG=False`, HTTPS, copias de seguridad de PostgreSQL y monitoreo.
7. Restringir a la esteticista a sus propias citas.
