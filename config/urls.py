from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.agenda.views import (BloqueoViewSet, CabinaViewSet, CitaViewSet, DisponibilidadViewSet,ProfesionalViewSet, ServicioViewSet)
from apps.clientas.views import ClientaViewSet, FichaViewSet
from apps.core.views import CentroViewSet, LoginView, MeView, UsuarioViewSet
from apps.dashboard.views import ResumenView
from apps.pagos.views import PagoViewSet, PagoWebhook
from apps.reasignacion.views import ListaEsperaViewSet, OfertaViewSet
from apps.whatsapp.views import WhatsAppWebhook


def health(request):
    """Para comprobar que el servidor está vivo (sirve luego para el monitoreo de uptime)."""
    return JsonResponse({"status": "ok", "servicio": "glowsync-api"})


router = DefaultRouter()
router.register("centros", CentroViewSet, basename="centro")
router.register("usuarios", UsuarioViewSet, basename="usuario")
router.register("cabinas", CabinaViewSet, basename="cabina")
router.register("servicios", ServicioViewSet, basename="servicio")
router.register("profesionales", ProfesionalViewSet, basename="profesional")
router.register("disponibilidades", DisponibilidadViewSet, basename="disponibilidad")
router.register("bloqueos", BloqueoViewSet, basename="bloqueo")
router.register("clientas", ClientaViewSet, basename="clienta")
router.register("fichas", FichaViewSet, basename="ficha")
router.register("citas", CitaViewSet, basename="cita")
router.register("espera", ListaEsperaViewSet, basename="espera")
router.register("ofertas", OfertaViewSet, basename="oferta")
router.register("pagos", PagoViewSet, basename="pago")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/dashboard/resumen/", ResumenView.as_view(), name="dashboard-resumen"),
    path("api/webhooks/whatsapp/", WhatsAppWebhook.as_view(), name="webhook-whatsapp"),
    path("api/webhooks/pagos/", PagoWebhook.as_view(), name="webhook-pagos"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api-auth/", include("rest_framework.urls")),
    path("api/", include(router.urls)),
]
