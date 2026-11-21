"""SIGER Consultas: interfaz sencilla y navegador con sesión persistente."""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core import (Consulta, SIGER_URL, agrupar_pendientes, analizar_xml, aplicar_edicion,
                  exportar_excel, fecha_actual, importar_archivo, preparar, reconciliar_entradas)

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
    // SIGER muestra index.xhtml, pero las solicitudes AJAX van a consultaPublica.xhtml.
    // No usar location.pathname: apuntaría a index.xhtml.
    const destino = new URL('/siger2/xhtml/consulta/consultaPublica/consultaPublica.xhtml', location.origin);
    const respuesta = await fetch(destino.toString(), {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Faces-Request': 'partial/ajax', 'X-Requested-With': 'XMLHttpRequest',
                 'Accept': 'application/xml, text/xml, */*; q=0.01',
                 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
      body: datos.toString(), signal: abortar.signal
    });
    return {codigo: respuesta.status, cuerpo: await respuesta.text()};
  } finally { clearTimeout(reloj); }
}"""


# Modo beta: dos iframes independientes, cada uno con ViewState propio.
# No se comparte un único formulario JSF entre peticiones paralelas.
JS_PARALELO = r"""async (criterios) => {
  if (criterios.length !== 2) return {disponible: false, razon: 'Se requieren dos consultas'};
  const d = document;
  const marcoInicial = d.querySelector('form[id="formValores"]');
  const original = d.querySelector('input[name="javax.faces.ViewState"]')?.value;
  if (!marcoInicial || !original) {
    return {disponible: false, razon: 'El formulario principal ya no está disponible'};
  }
  const crear = async (i) => {
    let f = d.getElementById('__siger_consultas_worker_' + i);
    if (f && f.contentDocument?.querySelector('form[id="formValores"]')) return f;
    if (f) f.remove();
    f = d.createElement('iframe');
    f.id = '__siger_consultas_worker_' + i;
    f.setAttribute('aria-hidden', 'true');
    f.style.cssText = 'position:absolute;left:-10000px;top:0;width:1px;height:1px;border:0';
    d.body.appendChild(f);
    await new Promise((resolve, reject) => {
      const reloj = setTimeout(() => reject(new Error('La vista adicional no cargó')), 15000);
      f.onload = () => { clearTimeout(reloj); resolve(); };
      f.onerror = () => { clearTimeout(reloj); reject(new Error('Fallo al abrir vista adicional')); };
      f.src = location.href;
    });
    return f;
  };
  try {
    const marcos = [await crear(0), await crear(1)];
    const estados = marcos.map(f => {
      const doc = f.contentDocument;
      if (!doc || !doc.getElementById('formValores') ||
          !doc.getElementById('formValores:consultaa'))
        throw new Error('SIGER no habilita Consulta pública en vistas adicionales');
      return doc.querySelector('input[name="javax.faces.ViewState"]')?.value;
    });
    if (estados.some(v => !v) || estados[0] === estados[1] ||
        estados.includes(original))
      throw new Error('Las vistas no tienen ViewState independientes');
    const destino = new URL('/siger2/xhtml/consulta/consultaPublica/consultaPublica.xhtml', location.origin);
    const enviar = async (frame, criterio) => {
      const doc = frame.contentDocument;
      const estado = doc.querySelector('input[name="javax.faces.ViewState"]');
      if (!estado || !estado.value) throw new Error('ViewState no disponible');
      const datos = new URLSearchParams({
        'javax.faces.partial.ajax': 'true',
        'javax.faces.source': 'formValores:consultaa',
        'javax.faces.partial.execute': '@all',
        'javax.faces.partial.render': 'formValores:dataTableCaratula formValores:panelBotones',
        'formValores:consultaa': 'formValores:consultaa',
        'formValores': 'formValores',
        'formValores:fme': '',
        'formValores:rsocial': criterio.razon,
        'formValores:clvOficina': '',
        'formValores:clvEstado': '',
        'formValores:nombre': criterio.nombre,
        'formValores:apellido_paterno': criterio.paterno,
        'formValores:apellido_materno': criterio.materno,
        'formValores:dataTableCaratula_selection': '',
        'javax.faces.ViewState': estado.value
      });
      const controller = new AbortController();
      const reloj = setTimeout(() => controller.abort(), 120000);
      try {
        const r = await frame.contentWindow.fetch(destino.toString(), {
          method: 'POST', credentials: 'same-origin',
          headers: {'Faces-Request': 'partial/ajax', 'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/xml, text/xml, */*; q=0.01',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
          body: datos.toString(), signal: controller.signal
        });
        const cuerpo = await r.text();
        const xml = new DOMParser().parseFromString(cuerpo, 'text/xml');
        const actualizado = [...xml.getElementsByTagName('update')]
          .find(n => n.getAttribute('id') === 'javax.faces.ViewState');
        if (actualizado?.textContent) estado.value = actualizado.textContent;
        return {codigo: r.status, cuerpo};
      } finally { clearTimeout(reloj); }
    };
    const resultados = await Promise.allSettled(marcos.map((f,i) => enviar(f,criterios[i])));
    return {disponible: true, resultados: resultados.map(r =>
      r.status === 'fulfilled' ? r.value : {codigo: 0, cuerpo: '', error: String(r.reason)})};
  } catch (err) {
    return {disponible: false, razon: String(err.message || err)};
  }
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
    def pagina_lista(frame) -> bool:
        """Detectar el formulario JSF real, independientemente de la URL visible.

        La página puede mostrarse en index.xhtml e incluir el formulario en un frame.
        La primera respuesta válida confirma si la sesión sigue autenticada.
        """
        try:
            if frame.is_detached():
                return False
            return (frame.locator('form[id="formValores"]').count() > 0 and
                    frame.locator('[id="formValores:consultaa"]').count() > 0 and
                    frame.locator('input[name="javax.faces.ViewState"]').count() > 0)
        except Exception:
            return False

    def localizar(self, contextos):
        """Buscar Consulta pública entre las pestañas y frames de Chrome/Edge."""
        for ctx in contextos:
            for pagina in reversed(ctx.pages):
                try:
                    if pagina.is_closed():
                        continue
                    for frame in reversed(pagina.frames):
                        if self.pagina_lista(frame):
                            return frame
                except Exception:
                    continue
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
                            if estado == 'ACTIVA':
                                self.enviar('log', texto='Formulario de Consulta pública detectado. Ya puedes consultar.')
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
                    elif accion in ('consultar', 'consultar_paralelo'):
                        self.cancelar.clear()
                        contextos = browser.contexts if browser and browser.is_connected() else ([contexto] if contexto else [])
                        pagina = self.localizar(contextos)
                        if not pagina:
                            self.enviar('error', texto='No se detectó el formulario de SIGER. Entra a Consulta pública.')
                            self.enviar('fin')
                            continue
                        self.enviar('estado', valor='CONSULTANDO')
                        grupos = agrupar_pendientes(datos)
                        self.enviar('log', texto=f'{len(datos)} entradas, {len(grupos)} consultas distintas.')
                        paralelo = accion == 'consultar_paralelo'
                        fallos_sesion = False

                        def informar(grupo, cantidad=None, error=None):
                            for indice, reg in grupo:
                                if error:
                                    self.enviar('fila', indice=indice, estado='ERROR',
                                                cantidad=None, mensaje=error[:180])
                                else:
                                    self.enviar('fila', indice=indice,
                                                estado='ENCONTRADO' if cantidad else 'SIN RESULTADOS',
                                                cantidad=cantidad,
                                                mensaje='Coincidencia preliminar; verificar identidad')

                        posicion = 0
                        while posicion < len(grupos) and not self.cancelar.is_set():
                            lote = grupos[posicion:posicion + (2 if paralelo else 1)]
                            posicion += len(lote)
                            if paralelo and len(lote) == 2:
                                for grupo in lote:
                                    for indice, _ in grupo:
                                        self.enviar('trabajando', indice=indice)
                                try:
                                    respuesta = pagina.evaluate(JS_PARALELO,
                                        [grupo[0][1].criterios() for grupo in lote])
                                    if respuesta.get('disponible') and len(respuesta.get('resultados', [])) == 2:
                                        for grupo, resultado in zip(lote, respuesta['resultados']):
                                            try:
                                                if resultado.get('codigo') != 200:
                                                    raise ValueError(resultado.get('error') or
                                                        f'HTTP {resultado.get("codigo")}')
                                                cantidad, _ = analizar_xml(resultado['cuerpo'])
                                                informar(grupo, cantidad=cantidad)
                                            except Exception as exc:
                                                informar(grupo, error=str(exc))
                                        continue
                                    paralelo = False
                                    self.enviar('log', texto='No se pudieron abrir vistas independientes. '
                                                'Continuando 1 a 1: ' + respuesta.get('razon', 'sin detalles'))
                                except Exception as exc:
                                    paralelo = False
                                    self.enviar('log', texto='Modo paralelo no disponible; continuando 1 a 1: ' +
                                                str(exc)[:100])
                            for grupo in lote:
                                if self.cancelar.is_set():
                                    break
                                if not self.pagina_lista(pagina):
                                    informar(grupo, error='Sesión o formulario no disponible')
                                    fallos_sesion = True
                                    break
                                for indice, _ in grupo:
                                    self.enviar('trabajando', indice=indice)
                                try:
                                    cantidad = self.consultar(pagina, grupo[0][1])
                                    informar(grupo, cantidad=cantidad)
                                except Exception as exc:
                                    informar(grupo, error=str(exc))
                                    if any(t in str(exc).lower() for t in
                                           ('sesión', 'formulario', 'xml', 'viewstate', 'http')):
                                        fallos_sesion = True
                                        break
                                # Modo normal: pausa responsable; modo beta con fallback: un poco menor.
                                pausa = 0.6 if accion == 'consultar_paralelo' else 2.0
                                for _ in range(int(pausa / 0.2)):
                                    if self.cancelar.is_set():
                                        break
                                    time.sleep(0.2)
                            if fallos_sesion:
                                break
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
        self.editor = None
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
        ttk.Label(caja, text='Vista previa · doble clic en cualquier nombre o apellido para editar la celda').pack(anchor='w', pady=(11, 5))
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
        self.boton_paralelo = ttk.Button(
            acciones, text='Consultar 2 a la vez (beta)',
            command=lambda: self._consultar(modo='consultar_paralelo'))
        self.boton_paralelo.pack(side='left', padx=(8, 0))
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
        self.registros = reconciliar_entradas(self.registros, registros)
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

    def _editar(self, event):
        """Edición en la propia celda: Enter confirma, Escape cancela."""
        if self.ejecutando or self.editor:
            return
        if self.tabla.identify_region(event.x, event.y) != 'cell':
            return
        item = self.tabla.identify_row(event.y)
        columna = self.tabla.identify_column(event.x)
        if not item:
            return
        mapa = {'#1': 'original', '#2': 'nombre', '#3': 'paterno', '#4': 'materno'}
        campo = mapa.get(columna)
        if not campo:
            return
        reg = self.registros[int(item)]
        if reg.tipo == 'EMPRESA' and campo != 'original':
            return
        self.tabla.selection_set(item)
        caja = self.tabla.bbox(item, columna)
        if not caja:
            return
        x, y, ancho, alto = caja
        editor = ttk.Entry(self.tabla, font=('Segoe UI', 10))
        editor.insert(0, getattr(reg, campo))
        editor.place(x=x, y=y, width=ancho, height=alto)
        self.editor = editor
        finalizado = False

        def terminar(guardar):
            nonlocal finalizado
            if finalizado:
                return
            finalizado = True
            texto = editor.get()
            editor.destroy()
            self.editor = None
            if guardar:
                try:
                    aplicar_edicion(reg, campo, texto)
                except ValueError as exc:
                    messagebox.showwarning('Edición', str(exc), parent=self)
                self._mostrar_fila(int(item))

        editor.bind('<Return>', lambda e: terminar(True))
        editor.bind('<Escape>', lambda e: terminar(False))
        editor.bind('<FocusOut>', lambda e: terminar(True))
        editor.focus_set()
        editor.selection_range(0, 'end')

    def _importar(self):
        ruta = filedialog.askopenfilename(filetypes=[('Listas', '*.xlsx *.csv *.txt')])
        if ruta:
            try:
                entradas = importar_archivo(ruta)
                self.entrada.insert('end', ('\n' if self.entrada.get('1.0','end').strip() else '') + '\n'.join(entradas))
                self._preparar_vista()
            except Exception as exc:
                messagebox.showerror('Importación', str(exc))

    def _consultar(self, modo='consultar'):
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
        self.boton_paralelo.state(['disabled'])
        self.boton_detener.state(['!disabled'])
        self.comandos.put((modo, pendientes))

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
                    self.etiqueta.configure(text='CONECTADA' if valor in ('ACTIVA', 'CONSULTANDO') else valor)
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
                    self.boton_paralelo.state(['!disabled'])
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
