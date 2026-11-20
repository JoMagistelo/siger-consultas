import unittest
from core import preparar, separar_nombre, analizar_xml


def xml(total):
    return ("<partial-response><changes>"
            "<update id='formValores:dataTableCaratula'><![CDATA["
            f"<script>rowCount:{total},page:0</script>"
            "]]></update><update id='javax.faces.ViewState'><![CDATA[nuevo]]></update>"
            "</changes></partial-response>")


class Logica(unittest.TestCase):
    def test_tres(self):
        self.assertEqual(separar_nombre('JOSE CRUZ GOMEZ'), ('JOSE', 'CRUZ', 'GOMEZ'))

    def test_cuatro(self):
        self.assertEqual(separar_nombre('JOSE LUIS CRUZ GOMEZ'), ('JOSE LUIS', 'CRUZ', 'GOMEZ'))

    def test_cinco(self):
        self.assertEqual(separar_nombre('MARIA JOSE ANTONIO CRUZ GOMEZ'),
                         ('MARIA JOSE ANTONIO', 'CRUZ', 'GOMEZ'))

    def test_compuesto_manual(self):
        self.assertEqual(preparar('MARIA JOSE | DE LA CRUZ | GOMEZ', 'PERSONA').paterno, 'DE LA CRUZ')

    def test_empresa(self):
        self.assertEqual(preparar('BIMBO', 'EMPRESA').razon, 'BIMBO')

    def test_cuenta(self):
        self.assertEqual(analizar_xml(xml(56)), (56, 'nuevo'))
        self.assertEqual(analizar_xml(xml(0))[0], 0)

    def test_login_es_error(self):
        with self.assertRaises(ValueError):
            analizar_xml('<html>login</html>')


if __name__ == '__main__':
    unittest.main()
