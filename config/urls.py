from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def health(request):
    """Para comprobar que el servidor está vivo (sirve luego para el monitoreo de uptime)."""
    return JsonResponse({"status": "ok", "servicio": "glowsync-api"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
]
