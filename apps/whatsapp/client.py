"""Cliente mínimo de WhatsApp Cloud API. Con WHATSAPP_ENABLED=False solo registra en el log."""
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def solo_digitos(telefono):
    return "".join(c for c in telefono if c.isdigit())


def _post(payload):
    if not settings.WHATSAPP_ENABLED:
        log.info("[WhatsApp DEV] %s", payload)
        return "dev-message-id"
    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    resp = requests.post(url, json=payload, headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}, timeout=10)
    resp.raise_for_status()
    return resp.json()["messages"][0]["id"]


def send_template(to, template, body_params, button_payloads=(), idioma="es"):
    """Plantilla aprobada por Meta (una versión por idioma: 'es' y 'en'), con parámetros y botones de respuesta rápida."""
    components = [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in body_params]}]
    for i, payload in enumerate(button_payloads):
        components.append({"type": "button", "sub_type": "quick_reply", "index": str(i),
                           "parameters": [{"type": "payload", "payload": payload}]})
    return _post({
        "messaging_product": "whatsapp", "to": solo_digitos(to), "type": "template",
        "template": {"name": template, "language": {"code": idioma}, "components": components},
    })


def send_text(to, text):
    """Solo funciona dentro de la ventana de 24 h desde el último mensaje de la clienta."""
    return _post({"messaging_product": "whatsapp", "to": solo_digitos(to), "type": "text", "text": {"body": text}})
