# GlowSync — Backend (Django + DRF)

API REST multitenant para agendamiento de centros de estética, con **reasignación exprés** de citas canceladas por WhatsApp.

**Stack:** Python 3.12 · Django 5 · Django REST Framework · PostgreSQL 16 · Celery + Redis · JWT · WhatsApp Cloud API

## 1. Arrancar en 5 minutos

### Opción A — Docker (recomendada)
```bash
cp .env.example .env
docker compose up --build -d
docker compose exec web python manage.py seed_demo --n 100
```
API en http://localhost:8000/api/ · Documentación interactiva en http://localhost:8000/api/docs/

### Opción B — Local
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                       # ajusta credenciales de PostgreSQL
python manage.py migrate
python manage.py seed_demo --n 100
python manage.py runserver
# En otra terminal (recordatorios y vencimiento de ofertas):
celery -A config worker -l info
```
Necesitas PostgreSQL y Redis corriendo. Sin Redis, pon `CELERY_EAGER=True` en `.env` para desarrollo
(las tareas se ejecutan al instante, ignorando la hora programada).

## 2. Datos de ejemplo (`seed_demo`)
`python manage.py seed_demo --n 100 [--reset]` crea un centro demo con **100 clientas (con ficha) y 100 citas**
(60 % pasadas, 40 % futuras, sin cruces), más 138 pagos, 80 recordatorios, 4 cabinas, 8 servicios,
5 profesionales con turnos, un bloqueo de agenda y 10 clientas en lista de espera.

| Usuario | Clave | Rol |
|---|---|---|
| admin@glowsync.co | Admin12345! | ADMIN_SAAS |
| recepcion@glowsync.co | Recep12345! | RECEPCIONISTA |
| esteticista1@glowsync.co | Estet12345! | ESTETICISTA |

⚠️ Solo para desarrollo. Nunca cargues el seed en producción.

## 3. Endpoints principales
Todos bajo `/api/` y con `Authorization: Bearer <access>` salvo login y webhooks.

| Recurso | Ruta | Notas |
|---|---|---|
| Login / refresh / yo | `auth/login/`, `auth/refresh/`, `GET/PATCH auth/me/` | Login limitado a 20/min. `PATCH auth/me/ {"idioma":"en"}` cambia el idioma |
| Centros (SaaS) | `centros/`, `centros/{id}/usuarios/` | Solo ADMIN_SAAS |
| Equipo | `usuarios/` | Recepcionista gestiona su centro |
| Catálogo | `cabinas/`, `servicios/`, `profesionales/`, `disponibilidades/`, `bloqueos/` | |
| Clientas | `clientas/`, `fichas/` | Esteticista puede editar fichas |
| Citas | `citas/` + `POST citas/{id}/confirmar|cancelar|completar|no-asistio/` | 409 si hay cruce |
| Lista de espera | `espera/`, `ofertas/` | |
| Pagos | `pagos/` | Seña = precio × % seña |
| Dashboard | `dashboard/resumen/?desde=&hasta=` | Inasistencia, dinero recuperado, ingresos |
| Webhooks | `webhooks/whatsapp/`, `webhooks/pagos/` | Validan firma HMAC |

## 4. Cómo funciona lo importante
- **Multitenant:** todo lleva `centro`; `TenantMixin` filtra por el centro del JWT y `TenantPKField` impide referenciar objetos de otro centro.
- **Anti-solapamiento (PB-05):** además de validar en código, PostgreSQL tiene dos `ExclusionConstraint` (`sin_cruce_cabina`, `sin_cruce_profesional`). Si dos personas reservan a la vez, una recibe **409**.
- **Reasignación exprés (PB-10):** al cancelar (`cambiar_estado`) se dispara `iniciar_reasignacion` → busca la clienta más antigua de la lista de espera compatible (servicio, fecha, rango horario) → crea `OfertaReasignacion` con `expira_en = now + OFERTA_MINUTOS` → envía la plantilla con botones Aceptar/Rechazar → programa `expirar_oferta`. Si rechaza o vence, sigue con la siguiente. Aceptar usa `SELECT ... FOR UPDATE` y la restricción de BD evita doble venta.
- **Recordatorios (PB-08):** al crear la cita se programan 48 h y 24 h antes (Celery `eta`). Las tareas son idempotentes y se omiten si la cita ya no está activa.

## 5. WhatsApp: plantillas que debes crear en Meta (aprobación toma tiempo)
Idioma `es`. Los botones son de **respuesta rápida**; el payload lo envía el backend.

**`recordatorio_cita`** — Cuerpo: `Hola {{1}}, te recordamos tu cita de {{2}} el {{3}} en {{4}}. ¿Confirmas?` — Botones: *Confirmar*, *Cancelar*

**`oferta_reasignacion`** — Cuerpo: `Hola {{1}}, se liberó un cupo para {{2}} el {{3}}. Tienes {{4}} minutos para tomarlo.` — Botones: *Aceptar*, *Rechazar*

Configura en Meta el webhook `https://TU-DOMINIO/api/webhooks/whatsapp/` con tu `WHATSAPP_VERIFY_TOKEN`,
y rellena `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET` y `WHATSAPP_ENABLED=True`.
Con `WHATSAPP_ENABLED=False` los mensajes solo se registran en el log.

