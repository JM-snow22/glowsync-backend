from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.core.serializers import TenantPKField

from .models import BloqueoAgenda, Cabina, DisponibilidadProfesional, Profesional, Servicio


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
    