"""SIGER Consultas: interfaz sencilla y navegador con sesión persistente."""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from core import Consulta, SIGER_URL, analizar_xml, exportar_excel, fecha_actual, importar_archivo, preparar

# Se ejecuta dentro de la pestaña de SIGER: cookies del navegador, sin copiarlas a Python.
JS_CONSULTA = r"""async (criterios) => {
  const form = document.getElementById('formValores');
  if (!form) throw new Error('No se encuentra el formulario SIGER');
  const estado = form.querySelector('input[name="javax.faces.ViewState"]') ||
    document.querySelector('input[name="javax.faces.ViewState"]');
  if (!estado || !estado.value) throw new Error('No se encontró ViewState');
  const datos = new URLSearchParams({
    'javax.faces.partial.ajax': 'true',
    'javax.faces.source': 'formValores:consultaa',
    'javax.faces.partial.execute': '@all',
    'javax.faces.partial.render': 'formValores:dataTableCaratula formValores:panelBotones',
    'formValores:consultaa': 'formValores:consultaa',
    'formValores': 'formValores',
    'formValores:fme': '',
    'formValores:rsocial': criterios.razon,
    'formValores:clvOficina': '',
    'formValores:clvEstado': '',
    'formValores:nombre': criterios.nombre,
    'formValores:apellido_paterno': criterios.paterno,
    'formValores:apellido_materno': criterios.materno,
    'formValores:dataTableCaratula_selection': '',
    'javax.faces.ViewState': estado.value
  });
  const abortar = new AbortController();
  const reloj = setTimeout(() => abortar.abort(), 120000);
  try {
    const respuesta = await fetch(location.pathname, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Faces-Request': 'partial/ajax', 'X-Requested-With': 'XMLHttpRequest',
                 'Accept': 'application/xml, text/xml, */*; q=0.01',
                 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
      body: datos.toString(), signal: abortar.signal
    });
    return {codigo: respuesta.status, cuerpo: await respuesta.text()};
  } finally { clearTimeout(reloj); }
}"""


