from django.contrib import admin

from .models import Clienta, FichaEstetica


@admin.register(Clienta)
class ClientaAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "telefono_whatsapp",
        "idioma",
        "centro",
        "creado_en",
    )

    search_fields = (
        "nombre",
        "telefono_whatsapp",
    )

    list_filter = (
        "idioma",
        "centro",
    )


@admin.register(FichaEstetica)
class FichaEsteticaAdmin(admin.ModelAdmin):
    list_display = (
        "clienta",
        "tipo_cutis",
        "actualizada_en",
    )

    search_fields = (
        "clienta__nombre",
        "clienta__telefono_whatsapp",
        "tipo_cutis",
        "alergias",
    )

    list_filter = (
        "tipo_cutis",
    )