# Dictado por voz

Aplicacion de dictado por voz para Windows. Graba audio del microfono, lo envia a Whisper (OpenAI), y escribe el texto donde este el cursor — en cualquier programa. Vive como icono de microfono en el system tray (junto al reloj).

**Autor:** Hector de la Iglesia — delaiglesiahector@gmail.com — www.hectordelaiglesia.com

---

## Instalacion (usuarios)

**Solo descarga el ejecutable — no necesitas instalar Python ni nada mas:**

1. Ir a [Releases](../../releases) y descargar `DictadoPorVoz.exe`
2. Ejecutar el archivo (doble clic)
3. La primera vez pedira una **API key de OpenAI** (ver abajo)
4. El icono de microfono aparece junto al reloj

> El antivirus puede alertar porque es un .exe sin firma digital. Es falso positivo — el codigo fuente es abierto y esta en este repositorio.

### Como obtener una API key de OpenAI

1. Entrar a [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Crear una cuenta si no tenes (es gratis)
3. Hacer clic en **Create new secret key**
4. Copiar la key (empieza con `sk-...`) — solo se muestra una vez
5. Pegarla en la configuracion de la app

**Costo:** ~$0.006 USD por minuto de dictado. Con $5 de credito tenes mas de 13 horas.

---

## Uso

- **Atajo de teclado:** `Ctrl+Alt+Espacio` (configurable)
- Colocar el cursor donde se quiere escribir (Word, Chrome, Notepad, Gmail, etc.)
- Presionar el atajo para **iniciar** la grabacion
- Hablar con claridad
- Presionar el atajo de nuevo para **parar** y transcribir
- El texto aparece escrito donde estaba el cursor

### Colores del icono

| Color | Estado |
|-------|--------|
| Verde oscuro | Listo |
| Rojo | Grabando |
| Naranja | Transcribiendo |

---

## Menu (clic derecho en el icono)

- **Iniciar / Parar grabacion**
- **Configurar...** — cambiar API key y atajo de teclado
- **Ayuda...**
- **Acerca de...**
- **Iniciar con Windows** — activa/desactiva el autostart
- **Salir**

---

## Desarrollo

### Dependencias

```
py -3 -m pip install sounddevice keyboard pyperclip numpy pystray pillow
```

`requests` ya viene incluido en Python. **No usar `pyaudio`** — no compila en Python 3.14 sin Visual C++.

### Ejecutar en desarrollo

```
py -3 dictado_voz.pyw
```

### Compilar el ejecutable

```
cd "G:\Unidades compartidas\Héctor\Proyectos\Dictado"
py -3 -m PyInstaller --onefile --windowed --name "DictadoPorVoz" --hidden-import sounddevice --hidden-import pystray._win32 --hidden-import PIL._tkinter_finder --collect-data pystray dictado_voz.pyw
```

El resultado queda en `dist\DictadoPorVoz.exe` (~36 MB, todo incluido).

### Arquitectura

- **Hilo principal:** loop de pystray (`icono_tray.run()`) — debe estar siempre aqui
- **Hilo tkinter** (daemon): ventana `Tk()` oculta para todas las ventanas modales
- **Hilos audio/transcripcion** (daemon): grabacion con sounddevice + POST a Whisper

---

## Archivos

| Archivo | Descripcion |
|---------|-------------|
| `dictado_voz.pyw` | Aplicacion completa (unico archivo fuente) |
| `config.json` | API key y hotkey (se crea automaticamente, **no subir a git**) |
| `dist/DictadoPorVoz.exe` | Ejecutable compilado para distribuir |
