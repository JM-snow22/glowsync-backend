from django.contrib import admin

from .models import ListaEspera, OfertaReasignacion

admin.site.register(ListaEspera, list_display=("clienta", "servicio", "fecha_deseada", "estado"))
admin.site.register(OfertaReasignacion, list_display=("cita_liberada", "espera", "orden", "estado", "expira_en"))
