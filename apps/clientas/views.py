from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from apps.core.mixins import BorradoSeguroMixin, TenantMixin
from apps.core.permissions import CentroPermission

from .models import Clienta, FichaEstetica
from .serializers import ClientaSerializer, FichaEsteticaSerializer


class ClientaViewSet(BorradoSeguroMixin, TenantMixin, viewsets.ModelViewSet):
    queryset = Clienta.objects.all()
    serializer_class = ClientaSerializer
    permission_classes = [CentroPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["idioma"]
    search_fields = ["nombre", "telefono_whatsapp", "email"]  # ?search=ana
    ordering_fields = ["nombre", "creado_en"]


class FichaViewSet(TenantMixin, viewsets.ModelViewSet):
    """Ficha estética. La esteticista puede editarla (es quien conoce a la clienta en cabina)."""

    queryset = FichaEstetica.objects.select_related("clienta").order_by("id")
    serializer_class = FichaEsteticaSerializer
    permission_classes = [CentroPermission]
    tenant_lookup = "clienta__centro"
    esteticista_puede_escribir = True
    filterset_fields = ["clienta"]
