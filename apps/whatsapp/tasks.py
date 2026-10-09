import logging

from celery import shared_task

from .handlers import procesar_boton

log = logging.getLogger(__name__)


@shared_task
def procesar_eventos_whatsapp(payload):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                origen = msg.get("from", "")
                boton = None
                if msg.get("type") == "button":
                    boton = msg["button"].get("payload")
                elif msg.get("type") == "interactive":
                    boton = msg["interactive"].get("button_reply", {}).get("id")
                if boton:
                    procesar_boton(origen, boton)
