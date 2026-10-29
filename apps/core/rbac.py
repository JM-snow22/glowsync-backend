"""Matriz RBAC por negocio. Fuente única de verdad para la API y para el menú dinámico.

- ADMIN_SAAS es superadmin: acceso total fijo, no depende de la matriz ni se puede recortar.
- El módulo "centros" (Negocios) es exclusivo del ADMIN_SAAS y no se delega.
- ADMIN_SAAS edita la matriz de cualquier negocio; ADMIN_NEGOCIO edita la de su negocio,
  solo para Recepcionista y Esteticista.
"""
from .models import PermisoRol, PermisoUsuario, Usuario

R = Usuario.Rol
MODULOS = ("dashboard", "citas", "clientas", "fichas", "usuarios", "centros")
ROLES = tuple(R.values)
# Orden del menú; "rbac" (Permisos) no es un módulo de datos, siempre es visible.
MENU_ORDEN = ("centros", "dashboard", "citas", "clientas", "fichas", "usuarios", "rbac")
SOLO_LECTURA = {"dashboard"}
# Módulos que se pueden personalizar por rol o por persona ("centros" nunca se delega).
MODULOS_DELEGABLES = ("dashboard", "citas", "clientas", "fichas", "usuarios")  # módulos sin operaciones de escritura

# 0 = sin acceso, 1 = solo lectura, 2 = lectura y escritura
PREDETERMINADOS = {
    "dashboard": {"ADMIN_SAAS": 1, "ADMIN_NEGOCIO": 1, "RECEPCIONISTA": 1, "ESTETICISTA": 0},
    "citas": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 2, "RECEPCIONISTA": 2, "ESTETICISTA": 1},
    "clientas": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 2, "RECEPCIONISTA": 2, "ESTETICISTA": 1},
    "fichas": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 2, "RECEPCIONISTA": 2, "ESTETICISTA": 2},
    "usuarios": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 2, "RECEPCIONISTA": 2, "ESTETICISTA": 0},
    "centros": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 0, "RECEPCIONISTA": 0, "ESTETICISTA": 0},
}

VIEW_MODULE = {
    "ResumenView": "dashboard", "CitaViewSet": "citas", "ClientaViewSet": "clientas",
    "FichaViewSet": "fichas", "UsuarioViewSet": "usuarios",
}


def es_superadmin(user):
    return bool(user and user.is_authenticated and user.rol == R.ADMIN_SAAS)


def roles_editables(user):
    """Columnas de la matriz que este usuario puede modificar."""
    if es_superadmin(user):
        return [R.ADMIN_NEGOCIO, R.RECEPCIONISTA, R.ESTETICISTA]
    if user.is_authenticated and user.rol == R.ADMIN_NEGOCIO:
        return [R.RECEPCIONISTA, R.ESTETICISTA]
    return []


def es_protegida(modulo, rol):
    return rol == R.ADMIN_SAAS or modulo == "centros"


def nivel_permiso(centro_id, rol, modulo, usuario_id=None):
    """Consulta el permiso vigente en cada request; sin caché que deje permisos revocados activos.
    Orden: permiso personal de la persona > permiso de su rol en el negocio > predeterminado."""
    if modulo not in MODULOS or rol not in ROLES:
        return 0
    if es_protegida(modulo, rol):
        return PREDETERMINADOS[modulo][rol]
    if usuario_id:
        personal = (PermisoUsuario.objects.filter(usuario_id=usuario_id, modulo=modulo)
                    .values_list("nivel", flat=True).first())
        if personal is not None:
            return personal
    nivel = (PermisoRol.objects.filter(centro_id=centro_id, rol=rol, modulo=modulo)
             .values_list("nivel", flat=True).first())
    return PREDETERMINADOS[modulo][rol] if nivel is None else nivel


def matriz(centro_id):
    result = {m: dict(roles) for m, roles in PREDETERMINADOS.items()}
    for p in PermisoRol.objects.filter(centro_id=centro_id).values("rol", "modulo", "nivel"):
        if not es_protegida(p["modulo"], p["rol"]) and p["modulo"] in result and p["rol"] in result[p["modulo"]]:
            result[p["modulo"]][p["rol"]] = p["nivel"]
    return result


def permisos_usuario(user, centro_id):
    """{modulo: nivel} efectivo para el usuario en el negocio indicado."""
    if es_superadmin(user):
        return {m: PREDETERMINADOS[m][R.ADMIN_SAAS] for m in MODULOS}
    if not centro_id:
        return {m: 0 for m in MODULOS}
    m_actual = matriz(centro_id)
    result = {m: m_actual[m][user.rol] for m in MODULOS}
    for p in PermisoUsuario.objects.filter(usuario_id=user.id).values("modulo", "nivel"):
        if p["modulo"] in MODULOS_DELEGABLES:
            result[p["modulo"]] = p["nivel"]
    return result


def puede_gestionar_usuario(actor, objetivo):
    """Quién puede personalizar los permisos de quién."""
    if objetivo.rol == R.ADMIN_SAAS or actor.pk == objetivo.pk:
        return False
    if es_superadmin(actor):
        return True
    return (actor.rol == R.ADMIN_NEGOCIO and actor.centro_id == objetivo.centro_id
            and objetivo.rol in (R.RECEPCIONISTA, R.ESTETICISTA))


def detalle_permisos_usuario(objetivo):
    """Por módulo: nivel de su rol, nivel personal (o None) y el efectivo."""
    m_actual = matriz(objetivo.centro_id)
    personales = dict(PermisoUsuario.objects.filter(usuario=objetivo).values_list("modulo", "nivel"))
    return {m: {"rol": m_actual[m][objetivo.rol], "personal": personales.get(m),
                "efectivo": personales.get(m, m_actual[m][objetivo.rol])}
            for m in MODULOS_DELEGABLES}


def menu_usuario(user, centro_id):
    """Menú dinámico calculado en el servidor a partir de la matriz vigente."""
    permisos = permisos_usuario(user, centro_id)
    editables = roles_editables(user)
    items = []
    for modulo in MENU_ORDEN:
        if modulo == "rbac":
            items.append({"modulo": "rbac", "escritura": bool(editables)})
        elif permisos[modulo] > 0:
            items.append({"modulo": modulo, "escritura": permisos[modulo] == 2})
    return items
