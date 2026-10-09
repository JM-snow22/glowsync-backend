"""Interpreta los botones que llegan por WhatsApp. Formato del payload: tipo:id:accion"""
import logging

from django.utils import translation
from django.utils.translation import gettext, gettext_noop as _

from apps.agenda import services
from apps.agenda.models import Cita, Recordatorio
from apps.reasignacion import services as reasignacion

from . import client

log = logging.getLogger(__name__)


def _t(idioma, mensaje):
    """Traduce al idioma de la clienta (los mensajes de WhatsApp no dependen del idioma del servidor)."""
    with translation.override(idioma):
        return gettext(mensaje)


def _mismo_telefono(a, b):
    return client.solo_digitos(a)[-10:] == client.solo_digitos(b)[-10:]


def procesar_boton(telefono, payload):
    try:
        tipo, ident, accion = payload.split(":")
        ident = int(ident)
    except ValueError:
        log.warning("Payload de botón inválido: %s", payload)
        return
    if tipo == "cita":
        _responder_cita(telefono, ident, accion)
    elif tipo == "oferta":
        _responder_oferta(telefono, ident, accion)


def _responder_cita(telefono, cita_id, accion):
    cita = Cita.objects.select_related("clienta").filter(pk=cita_id).first()
    if not cita or not _mismo_telefono(cita.clienta.telefono_whatsapp, telefono):
        return  # ignora mensajes que no corresponden a la dueña de la cita
    idioma = cita.clienta.idioma
    ultimo = cita.recordatorios.filter(respuesta=Recordatorio.Respuesta.SIN_RESPUESTA, enviado_en__isnull=False).order_by("-enviado_en").first()
    try:
        if accion == "confirmar":
            if cita.estado == Cita.Estado.PENDIENTE:
                services.cambiar_estado(cita, Cita.Estado.CONFIRMADA)
            if ultimo:
                ultimo.respuesta = Recordatorio.Respuesta.CONFIRMA
            client.send_text(telefono, _t(idioma, _("¡Listo! Tu cita quedó confirmada ✅")))
        elif accion == "cancelar":
            services.cambiar_estado(cita, Cita.Estado.CANCELADA)
            if ultimo:
                ultimo.respuesta = Recordatorio.Respuesta.CANCELA
            client.send_text(telefono, _t(idioma, _("Tu cita fue cancelada. ¡Esperamos verte pronto!")))
    except Exception:  # noqa: BLE001 - estado inválido (ya cancelada, etc.)
        log.info("Acción %s ignorada para cita %s en estado %s", accion, cita_id, cita.estado)
    if ultimo:
        ultimo.save(update_fields=["respuesta"])


def _responder_oferta(telefono, oferta_id, accion):
    from apps.reasignacion.models import OfertaReasignacion

    oferta = OfertaReasignacion.objects.select_related("espera__clienta").filter(pk=oferta_id).first()
    if not oferta or not _mismo_telefono(oferta.espera.clienta.telefono_whatsapp, telefono):
        return
    resultado = reasignacion.responder_oferta(oferta_id, aceptar=(accion == "aceptar"))
    mensajes = {
        "aceptada": _("¡Cupo asignado! Tu cita quedó confirmada ✅"),
        "rechazada": _("Entendido, ofreceremos el cupo a otra persona."),
        "no_disponible": _("Lo sentimos, el cupo ya no está disponible."),
        "expirada": _("Esta oferta ya expiró."),
    }
    client.send_text(telefono, _t(oferta.espera.clienta.idioma, mensajes.get(resultado, _("Listo."))))
