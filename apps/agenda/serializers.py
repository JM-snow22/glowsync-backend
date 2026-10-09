from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.clientas.models import Clienta
from apps.core.serializers import TenantPKField

from . import services
from .models import (BloqueoAgenda, Cabina, Cita, DisponibilidadProfesional, Profesional, Recordatorio,
                     Servicio)


class CabinaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cabina
        fields = ["id", "nombre", "activa"]

    def validate_nombre(self, value):
        """Dos cabinas del mismo centro no pueden llamarse igual (se valida aquí para dar un 400 claro)."""
        qs = Cabina.objects.filter(centro=self.context["request"].user.centro, nombre__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_("Ya existe una cabina con ese nombre."))
        return value


class ServicioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Servicio
        fields = ["id", "nombre", "duracion_minutos", "precio", "porcentaje_sena", "activo"]


class ProfesionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profesional
        fields = ["id", "nombre", "telefono", "activo", "usuario"]
        read_only_fields = ["usuario"]


class DisponibilidadSerializer(serializers.ModelSerializer):
    profesional = TenantPKField(queryset=Profesional.objects.all())

    class Meta:
        model = DisponibilidadProfesional
        fields = ["id", "profesional", "dia_semana", "hora_desde", "hora_hasta"]

    def validate(self, attrs):
        # En un PATCH pueden venir solo algunos campos: se completan con los valores guardados.
        actual = self.instance
        desde = attrs.get("hora_desde", getattr(actual, "hora_desde", None))
        hasta = attrs.get("hora_hasta", getattr(actual, "hora_hasta", None))
        dia = attrs.get("dia_semana", getattr(actual, "dia_semana", None))
        if desde and hasta and hasta <= desde:
            raise serializers.ValidationError(_("hora_hasta debe ser mayor que hora_desde."))
        if dia is not None and not 0 <= dia <= 6:
            raise serializers.ValidationError(_("dia_semana debe estar entre 0 (lunes) y 6 (domingo)."))
        return attrs


class BloqueoSerializer(serializers.ModelSerializer):
    profesional = TenantPKField(queryset=Profesional.objects.all(), required=False, allow_null=True)

    class Meta:
        model = BloqueoAgenda
        fields = ["id", "profesional", "inicio", "fin", "motivo"]

    def validate(self, attrs):
        actual = self.instance
        inicio = attrs.get("inicio", getattr(actual, "inicio", None))
        fin = attrs.get("fin", getattr(actual, "fin", None))
        if inicio and fin and fin <= inicio:
            raise serializers.ValidationError(_("fin debe ser posterior a inicio."))
        return attrs


class RecordatorioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recordatorio
        fields = ["id", "tipo", "programado_para", "enviado_en", "respuesta"]


class CitaSerializer(serializers.ModelSerializer):
    clienta = TenantPKField(queryset=Clienta.objects.all())
    servicio = TenantPKField(queryset=Servicio.objects.all())
    profesional = TenantPKField(queryset=Profesional.objects.all())
    cabina = TenantPKField(queryset=Cabina.objects.all())
    recordatorios = RecordatorioSerializer(many=True, read_only=True)
    clienta_nombre = serializers.CharField(source="clienta.nombre", read_only=True)
    servicio_nombre = serializers.CharField(source="servicio.nombre", read_only=True)

    class Meta:
        model = Cita
        fields = ["id", "clienta", "clienta_nombre", "servicio", "servicio_nombre", "profesional", "cabina",
                  "hora_inicio", "hora_fin", "estado", "origen", "recordatorios"]
        read_only_fields = ["hora_fin", "estado", "origen"]

    def create(self, validated_data):
        validated_data.pop("centro", None)  # lo inyecta TenantMixin; el servicio usa el del usuario
        return services.crear_cita(centro=self.context["request"].user.centro, **validated_data)

    def update(self, instance, validated_data):
        raise serializers.ValidationError(_("Para reprogramar, cancela la cita y crea una nueva."))
