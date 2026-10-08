from django.utils import translation
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework_simplejwt.authentication import JWTAuthentication


class IdiomaJWTAuthentication(JWTAuthentication):
    """Prioridad del idioma de las respuestas:
    1) cabecera Accept-Language enviada por el cliente (el selector de idioma del frontend),
    2) idioma guardado en el perfil del usuario,
    3) idioma por defecto (es)."""

    def authenticate(self, request):
        resultado = super().authenticate(request)
        if resultado and "Accept-Language" not in request.headers:
            translation.activate(resultado[0].idioma)
            request.LANGUAGE_CODE = resultado[0].idioma
        return resultado


class IdiomaJWTScheme(OpenApiAuthenticationExtension):
    """Hace que /api/docs/ muestre el botón Authorize para pegar el token."""

    target_class = "apps.core.auth.IdiomaJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}