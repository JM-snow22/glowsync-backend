from django.utils import translation
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Centro, Idioma, Usuario
from .permissions import CentroPermission, IsAdminSaas, SoloRecepcionista, centro_actual
from .serializers import CentroSerializer, IdiomaSerializer, LoginSerializer, MeSerializer, UsuarioSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"  # máximo 20 intentos por minuto (settings)


class MeView(APIView):
    """Datos del usuario autenticado. PATCH {"idioma": "en"} cambia su idioma preferido."""

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        u = request.user
        return Response(
            {"id": u.id, "nombre": u.nombre, "email": u.email, "rol": u.rol, "idioma": u.idioma,
             "centro_id": u.centro_id, "centro": u.centro.nombre if u.centro_id else None}
        )

    @extend_schema(request=IdiomaSerializer, responses=MeSerializer)
    def patch(self, request):
        idioma = request.data.get("idioma")
        if idioma not in Idioma.values:
            raise ValidationError({"idioma": _("Idioma no soportado.")})
        request.user.idioma = idioma
        request.user.save(update_fields=["idioma"])
        translation.activate(idioma)
        return self.get(request)


class CentroViewSet(viewsets.ModelViewSet):
    """Gestión de los clientes del SaaS (solo ADMIN_SAAS)."""

    queryset = Centro.objects.all().order_by("id")
    serializer_class = CentroSerializer
    permission_classes = [IsAdminSaas]

    @action(detail=True, methods=["post"], url_path="usuarios", serializer_class=UsuarioSerializer)
    def crear_usuario(self, request, pk=None):
        """El admin SaaS crea un administrador o integrante para un negocio."""
        centro = self.get_object()
        ser = UsuarioSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save(centro=centro)
        return Response(ser.data, status=status.HTTP_201_CREATED)


class UsuarioViewSet(viewsets.ModelViewSet):
    """La administración opera únicamente sobre usuarios del negocio seleccionado."""

    queryset = Usuario.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [CentroPermission, SoloRecepcionista]
    filterset_fields = ["rol", "is_active"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Usuario.objects.none()
        return super().get_queryset().filter(centro_id=centro_actual(self.request).id)

    def perform_create(self, serializer):
        serializer.save(centro=centro_actual(self.request))

    def perform_update(self, serializer):
        if serializer.instance.rol == Usuario.Rol.ADMIN_NEGOCIO and self.request.user.rol != Usuario.Rol.ADMIN_SAAS:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo el administrador SaaS puede modificar administradores.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.rol == Usuario.Rol.ADMIN_NEGOCIO and self.request.user.rol != Usuario.Rol.ADMIN_SAAS:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo el administrador SaaS puede eliminar administradores.")
        instance.delete()