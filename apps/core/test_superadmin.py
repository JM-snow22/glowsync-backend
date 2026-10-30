from rest_framework.test import APITestCase

from .models import Usuario
from .tests import cliente, crear_centro, crear_usuario

R = Usuario.Rol
CLAVE = "UnaClaveSegura123!"


class SuperadminTest(APITestCase):
    def setUp(self):
        self.a = crear_centro("A")
        self.saas = crear_usuario("saas@x.co", R.ADMIN_SAAS)
        self.jefe = crear_usuario("jefe@x.co", R.ADMIN_NEGOCIO, self.a)
        self.rec = crear_usuario("rec@x.co", R.RECEPCIONISTA, self.a)
        self.c = cliente(self.saas, HTTP_X_CENTRO_ID=str(self.a.pk))

    def test_superadmin_crea_otro_superadmin(self):
        r = self.c.post("/api/superadmins/", {"email": "nuevo@x.co", "nombre": "Nuevo", "password": CLAVE}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        u = Usuario.objects.get(email="nuevo@x.co")
        self.assertEqual((u.rol, u.centro_id), (R.ADMIN_SAAS, None))
        self.assertTrue(u.check_password(CLAVE))

    def test_superadmin_crea_superadmin_desde_usuarios(self):
        r = self.c.post("/api/usuarios/", {"email": "n2@x.co", "nombre": "N2", "rol": "ADMIN_SAAS", "password": CLAVE}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(Usuario.objects.get(email="n2@x.co").centro_id)

    def test_superadmin_asciende_a_cualquier_usuario(self):
        for u in (self.rec, self.jefe):
            r = self.c.patch(f"/api/usuarios/{u.pk}/", {"rol": "ADMIN_SAAS"}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
            u.refresh_from_db()
            self.assertEqual((u.rol, u.centro_id), (R.ADMIN_SAAS, None))
            self.assertIn("ADMIN_SAAS", set(u.roles.values_list("nombre", flat=True)))
        # el ascendido ya entra como superadmin
        me = cliente(self.rec).get("/api/auth/me/")
        self.assertTrue(me.data["es_superadmin"])

    def test_nadie_mas_puede_crear_ni_ascender_superadmins(self):
        for actor in (self.jefe, self.rec):
            c = cliente(actor)
            self.assertEqual(c.patch(f"/api/usuarios/{self.rec.pk}/", {"rol": "ADMIN_SAAS"}, format="json").status_code
                             in (400, 403), True)
            self.assertEqual(c.post("/api/superadmins/", {"email": "z@x.co", "nombre": "Z", "password": CLAVE}, format="json").status_code, 403)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.rol, R.RECEPCIONISTA)

    def test_listar_y_eliminar_con_protecciones(self):
        otro = crear_usuario("otro@x.co", R.ADMIN_SAAS)
        self.assertEqual(len(self.c.get("/api/superadmins/").data["results"] if isinstance(self.c.get("/api/superadmins/").data, dict) else self.c.get("/api/superadmins/").data), 2)
        self.assertEqual(self.c.delete(f"/api/superadmins/{self.saas.pk}/").status_code, 403)  # a sí mismo no
        self.assertEqual(self.c.delete(f"/api/superadmins/{otro.pk}/").status_code, 204)
        self.assertEqual(self.c.delete(f"/api/superadmins/{self.saas.pk}/").status_code, 403)
