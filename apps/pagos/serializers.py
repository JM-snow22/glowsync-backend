from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers
from django.utils.translation import gettext as _
from apps.agenda.models import Cita
from apps.core.serializers import TenantPKField

from .models import Pago


class PagoSerializer(serializers.ModelSerializer):
    cita = TenantPKField(queryset=Cita.objects.all())

    class Meta:
        model = Pago
        fields = ["id", "cita", "tipo", "estado", "monto", "pasarela", "referencia", "creado_en"]
        read_only_fields = ["estado", "monto", "pasarela", "referencia", "creado_en"]

    def validate(self, attrs):
        cita, tipo = attrs["cita"], attrs["tipo"]
        if tipo == Pago.Tipo.REEMBOLSO:
            raise serializers.ValidationError(_("Los reembolsos los registra el sistema desde la pasarela."))
        if tipo == Pago.Tipo.SENA and cita.pagos.filter(
            tipo=Pago.Tipo.SENA, estado__in=[Pago.Estado.PENDIENTE, Pago.Estado.APROBADO]
        ).exists():
            raise serializers.ValidationError(_("Esta cita ya tiene una seña pendiente o aprobada."))
        return attrs

    def create(self, validated_data):
        import uuid

        cita, tipo = validated_data["cita"], validated_data["tipo"]
        precio = cita.servicio.precio
        pct = Decimal(cita.servicio.porcentaje_sena) / 100
        monto = (precio * pct if tipo == Pago.Tipo.SENA else precio * (1 - pct)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        return Pago.objects.create(
            centro=cita.centro, cita=cita, tipo=tipo, monto=monto, referencia=f"GS-{cita.id}-{uuid.uuid4().hex[:8]}"
        )
