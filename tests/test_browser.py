"""Pruebas sin abrir Chrome: detección de formularios JSF y destino AJAX."""
import unittest

from app import JS_CONSULTA, Navegador


class Locator:
    def __init__(self, count):
        self.n = count

    def count(self):
        return self.n


class Frame:
    def __init__(self, url, form=True, boton=True, viewstate=True):
        self.url = url
        self.elementos = {
            'form[id="formValores"]': form,
            '[id="formValores:consultaa"]': boton,
            'input[name="javax.faces.ViewState"]': viewstate,
        }

    def is_detached(self):
        return False

    def locator(self, selector):
        return Locator(int(self.elementos.get(selector, False)))


class Page:
    def __init__(self, frames):
        self.frames = frames

    def is_closed(self):
        return False


class Context:
    def __init__(self, pages):
        self.pages = pages


class DeteccionSIGER(unittest.TestCase):
    def test_index_xhtml_con_formulario(self):
        frame = Frame('https://rpc.economia.gob.mx/siger2/xhtml/index.xhtml')
        self.assertTrue(Navegador.pagina_lista(frame))
        self.assertIs(Navegador(None, None).localizar([Context([Page([frame])])]), frame)

    def test_formulario_en_iframe(self):
        inicio = Frame('https://rpc.economia.gob.mx/siger2/xhtml/index.xhtml', form=False)
        consulta = Frame('https://rpc.economia.gob.mx/siger2/xhtml/consulta/consultaPublica/consultaPublica.xhtml')
        self.assertIs(Navegador(None, None).localizar([Context([Page([inicio, consulta])])]), consulta)

    def test_login_no_es_sesion_activa(self):
        frame = Frame('https://rpc.economia.gob.mx/siger2/xhtml/login/login2.xhtml', form=False)
        self.assertFalse(Navegador.pagina_lista(frame))
        self.assertIsNone(Navegador(None, None).localizar([Context([Page([frame])])]))

    def test_sin_viewstate_no_esta_listo(self):
        frame = Frame('https://rpc.economia.gob.mx/siger2/xhtml/index.xhtml', viewstate=False)
        self.assertFalse(Navegador.pagina_lista(frame))

    def test_ajax_se_envia_al_endpoint_correcto(self):
        self.assertIn("'/siger2/xhtml/consulta/consultaPublica/consultaPublica.xhtml'", JS_CONSULTA)
        self.assertIn('fetch(destino.toString()', JS_CONSULTA)
        self.assertNotIn('fetch(location.pathname', JS_CONSULTA)


if __name__ == '__main__':
    unittest.main()
