from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario


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
        if not (u.is_authenticated and u.centro_id):
            return False
        if not u.centro.suscripcion_activa:
            self.message = _("La suscripción del centro está vencida o suspendida.")
            return False
        if (
            request.method not in SAFE_METHODS
            and u.rol == Usuario.Rol.ESTETICISTA
            and not getattr(view, "esteticista_puede_escribir", False)
        ):
            self.message = _("Tu rol solo permite consultar.")
            return False
        return True


class SoloRecepcionista(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.rol == Usuario.Rol.RECEPCIONISTA