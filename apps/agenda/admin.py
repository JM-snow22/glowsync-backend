from django.contrib import admin

from .models import BloqueoAgenda, Cabina, DisponibilidadProfesional, Profesional, Servicio

admin.site.register(Cabina, list_display=("nombre", "centro", "activa"))
admin.site.register(Servicio, list_display=("nombre", "centro", "duracion_minutos", "precio", "activo"))
admin.site.register(Profesional, list_display=("nombre", "centro", "activo"))
admin.site.register(DisponibilidadProfesional, list_display=("profesional", "dia_semana", "hora_desde", "hora_hasta"))
admin.site.register(BloqueoAgenda, list_display=("centro", "profesional", "inicio", "fin", "motivo"))