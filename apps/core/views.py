from django.utils import translation
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from .models import PermisoRol, PermisoUsuario
from .rbac import MODULOS, ROLES, SOLO_LECTURA, MODULOS_DELEGABLES, detalle_permisos_usuario, es_protegida, es_superadmin, modulos_editables, puede_gestionar_usuario, matriz, menu_usuario, permisos_usuario, roles_editables
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
from .permissions import CentroPermission, IsAdminSaas, NegociosPermission, SoloRecepcionista, centro_actual
from .serializers import CentroNegocioSerializer, CentroSerializer, IdiomaSerializer, LoginSerializer, MeSerializer, UsuarioSerializer


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
    """ADMIN_SAAS gestiona todos los negocios. Los demás roles, si la matriz les da "Negocios",
    solo ven / editan los datos básicos de su propio negocio."""

    queryset = Centro.objects.all().order_by("id")
    serializer_class = CentroSerializer
    permission_classes = [NegociosPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, "swagger_fake_view", False) or es_superadmin(self.request.user):
            return qs
        return qs.filter(pk=self.request.user.centro_id)

    def get_serializer_class(self):
        if self.action == "crear_usuario":
            return UsuarioSerializer
        return CentroSerializer if es_superadmin(self.request.user) else CentroNegocioSerializer

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

    @action(detail=True, methods=["get", "put"], url_path="permisos")
    def permisos(self, request, pk=None):
        """Permisos personalizados de una persona. PUT {"permisos": {"citas": 2, "usuarios": null}};
        null vuelve a usar el permiso de su rol."""
        objetivo = self.get_object()
        editable = puede_gestionar_usuario(request.user, objetivo)
        if request.method == "PUT":
            if not editable:
                raise PermissionDenied(_("No puedes modificar los permisos de esta persona."))
            cambios = request.data.get("permisos")
            if not isinstance(cambios, dict):
                raise ValidationError({"permisos": "Formato inválido."})
            for modulo, nivel in cambios.items():
                if modulo not in MODULOS_DELEGABLES:
                    raise ValidationError({"permisos": f"Módulo no personalizable: {modulo}."})
                if nivel is not None and (type(nivel) is not int or nivel not in (0, 1, 2)):
                    raise ValidationError({"permisos": f"Nivel inválido en {modulo}."})
                if modulo in SOLO_LECTURA and nivel == 2:
                    raise ValidationError({"permisos": "Resumen es un módulo de solo lectura."})
            with transaction.atomic():
                for modulo, nivel in cambios.items():
                    if nivel is None:
                        PermisoUsuario.objects.filter(usuario=objetivo, modulo=modulo).delete()
                    else:
                        PermisoUsuario.objects.update_or_create(
                            usuario=objetivo, modulo=modulo, defaults={"nivel": nivel})
        return Response({"usuario": objetivo.pk, "rol": objetivo.rol, "editable": editable,
                         "modulos": detalle_permisos_usuario(objetivo)})


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
                         "editable": bool(editables), "roles_editables": editables,
                         "modulos_editables": list(modulos_editables(request.user)) if editables else []})

    def put(self, request):
        editables = self._editables(request)
        centro = self._centro(request)
        actual = matriz(centro.pk)
        filas = modulos_editables(request.user)
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
                if (rol not in editables or modulo not in filas) and nivel != actual[modulo][rol]:
                    raise PermissionDenied(_("No puedes modificar los permisos de ese rol."))
                if modulo in SOLO_LECTURA and nivel == 2:
                    raise ValidationError({"matriz": "Resumen es un módulo de solo lectura."})
        with transaction.atomic():
            for modulo, roles in payload.items():
                for rol, nivel in roles.items():
                    if rol in editables and modulo in filas and not es_protegida(modulo, rol):
                        PermisoRol.objects.update_or_create(
                            centro=centro, rol=rol, modulo=modulo, defaults={"nivel": nivel})
        return self.get(request)

    def delete(self, request):
        editables = self._editables(request)
        centro = self._centro(request)
        PermisoRol.objects.filter(centro=centro, rol__in=editables,
                                  modulo__in=modulos_editables(request.user)).delete()
        return self.get(request)


class SuperadminViewSet(viewsets.ModelViewSet):
    """Superadministradores del SaaS (solo ADMIN_SAAS). Crear: POST con los datos del usuario.
    Ascender a alguien existente: PATCH /api/usuarios/{id}/ con {"rol": "ADMIN_SAAS"}."""

    serializer_class = UsuarioSerializer
    permission_classes = [IsAdminSaas]
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return Usuario.objects.filter(rol=Usuario.Rol.ADMIN_SAAS).order_by("id")

    def create(self, request, *args, **kwargs):
        ser = UsuarioSerializer(data={**request.data, "rol": Usuario.Rol.ADMIN_SAAS}, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise PermissionDenied(_("No puedes eliminar tu propia cuenta de superadmin."))
        if Usuario.objects.filter(rol=Usuario.Rol.ADMIN_SAAS, is_active=True).count() <= 1:
            raise ValidationError({"detail": _("Debe quedar al menos un superadmin.")})
        instance.delete()
