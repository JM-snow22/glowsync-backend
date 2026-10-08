from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.core.mixins import TenantMixin
from apps.core.permissions import CentroPermission

from .models import Clienta, FichaEstetica
from .serializers import ClientaSerializer, FichaEsteticaSerializer


class ClientaViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Clienta.objects.all().order_by("id")
    serializer_class = ClientaSerializer
    permission_classes = [CentroPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["idioma"]
    search_fields = ["nombre", "telefono_whatsapp"]


class FichaEsteticaViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = FichaEstetica.objects.select_related("clienta").order_by("id")
    serializer_class = FichaEsteticaSerializer
    permission_classes = [CentroPermission]

    # La esteticista puede registrar y consultar fichas.
    esteticista_puede_escribir = True

    # FichaEstetica no tiene un campo "centro".
    # El centro se determina a través de la clienta.
    tenant_lookup = "clienta__centro"

    filterset_fields = ["clienta"]