from django.contrib import admin

from .models import Pago

admin.site.register(Pago, list_display=("id", "cita", "tipo", "estado", "monto", "referencia"), list_filter=("tipo", "estado"))
