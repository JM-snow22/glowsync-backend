from rest_framework import serializers
from django.utils.translation import gettext as _
from apps.agenda.models import Servicio
from apps.clientas.models import Clienta
from apps.core.serializers import TenantPKField

from .models import ListaEspera, OfertaReasignacion


class ListaEsperaSerializer(serializers.ModelSerializer):
    clienta = TenantPKField(queryset=Clienta.objects.all())
    servicio = TenantPKField(queryset=Servicio.objects.all())
    clienta_nombre = serializers.CharField(source="clienta.nombre", read_only=True)

    class Meta:
        model = ListaEspera
        fields = ["id", "clienta", "clienta_nombre", "servicio", "fecha_deseada", "hora_desde", "hora_hasta", "estado", "creado_en"]
        read_only_fields = ["estado", "creado_en"]

    def validate(self, attrs):
        if attrs["hora_hasta"] <= attrs["hora_desde"]:
            raise serializers.ValidationError(_("hora_hasta debe ser mayor que hora_desde."))
        return attrs


class OfertaSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfertaReasignacion
        fields = ["id", "cita_liberada", "espera", "orden", "enviada_en", "expira_en", "estado", "respondida_en"]
