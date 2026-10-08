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