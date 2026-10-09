from celery import shared_task

from . import services


@shared_task
def iniciar_reasignacion(cita_id):
    oferta = services.iniciar_oferta(cita_id)
    return oferta.id if oferta else None


@shared_task
def expirar_oferta(oferta_id):
    return services.vencer_oferta(oferta_id)
