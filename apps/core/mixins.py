from django.db.models import ProtectedError
from django.utils.translation import gettext as _
from rest_framework.exceptions import APIException


class TenantMixin:
    """Filtra siempre por el centro del usuario autenticado (aislamiento multitenant).
    Se usa desde el paso 4 en las vistas de cabinas, servicios, citas, etc."""

    tenant_lookup = "centro"

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):  # para la documentación automática
            return qs.none()
        return qs.filter(**{self.tenant_lookup: self.request.user.centro_id})

    def perform_create(self, serializer):
        if self.tenant_lookup == "centro":
            serializer.save(centro=self.request.user.centro)
        else:
            serializer.save()


class ConflictoRelacion(APIException):
    status_code = 409
    default_code = "conflicto_relacion"


class BorradoSeguroMixin:
    """Si algo tiene citas asociadas no se puede borrar (409); se desactiva en su lugar."""

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise ConflictoRelacion(_("No se puede eliminar porque tiene registros asociados. Desactívalo en su lugar."))
