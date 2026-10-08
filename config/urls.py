from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.views import CentroViewSet, LoginView, MeView, UsuarioViewSet


def health(request):
    """Para comprobar que el servidor está vivo (sirve luego para el monitoreo de uptime)."""
    return JsonResponse({"status": "ok", "servicio": "glowsync-api"})


router = DefaultRouter()
router.register("centros", CentroViewSet, basename="centro")
router.register("usuarios", UsuarioViewSet, basename="usuario")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/", include(router.urls)),
]