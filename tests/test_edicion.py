"""Pruebas de edición directa, conservación de cambios y deduplicación."""
import unittest
from core import preparar, aplicar_edicion, reconciliar_entradas, agrupar_pendientes
from app import JS_PARALELO


class PruebasEdicion(unittest.TestCase):
    def test_editar_apellido_actualiza_criterios(self):
        r = preparar("JOSE LUIS CRUZ GOMEZ", "PERSONA")
        r.estado, r.registros = "ENCONTRADO", 57
        aplicar_edicion(r, "paterno", "DE LA CRUZ")
        self.assertEqual(r.criterios(), dict(nombre="JOSE LUIS", paterno="DE LA CRUZ", materno="GOMEZ", razon=""))
        self.assertEqual((r.estado, r.registros), ("PENDIENTE", None))

    def test_editar_texto_completo_reparte_nombre(self):
        r = preparar("JOSE CRUZ GOMEZ", "PERSONA")
        aplicar_edicion(r, "original", "MARIA FERNANDA RUIZ GARCIA")
        self.assertEqual((r.nombre, r.paterno, r.materno), ("MARIA FERNANDA", "RUIZ", "GARCIA"))

    def test_edicion_empresa_actualiza_busqueda(self):
        r = preparar("BIMBO", "EMPRESA")
        aplicar_edicion(r, "original", "GRUPO BIMBO")
        self.assertEqual(r.criterios()["razon"], "GRUPO BIMBO")
        self.assertEqual(r.original, "GRUPO BIMBO")

    def test_edicion_se_conserva_al_actualizar_lista(self):
        r = preparar("JOSE CRUZ GOMEZ", "PERSONA")
        aplicar_edicion(r, "paterno", "DE LA CRUZ")
        nuevo = preparar("JOSE CRUZ GOMEZ", "PERSONA")
        lista = reconciliar_entradas([r], [nuevo])
        self.assertIs(lista[0], r)
        self.assertEqual(lista[0].paterno, "DE LA CRUZ")

    def test_razon_social_editada_se_conserva(self):
        r = preparar("BIMBO", "EMPRESA")
        aplicar_edicion(r, "original", "GRUPO BIMBO")
        nuevo = preparar("BIMBO", "EMPRESA")
        self.assertEqual(reconciliar_entradas([r], [nuevo])[0].razon, "GRUPO BIMBO")

    def test_duplicados_con_ediciones_independientes(self):
        a, b = preparar("JOSE CRUZ GOMEZ", "PERSONA"), preparar("JOSE CRUZ GOMEZ", "PERSONA")
        aplicar_edicion(b, "paterno", "RUIZ")
        nuevos = [preparar("JOSE CRUZ GOMEZ", "PERSONA") for _ in range(2)]
        actual = reconciliar_entradas([a,b], nuevos)
        self.assertEqual((actual[0].paterno, actual[1].paterno), ("CRUZ","RUIZ"))

    def test_consultas_identicas_se_agrupan(self):
        rs = [preparar("JOSE CRUZ GOMEZ", "PERSONA") for _ in range(6)]
        grupos = agrupar_pendientes(list(enumerate(rs)))
        self.assertEqual(len(grupos), 1)
        self.assertEqual(len(grupos[0]), 6)

    def test_no_agrupar_nombres_editados(self):
        a,b = preparar("JOSE CRUZ GOMEZ", "PERSONA"), preparar("JOSE CRUZ GOMEZ", "PERSONA")
        aplicar_edicion(b, "paterno", "RUIZ")
        self.assertEqual(len(agrupar_pendientes([(0,a),(1,b)])), 2)

    def test_paralelismo_usa_frames_y_vistas_independientes(self):
        self.assertIn("new Promise", JS_PARALELO)
        self.assertIn("estados[0] === estados[1]", JS_PARALELO)
        self.assertIn("Promise.allSettled", JS_PARALELO)
        self.assertNotIn("fetch(location.pathname", JS_PARALELO)

    def test_puede_borrar_nombre_y_conservar_los_apellidos(self):
        r = preparar("JOSE CRUZ GOMEZ", "PERSONA")
        r.estado, r.registros = "ENCONTRADO", 57
        aplicar_edicion(r, "nombre", "   ")
        self.assertEqual(r.criterios(), dict(nombre="", paterno="CRUZ", materno="GOMEZ", razon=""))
        self.assertEqual((r.estado, r.registros), ("PENDIENTE", None))

    def test_puede_borrar_cualquiera_de_los_apellidos(self):
        r = preparar("JOSE CRUZ GOMEZ", "PERSONA")
        aplicar_edicion(r, "paterno", "")
        aplicar_edicion(r, "materno", " ")
        self.assertEqual((r.nombre, r.paterno, r.materno), ("JOSE", "", ""))

    def test_se_conservan_ediciones_en_blanco(self):
        r = preparar("JOSE CRUZ GOMEZ", "PERSONA")
        aplicar_edicion(r, "materno", "")
        self.assertIs(reconciliar_entradas([r], [preparar("JOSE CRUZ GOMEZ", "PERSONA")])[0], r)
        self.assertEqual(r.criterios()["materno"], "")

    def test_no_acepta_buscar_con_todos_los_campos_en_blanco(self):
        r = preparar("JOSE CRUZ GOMEZ", "PERSONA")
        aplicar_edicion(r, "nombre", "")
        aplicar_edicion(r, "paterno", "")
        with self.assertRaisesRegex(ValueError, "al menos"):
            aplicar_edicion(r, "materno", "")
        self.assertEqual(r.materno, "GOMEZ")

    def test_permite_formato_separado_con_campos_vacios(self):
        r = preparar(" | CRUZ | ", "PERSONA")
        self.assertEqual(r.criterios(), dict(nombre="", paterno="CRUZ", materno="", razon=""))
        with self.assertRaises(ValueError):
            preparar(" | | ", "PERSONA")

    def test_no_permite_razon_social_vacia(self):
        r = preparar("BIMBO", "EMPRESA")
        with self.assertRaises(ValueError):
            aplicar_edicion(r, "original", "")
        self.assertEqual(r.razon, "BIMBO")


if __name__ == "__main__":
    unittest.main()
