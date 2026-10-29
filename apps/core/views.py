from django.utils import translation
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from .models import PermisoRol
from .rbac import MODULOS, ROLES, SOLO_LECTURA, es_protegida, es_superadmin, matriz, menu_usuario, permisos_usuario, roles_editables
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
        centro_id = u.centro_id
        if es_superadmin(u):
            raw = request.headers.get("X-Centro-ID")
            centro_id = int(raw) if raw and raw.isdigit() else None
        return Response(
            {"id": u.id, "nombre": u.nombre, "email": u.email, "rol": u.rol, "idioma": u.idioma,
             "centro_id": u.centro_id, "centro": u.centro.nombre if u.centro_id else None,
             "es_superadmin": es_superadmin(u),
             "permisos": permisos_usuario(u, centro_id),
             "menu": menu_usuario(u, centro_id)}
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


class PermisosRolView(APIView):
    """GET: matriz del negocio. PUT/DELETE: ADMIN_SAAS edita todo salvo filas protegidas;
    ADMIN_NEGOCIO solo las columnas de Recepcionista y Esteticista de su negocio."""

    permission_classes = [IsAuthenticated]

    def _centro(self, request):
        if es_superadmin(request.user):
            return centro_actual(request)
        if not request.user.centro_id or not request.user.centro.suscripcion_activa:
            raise PermissionDenied(_("No tienes un negocio activo asignado."))
        return request.user.centro

    def _editables(self, request):
        editables = roles_editables(request.user)
        if not editables:
            raise PermissionDenied(_("Tu rol no puede editar los permisos."))
        return editables

    def get(self, request):
        centro = self._centro(request)
        editables = roles_editables(request.user)
        return Response({"centro_id": centro.pk, "matriz": matriz(centro.pk),
                         "editable": bool(editables), "roles_editables": editables})

    def put(self, request):
        editables = self._editables(request)
        centro = self._centro(request)
        actual = matriz(centro.pk)
        payload = request.data.get("matriz")
        if not isinstance(payload, dict) or set(payload) != set(MODULOS):
            raise ValidationError({"matriz": "Debes enviar todos los módulos."})
        for modulo, roles in payload.items():
            if not isinstance(roles, dict) or set(roles) != set(ROLES):
                raise ValidationError({"matriz": f"Roles incompletos en {modulo}."})
            for rol, nivel in roles.items():
                if type(nivel) is not int or nivel not in (0, 1, 2):
                    raise ValidationError({"matriz": f"Nivel inválido en {modulo}/{rol}."})
                if es_protegida(modulo, rol) and nivel != actual[modulo][rol]:
                    raise ValidationError({"matriz": "Los permisos del administrador SaaS y Negocios son protegidos."})
                if rol not in editables and nivel != actual[modulo][rol]:
                    raise PermissionDenied(_("No puedes modificar los permisos de ese rol."))
                if modulo in SOLO_LECTURA and nivel == 2:
                    raise ValidationError({"matriz": "Resumen es un módulo de solo lectura."})
        with transaction.atomic():
            for modulo, roles in payload.items():
                for rol, nivel in roles.items():
                    if rol in editables and not es_protegida(modulo, rol):
                        PermisoRol.objects.update_or_create(
                            centro=centro, rol=rol, modulo=modulo, defaults={"nivel": nivel})
        return self.get(request)

    def delete(self, request):
        editables = self._editables(request)
        centro = self._centro(request)
        PermisoRol.objects.filter(centro=centro, rol__in=editables).delete()
        return self.get(request)