class Navegador(threading.Thread):
    """El navegador solo es manipulado desde este hilo de trabajo."""
    def __init__(self, avisos: queue.Queue, comandos: queue.Queue):
        super().__init__(daemon=True)
        self.avisos = avisos
        self.comandos = comandos
        self.cancelar = threading.Event()
        self.vivo = True

    def enviar(self, clase: str, **datos):
        self.avisos.put((clase, datos))

    @staticmethod
    def pagina_lista(page) -> bool:
        try:
            return (not page.is_closed() and 'consultaPublica.xhtml' in page.url and
                    page.locator('[id="formValores:consultaa"]').count() == 1 and
                    page.locator('input[name="javax.faces.ViewState"]').count() > 0)
        except Exception:
            return False

    def localizar(self, contextos):
        for ctx in contextos:
            for pagina in reversed(ctx.pages):
                if self.pagina_lista(pagina):
                    return pagina
        return None

    def iniciar(self, pw):
        # Chrome normal no permite adjuntarse si no fue iniciado con depuración remota.
        # Solo se inspecciona 127.0.0.1; no se expone el puerto por red.
        try:
            browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=2200)
            self.enviar('log', texto='Conectado a Chrome con depuración remota (puerto 9222).')
            return browser, None
        except Exception:
            pass
        local = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'SIGERConsultas' / 'ChromeProfile'
        local.mkdir(parents=True, exist_ok=True)
        fallos = []
        for canal in ('chrome', 'msedge', None):
            try:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=str(local), headless=False, channel=canal,
                    viewport={'width': 1300, 'height': 850}, locale='es-MX')
                self.enviar('log', texto='Perfil SIGER persistente abierto. El acceso se conserva entre ejecuciones cuando SIGER lo permite.')
                pagina = ctx.pages[-1] if ctx.pages else ctx.new_page()
                if 'rpc.economia.gob.mx' not in pagina.url:
                    try:
                        pagina.goto(SIGER_URL, wait_until='domcontentloaded', timeout=45000)
                    except Exception as exc:
                        self.enviar('log', texto=f'Abre SIGER manualmente si tarda en cargar: {str(exc)[:90]}')
                return None, ctx
            except Exception as exc:
                fallos.append(str(exc).splitlines()[0])
        raise RuntimeError('No se pudo abrir Chrome/Edge. Revisa la instalación de Playwright. ' + ' / '.join(fallos[-2:]))

    def consultar(self, pagina, reg: Consulta) -> int:
        if not self.pagina_lista(pagina):
            raise ValueError('Sesión o formulario no disponible')
        resultado = pagina.evaluate(JS_CONSULTA, reg.criterios())
        if resultado['codigo'] != 200:
            raise ValueError(f'SIGER respondió HTTP {resultado["codigo"]}')
        cantidad, estado = analizar_xml(resultado['cuerpo'])
        if estado:
            pagina.evaluate("v => document.querySelectorAll('input[name=\"javax.faces.ViewState\"]').forEach(e => e.value = v)", estado)
        return cantidad

    def run(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.enviar('error', texto='No se encuentra Playwright. Ejecuta INSTALAR.bat.')
            return
        browser = None
        contexto = None
        previo = None
        ultimo = 0.0
        try:
            with sync_playwright() as pw:
                while self.vivo:
                    if time.monotonic() - ultimo > 1.8:
                        contextos = browser.contexts if browser and browser.is_connected() else ([contexto] if contexto else [])
                        pagina = self.localizar(contextos)
                        estado = 'ACTIVA' if pagina else ('ESPERANDO' if (browser or contexto) else 'DESCONECTADA')
                        if estado != previo:
                            self.enviar('estado', valor=estado)
                            previo = estado
                        ultimo = time.monotonic()
                    try:
                        accion, datos = self.comandos.get(timeout=0.15)
                    except queue.Empty:
                        continue
                    if accion == 'salir':
                        self.vivo = False
                    elif accion == 'conectar':
                        if browser and browser.is_connected() or contexto:
                            self.enviar('log', texto='Navegador conectado. Entra en Consulta pública si aún no aparece la luz verde.')
                        else:
                            try:
                                browser, contexto = self.iniciar(pw)
                            except Exception as exc:
                                self.enviar('error', texto=str(exc))
                        ultimo = 0
                    elif accion == 'consultar':
                        self.cancelar.clear()
                        contextos = browser.contexts if browser and browser.is_connected() else ([contexto] if contexto else [])
                        pagina = self.localizar(contextos)
                        if not pagina:
                            self.enviar('error', texto='No se detectó el formulario activo de SIGER. Conecta Chrome y entra a Consulta pública.')
                            self.enviar('fin')
                            continue
                        self.enviar('estado', valor='CONSULTANDO')
                        for indice, reg in datos:
                            if self.cancelar.is_set():
                                break
                            if not self.pagina_lista(pagina):
                                self.enviar('fila', indice=indice, estado='ERROR', cantidad=None,
                                            mensaje='Sesión o formulario no disponible')
                                break
                            self.enviar('trabajando', indice=indice)
                            try:
                                cantidad = self.consultar(pagina, reg)
                                self.enviar('fila', indice=indice, estado='ENCONTRADO' if cantidad else 'SIN RESULTADOS',
                                            cantidad=cantidad, mensaje='Coincidencia preliminar; verificar identidad')
                            except Exception as exc:
                                self.enviar('fila', indice=indice, estado='ERROR', cantidad=None, mensaje=str(exc)[:180])
                                # No transformar fallos de sesión en resultados negativos.
                                if any(t in str(exc).lower() for t in ('sesión', 'formulario', 'xml', 'viewstate', 'http')):
                                    break
                            for _ in range(10):
                                if self.cancelar.is_set():
                                    break
                                time.sleep(.2)
                        self.enviar('fin')
                        ultimo = 0
        except Exception as exc:
            self.enviar('error', texto=f'Error del navegador: {exc}')
        finally:
            if contexto:
                try:
                    contexto.close()
                except Exception:
                    pass
            # Una conexión CDP a Chrome ajeno solo se desconecta; no cerrar pestañas del usuario.
            self.enviar('estado', valor='DESCONECTADA')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SIGER 2.0 | Consultas')
        self.geometry('1040x715')
        self.minsize(870, 590)
        self.configure(bg='#F4F7FB')
        self.avisos, self.comandos = queue.Queue(), queue.Queue()
        self.motor = Navegador(self.avisos, self.comandos)
        self.motor.start()
        self.registros: list[Consulta] = []
        self.ejecutando = False
        self._crear_ui()
        self.after(150, self._procesar_eventos)
        self.protocol('WM_DELETE_WINDOW', self._cerrar)

    def _crear_ui(self):
        estilo = ttk.Style()
        estilo.theme_use('clam')
        estilo.configure('TFrame', background='#F4F7FB')
        estilo.configure('TLabel', background='#F4F7FB', foreground='#263A51', font=('Segoe UI', 10))
        estilo.configure('TButton', font=('Segoe UI Semibold', 10), padding=8)
        estilo.configure('Treeview', rowheight=29, font=('Segoe UI', 9))
        estilo.configure('Treeview.Heading', font=('Segoe UI Semibold', 9))
        caja = ttk.Frame(self, padding=18)
        caja.pack(fill='both', expand=True)
        encabezado = ttk.Frame(caja)
        encabezado.pack(fill='x', pady=(0, 11))
        tk.Label(encabezado, text='SIGER 2.0', bg='#F4F7FB', fg='#193B60',
                 font=('Segoe UI Semibold', 22)).pack(side='left')
        estado_box = ttk.Frame(encabezado)
        estado_box.pack(side='right')
        self.luz = tk.Canvas(estado_box, width=25, height=25, bg='#F4F7FB', highlightthickness=0)
        self.luz.pack(side='left')
        self.bombilla = self.luz.create_oval(5, 5, 20, 20, fill='#A0A9B4', outline='')
        self.etiqueta = ttk.Label(estado_box, text='DESCONECTADA')
        self.etiqueta.pack(side='left', padx=(1, 12))
        ttk.Button(estado_box, text='Conectar Chrome', command=lambda: self.comandos.put(('conectar', None))).pack(side='right')

        barra = ttk.Frame(caja)
        barra.pack(fill='x', pady=(2, 7))
        ttk.Label(barra, text='Tipo de consulta:').pack(side='left')
        self.tipo = tk.StringVar(value='PERSONA')
        tipo_combo = ttk.Combobox(barra, textvariable=self.tipo, values=('PERSONA', 'EMPRESA'),
                                  state='readonly', width=12)
        tipo_combo.pack(side='left', padx=9)
        tipo_combo.bind('<<ComboboxSelected>>', self._preparar_vista)
        ttk.Label(barra, text='Pega un nombre o razón social por línea; se prepara automáticamente.').pack(side='left')
        ttk.Button(barra, text='Importar archivo', command=self._importar).pack(side='right')

        self.entrada = tk.Text(caja, height=7, bg='white', fg='#233449', relief='solid', bd=1,
                               font=('Segoe UI', 11), padx=10, pady=8, undo=True)
        self.entrada.pack(fill='x')
        self.entrada.bind('<KeyRelease>', self._agenda_vista)
        self.entrada.bind('<<Paste>>', lambda e: self.after(150, self._preparar_vista))
        ttk.Label(caja, text='Vista previa · doble clic en una fila para corregir apellidos compuestos').pack(anchor='w', pady=(11, 5))
        marco = ttk.Frame(caja)
        marco.pack(fill='both', expand=True)
        cols = ('original', 'nombre', 'paterno', 'materno', 'estado', 'registros')
        self.tabla = ttk.Treeview(marco, columns=cols, show='headings')
        for c, titulo, ancho in [
            ('original', 'Entrada / Razón social', 310), ('nombre', 'Nombre(s)', 180),
            ('paterno', 'Paterno', 125), ('materno', 'Materno', 125),
            ('estado', 'Resultado', 130), ('registros', 'Núm.', 65)]:
            self.tabla.heading(c, text=titulo)
            self.tabla.column(c, width=ancho, minwidth=50, stretch=c == 'original')
        self.tabla.tag_configure('OK', background='#E6F5EB')
        self.tabla.tag_configure('ERR', background='#FDEDED')
        self.tabla.tag_configure('RUN', background='#FFF1D3')
        self.tabla.pack(side='left', fill='both', expand=True)
        barra_scroll = ttk.Scrollbar(marco, command=self.tabla.yview)
        barra_scroll.pack(side='right', fill='y')
        self.tabla.configure(yscrollcommand=barra_scroll.set)
        self.tabla.bind('<Double-1>', self._editar)

        acciones = ttk.Frame(caja)
        acciones.pack(fill='x', pady=(11, 8))
        self.boton_consultar = ttk.Button(acciones, text='Consultar lista', command=self._consultar)
        self.boton_consultar.pack(side='left')
        ttk.Button(acciones, text='Exportar Excel', command=self._exportar).pack(side='left', padx=9)
        self.boton_detener = ttk.Button(acciones, text='Detener', command=self.motor.cancelar.set)
        self.boton_detener.pack(side='left')
        self.boton_detener.state(['disabled'])
        self.conteo = ttk.Label(acciones, text='0 consultas')
        self.conteo.pack(side='right')
        self.estado_texto = ttk.Label(caja, text='Inicia con Conectar Chrome. El CAPTCHA se resuelve manualmente.')
        self.estado_texto.pack(anchor='w')
        self._pendiente = None

    def _agenda_vista(self, _event=None):
        if self.ejecutando:
            return
        if self._pendiente:
            self.after_cancel(self._pendiente)
        self._pendiente = self.after(280, self._preparar_vista)

    def _preparar_vista(self, _event=None):
        if self.ejecutando:
            return
        self._pendiente = None
        entradas = [x.strip() for x in self.entrada.get('1.0', 'end').splitlines() if x.strip()]
        registros = []
        for texto in entradas:
            try:
                registros.append(preparar(texto, self.tipo.get()))
            except ValueError as exc:
                registros.append(Consulta(original=texto, tipo=self.tipo.get(),
                                         estado='REVISAR', observacion=str(exc)))
        self.registros = registros
        self._mostrar_todo()

    def _mostrar_todo(self):
        self.tabla.delete(*self.tabla.get_children())
        for i in range(len(self.registros)):
            self._mostrar_fila(i)
        self.conteo.configure(text=f'{len(self.registros)} consultas')

    def _mostrar_fila(self, i):
        r = self.registros[i]
        tag = 'OK' if r.estado == 'ENCONTRADO' else ('ERR' if r.estado in ('ERROR','REVISAR') else ('RUN' if r.estado == 'CONSULTANDO' else ''))
        vals = (r.original, r.nombre, r.paterno, r.materno, r.estado,
                '' if r.registros is None else r.registros)
        if self.tabla.exists(str(i)):
            self.tabla.item(str(i), values=vals, tags=(tag,))
        else:
            self.tabla.insert('', 'end', iid=str(i), values=vals, tags=(tag,))

    def _editar(self, _event):
        if self.ejecutando or self.tipo.get() != 'PERSONA':
            return
        seleccionado = self.tabla.selection()
        if not seleccionado:
            return
        i = int(seleccionado[0])
        r = self.registros[i]
        nombre = simpledialog.askstring('Corregir', 'Nombre(s):', initialvalue=r.nombre, parent=self)
        if nombre is None:
            return
        paterno = simpledialog.askstring('Corregir', 'Apellido paterno:', initialvalue=r.paterno, parent=self)
        if paterno is None:
            return
        materno = simpledialog.askstring('Corregir', 'Apellido materno:', initialvalue=r.materno, parent=self)
        if materno is None:
            return
        if not all(x.strip() for x in (nombre, paterno, materno)):
            messagebox.showwarning('Campos incompletos', 'Los tres campos son obligatorios')
            return
        r.nombre, r.paterno, r.materno = nombre.strip(), paterno.strip(), materno.strip()
        r.estado, r.observacion = 'PENDIENTE', ''
        self._mostrar_fila(i)

    def _importar(self):
        ruta = filedialog.askopenfilename(filetypes=[('Listas', '*.xlsx *.csv *.txt')])
        if ruta:
            try:
                entradas = importar_archivo(ruta)
                self.entrada.insert('end', ('\n' if self.entrada.get('1.0','end').strip() else '') + '\n'.join(entradas))
                self._preparar_vista()
            except Exception as exc:
                messagebox.showerror('Importación', str(exc))

    def _consultar(self):
        if self.ejecutando:
            return
        if not self.registros:
            self._preparar_vista()
        pendientes = [(i, r) for i, r in enumerate(self.registros)
                      if r.estado not in ('REVISAR', 'ENCONTRADO', 'SIN RESULTADOS')]
        if not pendientes:
            messagebox.showinfo('SIGER', 'No hay consultas pendientes válidas')
            return
        self.ejecutando = True
        self.boton_consultar.state(['disabled'])
        self.boton_detener.state(['!disabled'])
        self.comandos.put(('consultar', pendientes))

    def _exportar(self):
        if not self.registros:
            messagebox.showinfo('SIGER', 'No hay registros para exportar')
            return
        ruta = filedialog.asksaveasfilename(defaultextension='.xlsx', filetypes=[('Excel', '*.xlsx')],
                                             initialfile='resultados_siger.xlsx')
        if ruta:
            try:
                exportar_excel(self.registros, ruta)
                self.estado_texto.configure(text=f'Excel guardado: {ruta}')
            except Exception as exc:
                messagebox.showerror('Exportación', str(exc))

    def _procesar_eventos(self):
        try:
            while True:
                tipo, datos = self.avisos.get_nowait()
                if tipo == 'estado':
                    valor = datos['valor']
                    color = '#20A466' if valor in ('ACTIVA', 'CONSULTANDO') else ('#DB9A20' if valor == 'ESPERANDO' else '#A0A9B4')
                    self.luz.itemconfigure(self.bombilla, fill=color)
                    self.etiqueta.configure(text='CONECTADA' if valor == 'ACTIVA' else valor)
                elif tipo == 'log':
                    self.estado_texto.configure(text=datos['texto'])
                elif tipo == 'error':
                    self.estado_texto.configure(text=datos['texto'])
                    messagebox.showerror('SIGER', datos['texto'])
                elif tipo == 'trabajando':
                    r = self.registros[datos['indice']]
                    r.estado = 'CONSULTANDO'
                    self._mostrar_fila(datos['indice'])
                elif tipo == 'fila':
                    r = self.registros[datos['indice']]
                    r.estado, r.registros, r.observacion = datos['estado'], datos['cantidad'], datos['mensaje']
                    r.fecha = fecha_actual()
                    self._mostrar_fila(datos['indice'])
                    self.estado_texto.configure(text=f'{r.original}: {r.estado} ({r.registros if r.registros is not None else "—"})')
                elif tipo == 'fin':
                    self.ejecutando = False
                    self.boton_consultar.state(['!disabled'])
                    self.boton_detener.state(['disabled'])
        except queue.Empty:
            pass
        self.after(150, self._procesar_eventos)

    def _cerrar(self):
        self.motor.cancelar.set()
        self.comandos.put(('salir', None))
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
