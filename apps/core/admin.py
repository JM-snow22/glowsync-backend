from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Centro, Usuario


@admin.register(Centro)
class CentroAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ciudad", "plan", "estado_suscripcion", "fecha_vencimiento")
    list_filter = ("plan", "estado_suscripcion")


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("email", "nombre", "rol", "centro", "is_active")
    list_filter = ("rol", "is_active")
    ordering = ("email",)
    search_fields = ("email", "nombre")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos", {"fields": ("nombre", "rol", "centro", "idioma")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "nombre", "rol", "centro", "password1", "password2")}),
    )