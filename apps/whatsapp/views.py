import hashlib
import hmac
import json

from django.conf import settings
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .tasks import procesar_eventos_whatsapp


class WhatsAppWebhook(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """Verificación inicial que hace Meta al registrar el webhook."""
        if (request.GET.get("hub.mode") == "subscribe"
                and request.GET.get("hub.verify_token") == settings.WHATSAPP_VERIFY_TOKEN):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse(status=403)

    def post(self, request):
        raw = request.body  # leer el cuerpo crudo ANTES de tocar request.data
        esperado = "sha256=" + hmac.new(settings.WHATSAPP_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", ""), esperado):
            return HttpResponse(status=403)
        try:
            payload = json.loads(raw)
        except ValueError:
            return HttpResponse(status=400)
        procesar_eventos_whatsapp.delay(payload)  # responder 200 rápido; se procesa en la cola
        return Response({"ok": True})
