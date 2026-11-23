# SIGER Consultas — edición portátil Windows x64

## Para personas que reciben el ZIP

1. Descarga `SIGER-Consultas-Windows-x64.zip` desde la publicación del proyecto.
2. Descomprime **toda** la carpeta `SIGER-Consultas` (no ejecutes el EXE desde dentro del ZIP).
3. Abre `SIGER-Consultas\SIGER-Consultas.exe`. No requiere instalar Python, pip, Playwright ni Chrome.
4. Pulsa **Conectar Chrome**: la aplicación abrirá su Chromium empaquetado. Inicia sesión en SIGER y resuelve el CAPTCHA manualmente.
5. Entra a **Consulta pública**. Si aparece el formulario, la luz pasa a verde.
6. Pega nombres en el cuadro o importa Excel/TXT, revisa la vista previa (doble clic para corregir), consulta y exporta los resultados.

El equipo necesita Windows 10/11 de 64 bits, conexión a Internet y autorización de acceso a SIGER. No hacen falta permisos de administrador para extraer el ZIP.

## Qué se incluye y qué no

- El ZIP incluye el ejecutable, bibliotecas Python, Playwright, navegador Chromium y archivos de soporte, por lo que ocupa bastante más que un EXE ordinario.
- **No** incluye cuentas, contraseñas, cookies, CAPTCHA resueltos ni datos de investigaciones.
- La ventana abierta es un navegador propio de la aplicación: no se adjunta automáticamente al Chrome personal del usuario.
- Cada usuario tiene su propio perfil persistente en `%LOCALAPPDATA%\SIGERConsultas\ChromeProfile`. El portal puede pedir iniciar sesión de nuevo cuando caduque.
- Capturas automáticas, temporizador y extracción de fichas registrales **no forman parte de este primer paquete**; son mejoras futuras.
- El ejecutable todavía **no está firmado digitalmente**: Windows SmartScreen o el antivirus institucional pueden advertirlo o bloquearlo. No se debe desactivar la seguridad del equipo. Solicita validación al área de TI antes de distribuirlo institucionalmente.
- Las operaciones se hacen bajo los permisos de la cuenta del usuario. La luz verde indica que hay formulario y ViewState; no verifica por sí sola que el servidor conserve la sesión.

## Para compilar / publicar una nueva versión (mantenedores)

El workflow `.github/workflows/windows-portable.yml` compila automáticamente el ZIP en Windows y ejecuta `SIGER-Consultas.exe --self-test` sin acceder a SIGER. Descarga el archivo desde la pestaña **Actions** del repositorio, ejecución **Windows portable (sin instalar Python)**, sección **Artifacts**.

Después de probarlo manualmente en Windows con la sesión del usuario, se puede usar **Run workflow** en la rama `main`, con `publicar_release=true` y `version=v0.3.0`, para publicar el ZIP en Releases. Esa acción es opcional y explícita; no publica las versiones de los PR sin validarlas.

No publiques archivos Excel, TXT con datos personales, capturas, cookies ni perfiles del navegador en GitHub.

## Problemas habituales

- **El EXE no abre:** confirma que la carpeta fue extraída completa, usa Windows x64 y revisa si TI bloqueó un programa no firmado.
- **Luz amarilla ESPERANDO:** entra a Consulta pública dentro de la ventana de Chromium que abrió SIGER Consultas.
- **Se vuelve a pedir acceso:** la sesión del portal pudo caducar; inicia sesión manualmente otra vez.
- **Consulta sin resultado:** comprueba que SIGER realmente devolvió cero registros y que la solicitud no tuvo errores; un nombre con coincidencias parciales no confirma identidad.
