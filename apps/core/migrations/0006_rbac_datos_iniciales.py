"""Siembra el RBAC relacional con los permisos que antes estaban escritos en el código
y vincula a cada usuario existente con su rol (USUARIO_HAS_ROL).

Es una copia congelada a propósito: una migración no debe depender de código que cambiará.
"""
from django.db import migrations

# nivel por módulo y rol: 0 = sin acceso, 1 = solo ver, 2 = ver y editar
NIVELES = {
    "dashboard": {"ADMIN_SAAS": 1, "ADMIN_NEGOCIO": 1, "RECEPCIONISTA": 1, "ESTETICISTA": 0},
    "citas": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 2, "RECEPCIONISTA": 2, "ESTETICISTA": 1},
    "clientas": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 2, "RECEPCIONISTA": 2, "ESTETICISTA": 1},
    "fichas": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 2, "RECEPCIONISTA": 2, "ESTETICISTA": 2},
    "usuarios": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 2, "RECEPCIONISTA": 2, "ESTETICISTA": 0},
    "centros": {"ADMIN_SAAS": 2, "ADMIN_NEGOCIO": 0, "RECEPCIONISTA": 0, "ESTETICISTA": 0},
}
ROLES = ("ADMIN_SAAS", "ADMIN_NEGOCIO", "RECEPCIONISTA", "ESTETICISTA")
SOLO_LECTURA = {"dashboard"}  # sin recurso «.editar»


def sembrar(apps, schema_editor):
    Recurso = apps.get_model("core", "Recurso")
    Rol = apps.get_model("core", "Rol")
    Usuario = apps.get_model("core", "Usuario")

    recursos = {}
    for modulo in NIVELES:
        acciones = ["ver"] if modulo in SOLO_LECTURA else ["ver", "editar"]
        for accion in acciones:
            nombre = f"{modulo}.{accion}"
            recursos[nombre], _ = Recurso.objects.get_or_create(nombre=nombre)

    roles = {}
    for nombre in ROLES:
        roles[nombre], _ = Rol.objects.get_or_create(nombre=nombre)

    through_rr = Rol.recursos.through
    vinculos = []
    for modulo, por_rol in NIVELES.items():
        for rol, nivel in por_rol.items():
            if nivel >= 1:
                vinculos.append(through_rr(rol_id=roles[rol].pk, recurso_id=recursos[f"{modulo}.ver"].pk))
            if nivel >= 2:
                vinculos.append(through_rr(rol_id=roles[rol].pk, recurso_id=recursos[f"{modulo}.editar"].pk))
    through_rr.objects.bulk_create(vinculos, ignore_conflicts=True)

    # Cada usuario existente conserva exactamente el acceso que ya tenía.
    through_ur = Usuario.roles.through
    through_ur.objects.bulk_create(
        [through_ur(usuario_id=u_id, rol_id=roles[rol].pk)
         for u_id, rol in Usuario.objects.values_list("id", "rol") if rol in roles],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0005_rbac_relacional")]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
