import hashlib
import hmac
import json

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agenda import services as agenda
from apps.agenda.models import Cita
from apps.core.mixins import TenantMixin
from apps.core.permissions import CentroPermission

from .models import Pago
from .serializers import PagoSerializer


class PagoViewSet(TenantMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                  mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Crea el cobro pendiente. Aquí se integra el checkout de la pasarela (Wompi/ePayco/Bold)."""

    queryset = Pago.objects.select_related("cita")
    serializer_class = PagoSerializer
    permission_classes = [CentroPermission]
    filterset_fields = ["estado", "tipo", "cita"]


class PagoWebhook(APIView):
    """Webhook genérico: {"referencia": "...", "estado": "APROBADO"|"FALLIDO"}.
    Adáptalo al formato y firma reales de tu pasarela. Es idempotente."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.body
        esperado = hmac.new(settings.PAGOS_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not settings.PAGOS_WEBHOOK_SECRET or not hmac.compare_digest(request.headers.get("X-Signature", ""), esperado):
            return HttpResponse(status=403)
        try:
            datos = json.loads(raw)
            referencia, nuevo = datos["referencia"], datos["estado"]
        except (ValueError, KeyError):
            return HttpResponse(status=400)
        if nuevo not in (Pago.Estado.APROBADO, Pago.Estado.FALLIDO):
            return HttpResponse(status=400)

        with transaction.atomic():
            pago = Pago.objects.select_for_update().select_related("cita").filter(referencia=referencia).first()
            if not pago:
                return HttpResponse(status=404)
            if pago.estado != Pago.Estado.PENDIENTE:
                return Response({"duplicado": True})  # idempotencia: ya procesado
            pago.estado = nuevo
            pago.save(update_fields=["estado", "actualizado_en"])
            if nuevo == Pago.Estado.APROBADO and pago.tipo == Pago.Tipo.SENA and pago.cita.estado == Cita.Estado.PENDIENTE:
                agenda.cambiar_estado(pago.cita, Cita.Estado.CONFIRMADA)
        return Response({"ok": True})
