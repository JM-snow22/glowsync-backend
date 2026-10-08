from rest_framework import viewsets

from apps.core.mixins import TenantMixin
from apps.core.permissions import CentroPermission

from .models import BloqueoAgenda, Cabina, DisponibilidadProfesional, Profesional, Servicio
from .serializers import (BloqueoSerializer, CabinaSerializer, DisponibilidadSerializer,
                          ProfesionalSerializer, ServicioSerializer)


class CabinaViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Cabina.objects.all().order_by("id")
    serializer_class = CabinaSerializer
    permission_classes = [CentroPermission]
    filterset_fields = ["activa"]


class ServicioViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Servicio.objects.all().order_by("id")
    serializer_class = ServicioSerializer
    permission_classes = [CentroPermission]
    filterset_fields = ["activo"]


class ProfesionalViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Profesional.objects.all().order_by("id")
    serializer_class = ProfesionalSerializer
    permission_classes = [CentroPermission]
    filterset_fields = ["activo"]


class DisponibilidadViewSet(TenantMixin, viewsets.ModelViewSet):
    """Turnos semanales. Esta tabla no tiene 'centro' propio: se filtra por el centro del profesional."""

    queryset = DisponibilidadProfesional.objects.all().order_by("profesional", "dia_semana")
    serializer_class = DisponibilidadSerializer
    permission_classes = [CentroPermission]
    tenant_lookup = "profesional__centro"
    filterset_fields = ["profesional", "dia_semana"]


class BloqueoViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = BloqueoAgenda.objects.all().order_by("-inicio")
    serializer_class = BloqueoSerializer
    permission_classes = [CentroPermission]
    filterset_fields = ["profesional"]