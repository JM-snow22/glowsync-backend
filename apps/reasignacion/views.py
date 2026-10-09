from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import TenantMixin
from apps.core.permissions import CentroPermission

from .models import ListaEspera, OfertaReasignacion
from .serializers import ListaEsperaSerializer, OfertaSerializer


class ListaEsperaViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = ListaEspera.objects.select_related("clienta")
    serializer_class = ListaEsperaSerializer
    permission_classes = [CentroPermission]
    filterset_fields = ["estado", "servicio", "fecha_deseada"]

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        item = self.get_object()
        item.estado = ListaEspera.Estado.CANCELADA
        item.save(update_fields=["estado"])
        return Response(self.get_serializer(item).data)


class OfertaViewSet(TenantMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = OfertaReasignacion.objects.all()
    serializer_class = OfertaSerializer
    permission_classes = [CentroPermission]
    tenant_lookup = "espera__centro"
    filterset_fields = ["estado", "cita_liberada"]
