from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Func, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel


class TsTzRange(Func):
    """Rango de tiempo (inicio, fin) para las restricciones anti-solapamiento de PostgreSQL."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Cabina(TenantModel):
    """Sala física donde se atiende. Una cabina no puede tener dos citas a la vez."""

    nombre = models.CharField(max_length=80)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "cabina"
        constraints = [models.UniqueConstraint(fields=["centro", "nombre"], name="cabina_nombre_unico")]

    def __str__(self):
        return self.nombre


class Servicio(TenantModel):
    nombre = models.CharField(max_length=120)
    duracion_minutos = models.PositiveSmallIntegerField(validators=[MinValueValidator(5)])
    precio = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    porcentaje_sena = models.PositiveSmallIntegerField(
        default=30, validators=[MaxValueValidator(100)], help_text=_("% del precio cobrado como seña")
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "servicio"

    def __str__(self):
        return self.nombre


class Profesional(TenantModel):
    usuario = models.OneToOneField(
        "core.Usuario", null=True, blank=True, on_delete=models.SET_NULL, related_name="perfil_profesional"
    )
    nombre = models.CharField(max_length=120)
    telefono = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "profesional"

    def __str__(self):
        return self.nombre


class DisponibilidadProfesional(models.Model):
    """Turno semanal de un profesional. dia_semana: 0 = lunes ... 6 = domingo."""

    profesional = models.ForeignKey(Profesional, on_delete=models.CASCADE, related_name="disponibilidades")
    dia_semana = models.PositiveSmallIntegerField()
    hora_desde = models.TimeField()
    hora_hasta = models.TimeField()

    class Meta:
        db_table = "disponibilidad_profesional"
        constraints = [
            models.CheckConstraint(name="disp_dia_valido", condition=Q(dia_semana__lte=6)),
            models.CheckConstraint(name="disp_horas_validas", condition=Q(hora_hasta__gt=models.F("hora_desde"))),
        ]


class BloqueoAgenda(TenantModel):
    """Festivos, vacaciones, mantenimiento. Sin profesional = bloquea a todo el centro."""

    profesional = models.ForeignKey(
        Profesional, null=True, blank=True, on_delete=models.CASCADE, related_name="bloqueos"
    )
    inicio = models.DateTimeField()
    fin = models.DateTimeField()
    motivo = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "bloqueo_agenda"
        constraints = [models.CheckConstraint(name="bloqueo_rango_valido", condition=Q(fin__gt=models.F("inicio")))]


class Cita(TenantModel):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", _("Pendiente")
        CONFIRMADA = "CONFIRMADA", _("Confirmada")
        CANCELADA = "CANCELADA", _("Cancelada")
        COMPLETADA = "COMPLETADA", _("Completada")
        NO_ASISTIO = "NO_ASISTIO", _("No asistió")

    class Origen(models.TextChoices):
        NORMAL = "NORMAL", _("Normal")
        REASIGNACION = "REASIGNACION", _("Reasignación exprés")

    clienta = models.ForeignKey("clientas.Clienta", on_delete=models.PROTECT, related_name="citas")
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name="citas")
    profesional = models.ForeignKey(Profesional, on_delete=models.PROTECT, related_name="citas")
    cabina = models.ForeignKey(Cabina, on_delete=models.PROTECT, related_name="citas")
    hora_inicio = models.DateTimeField()
    hora_fin = models.DateTimeField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    origen = models.CharField(max_length=12, choices=Origen.choices, default=Origen.NORMAL)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cita"
        ordering = ["hora_inicio"]
        indexes = [
            models.Index(fields=["centro", "hora_inicio"]),
            models.Index(fields=["cabina", "hora_inicio"]),
            models.Index(fields=["profesional", "hora_inicio"]),
        ]
        constraints = [
            models.CheckConstraint(name="cita_rango_valido", condition=Q(hora_fin__gt=models.F("hora_inicio"))),
            # Garantía a nivel de BD: una cabina o un profesional no pueden tener dos citas activas que se crucen.
            ExclusionConstraint(
                name="sin_cruce_cabina",
                expressions=[
                    (TsTzRange("hora_inicio", "hora_fin", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("cabina", RangeOperators.EQUAL),
                ],
                condition=Q(estado__in=["PENDIENTE", "CONFIRMADA"]),
            ),
            ExclusionConstraint(
                name="sin_cruce_profesional",
                expressions=[
                    (TsTzRange("hora_inicio", "hora_fin", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("profesional", RangeOperators.EQUAL),
                ],
                condition=Q(estado__in=["PENDIENTE", "CONFIRMADA"]),
            ),
        ]


class Recordatorio(models.Model):
    class Tipo(models.TextChoices):
        H48 = "H48", _("48 horas antes")
        H24 = "H24", _("24 horas antes")

    class Respuesta(models.TextChoices):
        SIN_RESPUESTA = "SIN_RESPUESTA", _("Sin respuesta")
        CONFIRMA = "CONFIRMA", _("Confirma")
        CANCELA = "CANCELA", _("Cancela")

    cita = models.ForeignKey(Cita, on_delete=models.CASCADE, related_name="recordatorios")
    tipo = models.CharField(max_length=3, choices=Tipo.choices)
    programado_para = models.DateTimeField()
    enviado_en = models.DateTimeField(null=True, blank=True)
    respuesta = models.CharField(max_length=14, choices=Respuesta.choices, default=Respuesta.SIN_RESPUESTA)
    wa_message_id = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "recordatorio"
        constraints = [models.UniqueConstraint(fields=["cita", "tipo"], name="recordatorio_unico_por_tipo")]
