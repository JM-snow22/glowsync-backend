from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel


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