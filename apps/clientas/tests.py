from rest_framework.test import APITestCase

from apps.core.models import Usuario
from apps.core.tests import cliente, crear_centro, crear_usuario

from .models import Clienta, FichaEstetica


class ClientasFichaEsteticaTest(APITestCase):

    def setUp(self):
        self.A, self.B = (
            crear_centro("A"),
            crear_centro("B"),
        )

        self.recA = crear_usuario(
            "reca@x.co",
            Usuario.Rol.RECEPCIONISTA,
            self.A,
        )

        self.recB = crear_usuario(
            "recb@x.co",
            Usuario.Rol.RECEPCIONISTA,
            self.B,
        )

        self.estA = crear_usuario(
            "esta@x.co",
            Usuario.Rol.ESTETICISTA,
            self.A,
        )

    def test_crear_clienta_asigna_el_centro_automaticamente(self):

        c = cliente(self.recA)

        r = c.post(
            "/api/clientas/",
            {
                "nombre": "Laura",
                "telefono_whatsapp": "573001112233",
                "idioma": "es",
            },
            format="json",
        )

        self.assertEqual(
            r.status_code,
            201,
            r.content,
        )

        self.assertEqual(
            Clienta.objects.get(
                pk=r.data["id"]
            ).centro_id,
            self.A.id,
        )

    def test_cada_centro_ve_solo_sus_clientas(self):

        Clienta.objects.create(
            centro=self.B,
            nombre="Clienta B",
            telefono_whatsapp="573009998877",
            idioma="es",
        )

        r = cliente(
            self.recA
        ).get("/api/clientas/")

        self.assertEqual(
            r.data["count"],
            0,
        )

    def test_no_puede_leer_clienta_de_otro_centro(self):

        clienta_b = Clienta.objects.create(
            centro=self.B,
            nombre="Clienta B",
            telefono_whatsapp="573009998877",
            idioma="es",
        )

        c = cliente(self.recA)

        self.assertEqual(
            c.get(
                f"/api/clientas/{clienta_b.id}/"
            ).status_code,
            404,
        )

    def test_crear_ficha_estetica(self):

        clienta = Clienta.objects.create(
            centro=self.A,
            nombre="Laura",
            telefono_whatsapp="573001112233",
            idioma="es",
        )

        r = cliente(
            self.estA
        ).post(
            "/api/fichas-esteticas/",
            {
                "clienta": clienta.id,
                "tipo_cutis": "Mixto",
                "alergias": "Ninguna conocida",
                "observaciones": "Piel sensible en zona T",
            },
            format="json",
        )

        self.assertEqual(
            r.status_code,
            201,
            r.content,
        )

        self.assertEqual(
            FichaEstetica.objects.get(
                pk=r.data["id"]
            ).clienta_id,
            clienta.id,
        )

    def test_no_se_pueden_crear_dos_fichas(self):

        clienta = Clienta.objects.create(
            centro=self.A,
            nombre="Laura",
            telefono_whatsapp="573001112233",
            idioma="es",
        )

        FichaEstetica.objects.create(
            clienta=clienta,
            tipo_cutis="Seco",
        )

        r = cliente(
            self.estA
        ).post(
            "/api/fichas-esteticas/",
            {
                "clienta": clienta.id,
                "tipo_cutis": "Mixto",
            },
            format="json",
        )

        self.assertEqual(
            r.status_code,
            400,
        )

    def test_no_puede_usar_clienta_de_otro_centro(self):

        clienta_b = Clienta.objects.create(
            centro=self.B,
            nombre="Clienta B",
            telefono_whatsapp="573009998877",
            idioma="es",
        )

        r = cliente(
            self.estA
        ).post(
            "/api/fichas-esteticas/",
            {
                "clienta": clienta_b.id,
                "tipo_cutis": "Graso",
            },
            format="json",
        )

        self.assertEqual(
            r.status_code,
            400,
        )