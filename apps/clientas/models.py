from django.db import models

from apps.core.models import Idioma, TenantModel


class Clienta(TenantModel):
    """Clienta de un centro de estética (tabla CLIENTA)."""

    nombre = models.CharField(max_length=120)
    telefono_whatsapp = models.CharField(max_length=20)
    idioma = models.CharField(
        max_length=2,
        choices=Idioma.choices,
        default=Idioma.ES,
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clienta"
        constraints = [
            models.UniqueConstraint(
                fields=["centro", "telefono_whatsapp"],
                name="clienta_tel_unico_por_centro",
            )
        ]

    def __str__(self):
        return self.nombre


class FichaEstetica(models.Model):
    """Ficha estética 1:1 de una clienta."""

    clienta = models.OneToOneField(
        Clienta,
        on_delete=models.CASCADE,
        related_name="ficha_estetica",
    )
    tipo_cutis = models.CharField(max_length=80, blank=True)
    alergias = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ficha_estetica"

    def __str__(self):
        return f"Ficha estética de {self.clienta.nombre}"