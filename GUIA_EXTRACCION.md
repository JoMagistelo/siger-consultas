# Plan para extraer los resultados positivos de SIGER

Esta guía NO ejecuta consultas masivas, pagos, ni extracción de documentos; sirve para recopilar la evidencia técnica para desarrollar esa fase sin adivinar parámetros.

## Lo que ya devuelve el programa

- Petición AJAX a `/siger2/xhtml/consulta/consultaPublica/consultaPublica.xhtml`.
- `rowCount`: número total de sociedades encontradas (no necesariamente identidad del socio).
- Primeras diez filas del XML: FME, nombre/razón social, oficina registral y clave técnica `data-rk`.
- Cambios en `javax.faces.ViewState` entre solicitudes.

## Prueba 1: paginación de una búsqueda positiva (sin ingresar a un expediente)

1. Abre el navegador de SIGER, inicia sesión y entra en **Consulta pública**.
2. Realiza una consulta de ejemplo con varias páginas de resultados, idealmente por razón social de una empresa pública.
3. Presiona F12 y entra en **Network > Fetch/XHR**. Activa **Preserve log** y limpia la lista con el botón de papelera.
4. Haz clic sobre la página **2** en el paginador de resultados de SIGER. No presiones Enter.
5. Selecciona en Network la nueva solicitud POST `consultaPublica.xhtml`.
6. Abre **Headers > General**: anota URL, método y status HTTP.
7. Abre **Payload**: copia únicamente los **nombres de parámetros** y los valores no sensibles que indiquen la página/paginación. Tacha `javax.faces.ViewState`, `JSESSIONID` y cualquier token.
8. Abre **Response**: identifica el bloque XML `formValores:dataTableCaratula` y revisa que las filas ya correspondan a página 2.
9. Envíanos una captura de Payload y un extracto de Response con datos de una empresa pública (o redactados).

**Objetivo técnico:** automatizar la paginación completa y guardar todas las coincidencias por FME, sin quedarse en las diez primeras.

## Prueba 2: seleccionar un folio y presionar Revisar

1. Con Network abierto (Fetch/XHR + Preserve log), limpia las solicitudes anteriores.
2. Elige el círculo/radio de un resultado de prueba y espera a que el portal habilite **Revisar**.
3. Examina la petición nueva que se haya disparado al **seleccionar la fila**: captura URL, método y los nombres de campos de Payload. No copies cookies ni ViewState.
4. Presiona **Revisar** y observa si muestra ficha, redirige a otra página o solicita pago.
5. Examina las nuevas solicitudes: anota Request URL, Method y el nombre/estructura del contenido de Response de la acción Revisar, con valores sensibles ocultos.
6. Si aparece una pantalla de pago, detente: el programa no debe continuar ni pagar automáticamente; registraremos que esa información requiere autorización/pago.
7. Si se abre un detalle gratuito, observa si hay secciones, documentos o descargas; para cada botón se estudia una solicitud adicional sin necesidad de abrirlo todo manualmente.

**Objetivo técnico:** determinar la acción necesaria para recuperar la ficha que el portal permite consultar, y cuáles recursos exigen pasos adicionales.

## Diseño de la futura extracción

1. **Coincidencias:** obtener todas las páginas por consulta y guardar el XML bruto con fecha/hora, número de página, nombre consultado, FME y oficina.
2. **Detalle:** según las peticiones capturadas, recuperar el detalle permitido por la cuenta, sin omitir pantallas ni transformar el HTML/XML original.
3. **Archivos:** descargar únicamente documentos que el portal permita legalmente al usuario, conservando nombre, formato y fecha.
4. **Índice:** Excel/CSV con nombre buscado, FME, sociedad, oficina, estado de acceso (`DISPONIBLE`, `REQUIERE_PAGO`, `ERROR`), ruta de evidencia y marca temporal.
5. **Integridad:** en el futuro incluir hash SHA-256 de cada archivo para demostrar que el bruto no fue modificado y vincularlo a las tarjetas de investigación.

### Precauciones

- **No equivale a acceso directo a la BD de SIGER**: solo captura respuestas habilitadas a la sesión.
- Un nombre con coincidencias parciales NO acredita relación jurídica ni identidad.
- No compartir tokens, JSESSIONID, ViewState completo, identificadores de usuarios, contraseñas, datos de expedientes personales ni capturas sin ocultar información sensible.
- Evitar concurrencia agresiva, respetar los límites y los controles del portal y no eludir pagos/CAPTCHA.
