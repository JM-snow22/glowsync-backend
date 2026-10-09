import logging

from celery import shared_task
from django.conf import settings
from django.utils import dateformat, timezone, translation

from apps.whatsapp import client

from .models import Cita, Recordatorio

log = logging.getLogger(__name__)


def formatear_fecha(dt):
    """Fecha corta en el idioma ACTIVO: 'lun 6 oct, 10:00 AM' (es) / 'Mon 6 Oct, 10:00 AM' (en)."""
    return dateformat.format(timezone.localtime(dt), "D j M, h:i A")


@shared_task
def enviar_recordatorio(recordatorio_id):
    """Idempotente: si ya se envió o la cita dejó de estar activa, no hace nada."""
    r = Recordatorio.objects.select_related("cita__clienta", "cita__servicio", "cita__centro").get(pk=recordatorio_id)
    cita = r.cita
    if r.enviado_en or cita.estado not in (Cita.Estado.PENDIENTE, Cita.Estado.CONFIRMADA):
        return "omitido"
    idioma = cita.clienta.idioma
    with translation.override(idioma):  # la fecha va en el idioma de la clienta
        fecha = formatear_fecha(cita.hora_inicio)
    msg_id = client.send_template(
        cita.clienta.telefono_whatsapp,
        settings.WHATSAPP_TEMPLATE_RECORDATORIO,
        [cita.clienta.nombre.split()[0], cita.servicio.nombre, fecha, cita.centro.nombre],
        [f"cita:{cita.id}:confirmar", f"cita:{cita.id}:cancelar"],
        idioma=idioma,
    )
    r.enviado_en = timezone.now()
    r.wa_message_id = msg_id
    r.save(update_fields=["enviado_en", "wa_message_id"])
    return "enviado"
