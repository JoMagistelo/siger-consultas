# SIGER Consultas · v0.3 (beta)

Aplicación de escritorio para consultar **socios (personas)** y **razones sociales** en SIGER 2.0. Extrae el total de registros de la respuesta AJAX. **No confirma por sí sola la identidad de un socio.** El modo secuencial ya fue validado por el usuario contra la web real; el modo paralelo es experimental.

## Windows portátil (para quienes NO instalan Python)

Existe un flujo de GitHub Actions `Windows portable (sin instalar Python)` que construye `SIGER-Consultas-Windows-x64.zip` con el EXE, Playwright y Chromium integrado. Después de validarlo en Windows, se puede publicar como Release para descargarlo sin cuenta GitHub.

**Uso:** descargar el ZIP, extraer la carpeta completa, ejecutar `SIGER-Consultas.exe` e iniciar sesión manualmente. No requiere Python, pip, Playwright ni Chrome instalados. El usuario sigue necesitando Windows x64, conexión a Internet y cuenta válida de SIGER. El ejecutable no está firmado digitalmente.

Ver [Guía de distribución portátil](GUIA_PORTABLE.md) y [paso a paso para capturar las solicitudes de paginación y Revisar](GUIA_EXTRACCION.md).

**Alcance de esta primera versión:** búsquedas, edición de criterios, clasificación y exportación. Aún no incluye capturas automáticas, cronómetro ni extracción de detalles completos.

## Windows

1. Ejecuta `INSTALAR.bat` (Python 3.11+ recomendado; crea `.venv`).
2. Ejecuta `INICIAR.bat`.
3. Pulsa **Conectar Chrome**, inicia sesión manualmente si hace falta (CAPTCHA incluido) y entra a **Consulta pública**. Al detectar el formulario, la luz se vuelve **verde**.
4. Selecciona **PERSONA** o **EMPRESA**, pega una consulta por línea y observa la normalización en tiempo real.
5. Pulsa **Consultar lista** para el modo seguro (una consulta a la vez). Opcionalmente, **Consultar 2 a la vez (beta)** intenta dos vistas independientes de JSF, con dos `ViewState` distintos y un máximo de dos solicitudes simultáneas; si SIGER no permite inicializarlas, vuelve automáticamente al modo uno a uno. **No garantiza más velocidad**, y aún requiere una prueba real con SIGER.
6. Pulsa **Exportar Excel** cuando termine el lote. Si hay entradas repetidas con exactamente los mismos criterios, se envía una sola consulta y se aplica el mismo resultado a todas esas filas.

**Separación de nombres:** últimas dos palabras = apellidos, todas las anteriores = nombre(s). Ejemplo: `JOSE LUIS CRUZ GOMEZ` → `JOSE LUIS | CRUZ | GOMEZ`. No se adivinan apellidos compuestos: **haz doble clic sobre una celda de la vista previa** (entrada completa, nombre(s), paterno o materno), edita directamente, pulsa **Enter** para aceptar o **Escape** para descartar. En empresas se edita la primera columna. Cada cambio invalida el resultado anterior de esa fila, de modo que se consulta el valor efectivamente corregido. Las correcciones se conservan mientras su línea original permanezca en el área de entrada. **En búsquedas de PERSONA puedes dejar en blanco cualquiera de las tres celdas individualmente** (Nombre(s), Paterno o Materno); la aplicación enviará ese campo vacío. Debe quedar al menos un criterio con texto para evitar una consulta sin filtros. La primera columna de origen y la razón social deben tener texto. También puedes pegar `MARIA JOSE | DE LA CRUZ | GOMEZ` o ` | CRUZ | ` (tres campos separados por `|`, aunque algunos estén vacíos). La vista previa evita buscar silenciosamente con campos incorrectos.

**Chrome y sesiones:** se intenta conectar a un Chrome habilitado en `127.0.0.1:9222`; un Chrome normal ya abierto **no permite** adjuntar Playwright retroactivamente. Si no existe esa conexión, se abre Chrome con perfil independiente persistente en `%LOCALAPPDATA%\SIGERConsultas\ChromeProfile`, que conserva la sesión y las preferencias **si SIGER no la caduca**. Es normal que el primer inicio exija iniciar sesión de nuevo. Por seguridad, no se lee ni copia el perfil principal de Chrome ni se extraen contraseñas o cookies. No se automatiza CAPTCHA. El indicador verde significa formulario disponible y ViewState presente, no una comprobación independiente del permiso del servidor.

Para iniciar **deliberadamente** un Chrome depurable con perfil aislado (opcional), cierra la instancia de ese perfil y ejecuta en PowerShell:

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="$env:LOCALAPPDATA\SIGERConsultas\ChromeDepurable" "https://rpc.economia.gob.mx/siger2/xhtml/consulta/consultaPublica/consultaPublica.xhtml"
```

Chrome moderno no admite depuración remota del perfil predeterminado. No expongas el puerto 9222 fuera de tu equipo.

## Seguridad y límites

- El repositorio puede ser público: **nunca** publiques listas con personas reales, resultados ni datos privados. `.gitignore` excluye hojas de cálculo, CSV, TXT, perfiles, sesiones y entornos virtuales.
- Los resultados son `ENCONTRADO` (>0), `SIN RESULTADOS` (=0 verificado) y `ERROR` (red, login, XML, etc.). Una búsqueda por término parcial no demuestra relación societaria ni identidad.
- No se usa una conexión directa a una base de datos ni se evita el CAPTCHA. El procesamiento de SIGER puede tardar y las búsquedas deben respetar los límites del portal.
- **Modo beta:** no comparte un mismo `ViewState` para peticiones paralelas. Intenta abrir dos vistas de consulta separadas dentro del mismo navegador autenticado y comprueba que sus estados sean distintos; si no puede, recurre al procesamiento secuencial. Las vistas usan la misma cuenta/sesión autenticada y podrían seguir teniendo restricciones internas del servidor; no utilices la opción beta como prueba definitiva de ausencia de coincidencias sin verificar su comportamiento con consultas conocidas.
- La luz verde indica disponibilidad del formulario de Consulta pública. Una sesión que caduca se detecta como error en las consultas.

Pruebas: `python -m unittest discover -s tests -v`.