## 6. Multilenguaje (español / inglés)
Todo el backend está internacionalizado con el sistema de traducción de Django.

- **Idioma de las respuestas de la API.** Prioridad: (1) cabecera `Accept-Language: en|es` que envía el selector de idioma del frontend; (2) idioma guardado en el perfil del usuario (`PATCH /api/auth/me/ {"idioma": "en"}`); (3) español por defecto. La respuesta incluye la cabecera `Content-Language`.
- **Qué se traduce:** mensajes de error y validación (propios, de DRF y de JWT), etiquetas de estados y roles, el admin de Django y los mensajes de WhatsApp.
- **WhatsApp por clienta.** Cada `Clienta` tiene `idioma` (es/en), útil para turistas. Las plantillas se envían con el código de idioma de la clienta y las respuestas del bot también salen en su idioma, sin importar el idioma del servidor.
- **Plantillas de Meta:** crea cada plantilla en **los dos idiomas con el mismo nombre**:
  - `recordatorio_cita` (en): `Hi {{1}}, this is a reminder of your {{2}} appointment on {{3}} at {{4}}. Do you confirm?` — Botones: *Confirm*, *Cancel*
  - `oferta_reasignacion` (en): `Hi {{1}}, a slot opened up for {{2}} on {{3}}. You have {{4}} minutes to take it.` — Botones: *Accept*, *Reject*
- **Agregar o cambiar textos:** envuelve el texto con `_("...")` y ejecuta:
  ```bash
  python manage.py makemessages -l en --no-location --no-obsolete
  # edita locale/en/LC_MESSAGES/django.po y escribe la traducción en msgstr
  python manage.py compilemessages
  ```
  Requiere las herramientas GNU gettext (Mac: `brew install gettext` · Ubuntu: `sudo apt install gettext` · Windows: instalador de gettext).
- **Agregar otro idioma:** añádelo a `LANGUAGES` en `settings.py` y a `Idioma` en `apps/core/models.py`, y corre `makemessages -l fr`.
- **No se traduce** el contenido que cada centro escribe (nombres de servicios, observaciones). Si lo necesitas, el siguiente paso es agregar campos como `nombre_en` o usar `django-modeltranslation`.
- **Frontend:** debe tener su propio archivo de textos (por ejemplo `react-i18next`), guardar el idioma elegido y enviarlo en `Accept-Language` en cada petición.

## 7. Pruebas
```bash
python manage.py test apps
```
75 pruebas contra PostgreSQL real: multilenguaje (es/en), aislamiento entre centros, 409 por cruce (cabina y profesional), restricción de BD,
reasignación completa (rechazo → siguiente → aceptación), vencimiento, hueco ocupado, firmas de webhooks e idempotencia de pagos.

## 8. Estado y pendientes

**Listo:** autenticación JWT y roles, multilenguaje es/en, multitenant, suscripción por centro, catálogo, disponibilidad y bloqueos,
citas con anti-solapamiento, fichas, WhatsApp (envío + webhook), recordatorios, lista de espera, reasignación exprés,
pagos con webhook idempotente, dashboard, Docker, OpenAPI.

**Pendiente antes de vender / producción:**
1. **Pasarela de pago real:** `PagoViewSet` crea el cobro pendiente pero falta generar el link de checkout (Wompi/ePayco/Bold) y adaptar `PagoWebhook` a su formato y firma. Liberar el cupo si la seña no se paga en X minutos.
2. **Adelanto de turno:** hoy una oferta aceptada crea una cita nueva; si la clienta ya tenía una cita posterior, hay que cancelarla/moverla.
3. **Ficha estética:** cifrar `alergias`/`observaciones` y registrar quién la consulta (Ley 1581 de 2012).
4. **Endpoint de huecos libres** para que el panel sugiera horarios.
5. **Cobro de tu propia suscripción** a los centros (hoy se gestiona a mano con `estado_suscripcion` y `fecha_vencimiento`).
6. **Producción:** `DEBUG=False`, `SECRET_KEY` real, HTTPS (Caddy/Nginx), backups diarios de PostgreSQL, Redis con AOF (ya en el compose), Sentry y monitoreo de uptime.
7. Esteticista restringida a sus propias citas (hoy ve las de todo el centro).
