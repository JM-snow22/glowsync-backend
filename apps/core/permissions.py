from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Centro, Usuario
from rest_framework.exceptions import PermissionDenied, ValidationError


def centro_actual(request):
    """SaaS elige una sede explícita; los demás usuarios solo acceden a la suya."""
    u = request.user
    if u.rol != Usuario.Rol.ADMIN_SAAS:
        if not u.centro_id:
            raise PermissionDenied("No tienes un negocio asignado.")
        return u.centro
    raw = request.headers.get("X-Centro-ID")
    if not raw:
        raise ValidationError({"centro": "Selecciona un negocio para consultar sus datos."})
    try:
        pk = int(raw)
    except (ValueError, TypeError):
        raise ValidationError({"centro": "Identificador inválido."})
    try:
        return Centro.objects.get(pk=pk)
    except Centro.DoesNotExist:
        raise PermissionDenied("El negocio seleccionado no existe.")



class IsAdminSaas(BasePermission):
    """Solo el administrador del SaaS (el dueño del software)."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u.is_authenticated and u.rol == Usuario.Rol.ADMIN_SAAS)


class CentroPermission(BasePermission):
    """Usuario de un centro con suscripción vigente.
    La esteticista es solo lectura salvo que la vista declare `esteticista_puede_escribir = True`."""

    message = _("No tienes acceso a este recurso.")

    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        from .rbac import VIEW_MODULE, nivel_permiso
        if u.rol == Usuario.Rol.ADMIN_SAAS:
            centro_actual(request)
            return True
        if not u.centro_id:
            return False
        if not u.centro.suscripcion_activa:
            self.message = _("La suscripción del centro está vencida o suspendida.")
            return False
        modulo = VIEW_MODULE.get(view.__class__.__name__)
        if modulo:
            nivel = nivel_permiso(u.centro_id, u.rol, modulo, u.id)
            requiere = 1 if request.method in SAFE_METHODS else 2
            return nivel >= requiere
        # Para endpoints no presentes en la matriz se conserva el comportamiento anterior.
        if (request.method not in SAFE_METHODS and u.rol == Usuario.Rol.ESTETICISTA
                and not getattr(view, "esteticista_puede_escribir", False)):
            self.message = _("Tu rol solo permite consultar.")
            return False
        return True


class NegociosPermission(BasePermission):
    """ADMIN_SAAS: todo. Otros roles: según el módulo "centros" de la matriz, solo sobre su negocio
    (ver = 1, editar datos básicos = 2). Crear, eliminar y crear accesos queda para el ADMIN_SAAS."""

    message = _("No tienes acceso a este recurso.")

    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.rol == Usuario.Rol.ADMIN_SAAS:
            return True
        if not u.centro_id or not u.centro.suscripcion_activa:
            return False
        if getattr(view, "action", None) in ("create", "destroy", "crear_usuario"):
            return False
        from .rbac import nivel_permiso
        return nivel_permiso(u.centro_id, u.rol, "centros", u.id) >= (1 if request.method in SAFE_METHODS else 2)


class SoloRecepcionista(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.rol == Usuario.Rol.ADMIN_SAAS:
            return True
        from .rbac import nivel_permiso
        return nivel_permiso(request.user.centro_id, request.user.rol, "usuarios", request.user.id) >= (1 if request.method in SAFE_METHODS else 2)