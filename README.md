# SIGER Consultas · v0.2

Aplicación de escritorio para consultar **socios (personas)** y **razones sociales** en SIGER 2.0. Extrae el total de registros de la respuesta AJAX. **No confirma por sí sola la identidad de un socio.** Prototipo pendiente de validación contra la web real desde el equipo del usuario.

## Windows

1. Ejecuta `INSTALAR.bat` (Python 3.11+ recomendado; crea `.venv`).
2. Ejecuta `INICIAR.bat`.
3. Pulsa **Conectar Chrome**, inicia sesión manualmente si hace falta (CAPTCHA incluido) y entra a **Consulta pública**. Al detectar el formulario, la luz se vuelve **verde**.
4. Selecciona **PERSONA** o **EMPRESA**, pega una consulta por línea y observa la normalización en tiempo real.
5. Pulsa **Consultar lista**, luego **Exportar Excel**. Se procesan consultas secuencialmente, con pausa.

**Separación de nombres:** últimas dos palabras = apellidos, todas las anteriores = nombre(s). Ejemplo: `JOSE LUIS CRUZ GOMEZ` → `JOSE LUIS | CRUZ | GOMEZ`. No se adivinan apellidos compuestos: corrige con doble clic o pega `MARIA JOSE | DE LA CRUZ | GOMEZ` (tres campos separados por `|`). La vista previa evita buscar silenciosamente con campos incorrectos.

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
- La luz verde indica disponibilidad del formulario de Consulta pública. Una sesión que caduca se detecta como error en las consultas.

Pruebas: `python -m unittest discover -s tests -v`.
