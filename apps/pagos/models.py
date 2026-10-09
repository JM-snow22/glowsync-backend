from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel


class Pago(TenantModel):
    """Relación 1:N con CITA. Reintentos y reembolsos son registros NUEVOS; no se editan los anteriores."""

    class Tipo(models.TextChoices):
        SENA = "SENA", _("Seña")
        SALDO = "SALDO", _("Saldo")
        REEMBOLSO = "REEMBOLSO", _("Reembolso")

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", _("Pendiente")
        APROBADO = "APROBADO", _("Aprobado")
        FALLIDO = "FALLIDO", _("Fallido")
        REEMBOLSADO = "REEMBOLSADO", _("Reembolsado")

    cita = models.ForeignKey("agenda.Cita", on_delete=models.PROTECT, related_name="pagos")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    pasarela = models.CharField(max_length=30, blank=True)
    referencia = models.CharField(max_length=80, unique=True, null=True, blank=True, help_text=_("ID de la transacción en la pasarela"))
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pago"
        ordering = ["-creado_en"]
