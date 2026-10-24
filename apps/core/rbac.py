"""Matriz RBAC por negocio. La API y el frontend comparten estos valores por defecto.

La autoridad global ADMIN_SAAS y la gestión de negocios no se delegan.
"""
from .models import PermisoRol, Usuario

MODULOS = ("dashboard", "citas", "clientas", "fichas", "usuarios", "centros")
ROLES = tuple(Usuario.Rol.values)
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


def nivel_permiso(centro_id, rol, modulo):
    """Consulta el permiso vigente en cada request; sin caché que deje permisos revocados activos."""
    if modulo not in MODULOS or rol not in ROLES:
        return 0
    if rol == Usuario.Rol.ADMIN_SAAS or modulo == "centros":
        return PREDETERMINADOS[modulo][rol]
    nivel = (PermisoRol.objects.filter(centro_id=centro_id, rol=rol, modulo=modulo)
             .values_list("nivel", flat=True).first())
    return PREDETERMINADOS[modulo][rol] if nivel is None else nivel


def matriz(centro_id):
    result = {m: dict(roles) for m, roles in PREDETERMINADOS.items()}
    for p in PermisoRol.objects.filter(centro_id=centro_id).values("rol", "modulo", "nivel"):
        if p["rol"] != Usuario.Rol.ADMIN_SAAS and p["modulo"] != "centros" and p["modulo"] in result and p["rol"] in result[p["modulo"]]:
            result[p["modulo"]][p["rol"]] = p["nivel"]
    return result
