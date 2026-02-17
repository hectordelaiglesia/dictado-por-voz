# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proyecto

Aplicación de dictado por voz para Windows. Graba audio del micrófono, lo envía a Whisper (OpenAI), y escribe el texto transcripto donde esté el cursor — en cualquier programa. Vive como ícono en el system tray (junto al reloj).

**Autor:** Héctor De La Iglesia — delaiglesiahector@gmail.com — www.hectordelaiglesia.com
**Idioma del código:** español (comentarios, UI, logs)

## Archivos principales

- **`dictado_voz.pyw`** — aplicación completa (único archivo fuente). `.pyw` = sin consola negra al doble clic.
- **`config.json`** — persiste API key y hotkey. Se crea automáticamente. Usar siempre `guardar_config()` para escribirlo (hace merge, nunca reemplaza completo).
- **`dist/DictadoPorVoz.exe`** — ejecutable compilado para distribución (no editar, recompilar cuando cambie el .pyw).
- **`DictadoPorVoz.spec`** — spec de PyInstaller, se regenera al compilar.

## Dependencias

```
py -3 -m pip install sounddevice keyboard pyperclip numpy pystray pillow
```
`requests` ya viene incluido en Python. **No usar `pyaudio`** — no compila en Python 3.14 sin Visual C++; usar `sounddevice` en su lugar.

## Ejecutar en desarrollo

```
py -3 dictado_voz.pyw
```
O doble clic en el archivo.

## Compilar el ejecutable

```
cd "G:\Unidades compartidas\Héctor\Proyectos\Dictado"
py -3 -m PyInstaller --onefile --windowed --name "DictadoPorVoz" --hidden-import sounddevice --hidden-import pystray._win32 --hidden-import PIL._tkinter_finder --collect-data pystray dictado_voz.pyw
```
El resultado queda en `dist\DictadoPorVoz.exe` (~36 MB, todo incluido).

## Arquitectura de hilos

Este es el aspecto más crítico del código. Hay **tres hilos**:

| Hilo | Qué hace | Restricciones |
|------|----------|---------------|
| **Principal** | Loop de pystray (`icono_tray.run()`) | `pystray.run()` DEBE correr aquí siempre |
| **Tkinter** (daemon) | `tk.Tk()` oculto + todas las ventanas modales | Toda UI de tkinter va aquí via `_en_hilo_tk()` |
| **Audio/transcripción** (daemon) | Grabación sounddevice + POST a Whisper | Nunca toca tkinter ni pystray directamente |

**Regla de oro:** Nunca llamar `app.run()` desde el hilo tkinter. En el flujo de primera vez se usa `threading.Event` para que el hilo principal espere la señal y llame `run()` él mismo.

**Para actualizar UI desde cualquier hilo:** usar `self._en_hilo_tk(func)` (llama `tk_root.after(0, func)`).

## Clases principales

**`DictadoApp`** — clase central, instanciada una sola vez en `main()`:
- `_set_estado(estado)` — único punto de actualización de estado; actualiza ícono del tray, menú e `IndicadorVisual` atómicamente desde cualquier hilo
- `_toggle_grabacion()` — callback del hotkey global; alterna entre `_iniciar_grabacion()` / `_parar_grabacion()`
- `_llamar_whisper(wav_bytes)` — POST multipart a `https://api.openai.com/v1/audio/transcriptions` con `requests` (sin SDK de openai)
- `_escribir_texto(texto)` — escribe via clipboard + Ctrl+V para soportar acentos; fallback a `keyboard.write()`
- Todas las ventanas modales (`_abrir_ventana_config`, `_abrir_ventana_ayuda`, `_abrir_ventana_acerca_de`, `_abrir_ventana_config_inicial`) deben llamarse desde el hilo tkinter

**`IndicadorVisual`** — ventana `Toplevel` sin bordes, centrada, semitransparente. Se crea oculta y se muestra/oculta con `mostrar(estado)`/`ocultar()`. Anima un punto pulsante con `canvas.after(40, ...)`.

## Config

```json
{
  "openai_api_key": "sk-...",
  "hotkey": "ctrl+alt+space"
}
```
Se guarda en el mismo directorio que el `.pyw` / `.exe`. Usar siempre `guardar_config(dict)` para hacer merge sin destruir claves existentes.

## Autostart con Windows

Crea/elimina `dictado_voz.bat` en `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`. No requiere permisos de administrador. El .bat invoca `pythonw.exe` con la ruta absoluta al script.

## Constantes a actualizar para nueva versión

```python
APP_VERSION = "1.0"          # incrementar al distribuir nueva versión
APP_AUTOR   = "Hector De La Iglesia"
APP_EMAIL   = "delaiglesiahector@gmail.com"
APP_WEB     = "www.hectordelaiglesia.com"
```

## Audio

- Formato: 16kHz mono float32 (sounddevice) → convertido a int16 WAV en memoria (sin archivo temporal en disco)
- `frames_a_wav(frames_np)` — convierte array numpy a bytes WAV listos para enviar a la API
- El idioma forzado a Whisper es `"es"` (español); cambiar en `_llamar_whisper()` si se necesita otro
