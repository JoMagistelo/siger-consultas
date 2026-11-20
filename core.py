"""Preparación de consultas y lectura de las respuestas de SIGER 2.0."""
from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SIGER_URL = "https://rpc.economia.gob.mx/siger2/xhtml/consulta/consultaPublica/consultaPublica.xhtml"
TABLE_ID = "formValores:dataTableCaratula"


@dataclass
class Consulta:
    original: str
    tipo: str
    nombre: str = ""
    paterno: str = ""
    materno: str = ""
    razon: str = ""
    estado: str = "PENDIENTE"
    registros: int | None = None
    observacion: str = ""
    fecha: str = ""

    def criterios(self) -> dict[str, str]:
        return dict(nombre=self.nombre, paterno=self.paterno, materno=self.materno, razon=self.razon)

    def fila(self) -> list:
        return [self.tipo, self.original, self.nombre, self.paterno, self.materno,
                self.razon, self.estado, self.registros if self.registros is not None else "",
                self.observacion, self.fecha]


COLUMNAS = ["Tipo", "Entrada", "Nombre(s)", "Apellido paterno", "Apellido materno",
            "Razón social", "Resultado", "Registros", "Observación", "Fecha"]


def separar_nombre(texto: str) -> tuple[str, str, str]:
    """Regla solicitada: las dos últimas PALABRAS son apellidos; todas las anteriores nombres."""
    palabras = " ".join(texto.split()).split(" ")
    if len(palabras) < 3:
        raise ValueError("Se necesitan al menos 3 palabras: nombre, paterno y materno")
    return " ".join(palabras[:-2]), palabras[-2], palabras[-1]


def preparar(texto: str, tipo: str) -> Consulta:
    original = " ".join(str(texto).split())
    tipo = tipo.upper()
    if not original:
        raise ValueError("La consulta está vacía")
    if tipo == "EMPRESA":
        return Consulta(original=original, tipo=tipo, razon=original)
    if tipo != "PERSONA":
        raise ValueError("El tipo debe ser PERSONA o EMPRESA")
    # Opcional: nombre(s) | paterno | materno para apellidos compuestos.
    if "|" in texto:
        trozos = [x.strip() for x in texto.split("|")]
        if len(trozos) != 3 or not all(trozos):
            raise ValueError("Usa el formato Nombre(s) | Paterno | Materno")
        nombre, paterno, materno = trozos
    else:
        nombre, paterno, materno = separar_nombre(original)
    return Consulta(original=original, tipo=tipo, nombre=nombre, paterno=paterno, materno=materno)


def analizar_xml(respuesta: str) -> tuple[int, str | None]:
    """Solo da cero si SIGER devuelve formalmente rowCount:0; sesión caída nunca equivale a cero."""
    try:
        raiz = ET.fromstring(respuesta)
    except ET.ParseError as exc:
        raise ValueError("La respuesta no fue XML de SIGER; posible sesión caducada") from exc
    if raiz.tag != "partial-response" or raiz.find("error") is not None:
        raise ValueError("SIGER no devolvió una respuesta AJAX de consulta válida")
    tabla = raiz.find(f".//update[@id='{TABLE_ID}']")
    if tabla is None or not tabla.text:
        raise ValueError("No se recibió la tabla; verifica la sesión o el formulario")
    cuenta = re.search(r"\browCount\s*:\s*(\d+)\b", tabla.text)
    if not cuenta:
        cuenta = re.search(r"\(\s*(\d+)\s+registros\s*\)", tabla.text)
    if not cuenta:
        raise ValueError("No aparece el total de registros en la respuesta")
    view_state = raiz.find(".//update[@id='javax.faces.ViewState']")
    return int(cuenta.group(1)), view_state.text if view_state is not None else None


def fecha_actual() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def exportar_excel(registros: list[Consulta], destino: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = "SIGER"
    ws.append(COLUMNAS)
    for reg in registros:
        ws.append(reg.fila())
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for celda in ws[1]:
        celda.fill = PatternFill("solid", fgColor="17324D")
        celda.font = Font(color="FFFFFF", bold=True)
        celda.alignment = Alignment(wrap_text=True)
    for i, ancho in enumerate([13, 34, 25, 23, 23, 38, 20, 12, 48, 22], 1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    wb.save(destino)


def importar_archivo(ruta: str) -> list[str]:
    """Una columna de nombres, CSV, TXT o XLSX. No almacena resultados en el repositorio."""
    path = Path(ruta)
    suf = path.suffix.lower()
    if suf == ".txt":
        return [x.strip() for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    if suf == ".csv":
        contenido = path.read_text(encoding="utf-8-sig")
        filas = list(csv.reader(contenido.splitlines()))
        return [str(fila[0]).strip() for fila in filas if fila and str(fila[0]).strip()]
    if suf == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            return [str(fila[0]).strip() for fila in wb.active.iter_rows(values_only=True)
                    if fila and fila[0] is not None and str(fila[0]).strip()]
        finally:
            wb.close()
    raise ValueError("Se admiten TXT, CSV y XLSX")
