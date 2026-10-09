from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import BorradoSeguroMixin, TenantMixin
from apps.core.permissions import CentroPermission

from . import services
from .models import BloqueoAgenda, Cabina, Cita, DisponibilidadProfesional, Profesional, Servicio
from .serializers import (BloqueoSerializer, CabinaSerializer, CitaSerializer, DisponibilidadSerializer,
                          ProfesionalSerializer, ServicioSerializer)


class CabinaViewSet(BorradoSeguroMixin, TenantMixin, viewsets.ModelViewSet):
    queryset = Cabina.objects.all().order_by("id")
    serializer_class = CabinaSerializer
    permission_classes = [CentroPermission]
    filterset_fields = ["activa"]


class ServicioViewSet(BorradoSeguroMixin, TenantMixin, viewsets.ModelViewSet):
    queryset = Servicio.objects.all().order_by("id")
    serializer_class = ServicioSerializer
    permission_classes = [CentroPermission]
    filterset_fields = ["activo"]


class ProfesionalViewSet(BorradoSeguroMixin, TenantMixin, viewsets.ModelViewSet):
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


class CitaViewSet(TenantMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                  mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Cita.objects.select_related("clienta", "servicio").prefetch_related("recordatorios")
    serializer_class = CitaSerializer
    permission_classes = [CentroPermission]
    filterset_fields = {"estado": ["exact"], "profesional": ["exact"], "cabina": ["exact"], "clienta": ["exact"],
                        "hora_inicio": ["gte", "lte", "date"]}
    ordering_fields = ["hora_inicio"]

    def _cambiar(self, request, nuevo):
        cita = self.get_object()
        services.cambiar_estado(cita, nuevo)
        return Response(self.get_serializer(cita).data)

    @action(detail=True, methods=["post"])
    def confirmar(self, request, pk=None):
        return self._cambiar(request, Cita.Estado.CONFIRMADA)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        return self._cambiar(request, Cita.Estado.CANCELADA)

    @action(detail=True, methods=["post"])
    def completar(self, request, pk=None):
        return self._cambiar(request, Cita.Estado.COMPLETADA)

    @action(detail=True, methods=["post"], url_path="no-asistio")
    def no_asistio(self, request, pk=None):
        return self._cambiar(request, Cita.Estado.NO_ASISTIO)
