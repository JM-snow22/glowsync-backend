from rest_framework.exceptions import APIException
from django.utils.translation import gettext_lazy as _

class ConflictoAgenda(APIException):
    status_code = 409
    default_detail = _("Ese horario ya está ocupado (cabina o profesional).")
    default_code = "conflicto_agenda"
