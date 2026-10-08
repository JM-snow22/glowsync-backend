from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.core.serializers import TenantPKField

from .models import Clienta, FichaEstetica


class ClientaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clienta
        fields = [
            "id",
            "nombre",
            "telefono_whatsapp",
            "idioma",
            "creado_en",
        ]
        read_only_fields = ["creado_en"]

    def validate_telefono_whatsapp(self, value):
        digits = "".join(c for c in value if c.isdigit())
        if len(digits) < 10:
            raise serializers.ValidationError(
                _("Teléfono inválido (incluye el indicativo).")
            )
        qs = Clienta.objects.filter(
            centro=self.context["request"].user.centro,
            telefono_whatsapp=digits,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                _("Ya existe una clienta con este teléfono.")
            )
        return digits


class FichaEsteticaSerializer(serializers.ModelSerializer):
    clienta = TenantPKField(
        queryset=Clienta.objects.all()
    )

    class Meta:
        model = FichaEstetica
        fields = [
            "id",
            "clienta",
            "tipo_cutis",
            "alergias",
            "observaciones",
            "actualizada_en",
        ]
        read_only_fields = ["actualizada_en"]

    def validate_clienta(self, value):
        qs = FichaEstetica.objects.filter(clienta=value)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                _("La clienta ya tiene una ficha estética.")
            )

        return value