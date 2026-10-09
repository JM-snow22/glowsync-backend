from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel


class ListaEspera(TenantModel):
    class Estado(models.TextChoices):
        ACTIVA = "ACTIVA", _("Activa")
        ATENDIDA = "ATENDIDA", _("Atendida")
        CANCELADA = "CANCELADA", _("Cancelada")

    clienta = models.ForeignKey("clientas.Clienta", on_delete=models.CASCADE, related_name="esperas")
    servicio = models.ForeignKey("agenda.Servicio", on_delete=models.CASCADE, related_name="esperas")
    fecha_deseada = models.DateField()
    hora_desde = models.TimeField()
    hora_hasta = models.TimeField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVA)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lista_espera"
        indexes = [models.Index(fields=["servicio", "fecha_deseada", "estado"])]
        ordering = ["creado_en"]


class OfertaReasignacion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", _("Pendiente")
        ACEPTADA = "ACEPTADA", _("Aceptada")
        RECHAZADA = "RECHAZADA", _("Rechazada")
        VENCIDA = "VENCIDA", _("Vencida")

    cita_liberada = models.ForeignKey("agenda.Cita", on_delete=models.CASCADE, related_name="ofertas")
    espera = models.ForeignKey(ListaEspera, on_delete=models.CASCADE, related_name="ofertas")
    orden = models.PositiveSmallIntegerField()
    enviada_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    respondida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "oferta_reasignacion"
        constraints = [models.UniqueConstraint(fields=["cita_liberada", "espera"], name="oferta_unica_por_espera")]
        ordering = ["cita_liberada", "orden"]
