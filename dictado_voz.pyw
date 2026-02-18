"""
Dictado por voz con Whisper (OpenAI) — System Tray
====================================================
Aparece como icono de microfono junto al reloj de Windows.
Clic derecho en el icono para ver el menu.
Presiona Ctrl+Alt+Espacio para iniciar/parar la grabacion.
El texto transcripto aparece escrito donde este el cursor.

Dependencias (instalar una sola vez):
  py -3 -m pip install sounddevice keyboard pyperclip numpy pystray pillow

Uso: Doble clic en este archivo.
"""

import tkinter as tk
from tkinter import messagebox
import threading
import json
import os
import io
import time
import wave
import webbrowser
import numpy as np

import sounddevice as sd     # pip install sounddevice
import keyboard              # pip install keyboard
import pyperclip             # pip install pyperclip
import requests              # ya instalado
import pystray               # pip install pystray
from PIL import Image, ImageDraw, ImageFont   # pip install pillow

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH    = os.path.join(SCRIPT_DIR, "config.json")
HOTKEY_DEFAULT = "ctrl+alt+space"
WHISPER_URL    = "https://api.openai.com/v1/audio/transcriptions"
URL_API_KEYS   = "https://platform.openai.com/api-keys"
APP_NOMBRE      = "Dictado por voz"
APP_VERSION     = "1.0"
APP_AUTOR       = "Hector De La Iglesia"
APP_EMAIL       = "delaiglesiahector@gmail.com"
APP_WEB         = "www.hectordelaiglesia.com"
APP_GITHUB      = "github.com/hectordelaiglesia/dictado-por-voz"

# Carpeta Startup del usuario actual (sin permisos de admin)
STARTUP_DIR    = os.path.join(
    os.environ.get("APPDATA", ""),
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
)
STARTUP_BAT    = os.path.join(STARTUP_DIR, "dictado_voz.bat")

# Parametros de audio
SAMPLE_RATE = 16000
CHANNELS    = 1

# Colores del icono segun estado
COLORES_ICONO = {
    "listo":          "#1B5E20",   # verde oscuro
    "grabando":       "#C62828",   # rojo
    "transcribiendo": "#E65100",   # naranja oscuro
    "error":          "#6D1A1A",   # rojo muy oscuro
}

# Textos del tooltip segun estado
TOOLTIPS = {
    "listo":          "Dictado por voz - Listo",
    "grabando":       "Dictado por voz - Grabando...",
    "transcribiendo": "Dictado por voz - Transcribiendo...",
    "error":          "Dictado por voz - Error",
}

# Textos del item de estado en el menu
TEXTOS_ESTADO = {
    "listo":          "Estado: Listo",
    "grabando":       "Estado: Grabando...",
    "transcribiendo": "Estado: Transcribiendo...",
    "error":          "Estado: Error",
}


# ---------------------------------------------------------------------------
# Utilidades de configuracion
# ---------------------------------------------------------------------------

def cargar_config():
    """Lee config.json. Retorna dict con la config, o None si no hay API key."""
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("openai_api_key", "").strip():
            return cfg
    except Exception:
        pass
    return None


def guardar_config(nuevos_valores):
    """
    Merge: lee el JSON existente y agrega/pisa solo las claves indicadas.
    No toca otras claves que pueda haber en el archivo.
    """
    config_actual = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config_actual = json.load(f)
        except Exception:
            pass
    config_actual.update(nuevos_valores)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_actual, f, indent=2, ensure_ascii=False)
    return config_actual


# ---------------------------------------------------------------------------
# Utilidades de audio
# ---------------------------------------------------------------------------

def frames_a_wav(frames_np, sample_rate=SAMPLE_RATE):
    """
    Convierte array numpy float32 [-1, 1] a bytes de archivo WAV (int16).
    """
    audio_int16 = (frames_np * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Generacion del icono de microfono con Pillow
# ---------------------------------------------------------------------------

def crear_icono_microfono(estado="listo", size=64):
    """
    Genera un icono PIL con forma de microfono para el system tray.
    El color de fondo cambia segun el estado (listo/grabando/etc).
    """
    color_fondo = COLORES_ICONO.get(estado, "#1B5E20")
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Fondo: circulo con color de estado
    margen = 2
    d.ellipse(
        [margen, margen, size - margen - 1, size - margen - 1],
        fill=color_fondo
    )

    # --- Microfono ---
    cx = size // 2
    blanco = "#FFFFFF"

    # Cuerpo del microfono (capsula redondeada)
    mic_ancho = int(size * 0.28)
    mic_alto  = int(size * 0.38)
    mic_x0    = cx - mic_ancho // 2
    mic_y0    = int(size * 0.12)
    mic_x1    = cx + mic_ancho // 2
    mic_y1    = mic_y0 + mic_alto
    d.rounded_rectangle(
        [mic_x0, mic_y0, mic_x1, mic_y1],
        radius=mic_ancho // 2,
        fill=blanco
    )

    # Arco de captura (herradura por debajo del microfono)
    arco_margen = int(size * 0.18)
    arco_y0     = int(size * 0.30)
    arco_y1     = int(size * 0.65)
    grosor      = max(2, int(size * 0.055))

    # Dibujar el arco como un set de lineas (ImageDraw no tiene arco de borde solo)
    # Usamos un anillo: ellipse grande - ellipse chica del mismo color que el fondo
    d.arc(
        [arco_margen, arco_y0, size - arco_margen, arco_y1],
        start=0, end=180,
        fill=blanco,
        width=grosor
    )

    # Palito vertical bajo el arco (la base)
    base_x       = cx
    palito_y0    = int(size * 0.64)
    palito_y1    = int(size * 0.76)
    d.line(
        [(base_x, palito_y0), (base_x, palito_y1)],
        fill=blanco,
        width=grosor
    )

    # Base horizontal (pie del microfono)
    pie_ancho = int(size * 0.30)
    pie_y     = int(size * 0.76)
    d.line(
        [(cx - pie_ancho // 2, pie_y), (cx + pie_ancho // 2, pie_y)],
        fill=blanco,
        width=grosor
    )

    return img


# ---------------------------------------------------------------------------
# Indicador visual de estado (burbuja centrada en pantalla)
# ---------------------------------------------------------------------------

class IndicadorVisual:
    """
    Ventana sin bordes centrada en pantalla que muestra el estado del dictado.
    Aparece al iniciar la grabacion y desaparece al terminar.

    Estados:
      "grabando"       -> fondo oscuro, punto rojo pulsante, texto GRABANDO
      "transcribiendo" -> fondo oscuro, punto naranja pulsante, texto Transcribiendo...
      oculto           -> ventana escondida (no destruida, para reusar)
    """

    # Colores
    COLOR_FONDO       = "#1A1A1A"     # gris muy oscuro, casi negro
    COLOR_TEXTO_GRAB  = "#FF4444"     # rojo brillante
    COLOR_TEXTO_TRANS = "#FF9900"     # naranja
    COLOR_TEXTO_INFO  = "#CCCCCC"     # gris claro para texto secundario
    ALPHA             = 0.88          # transparencia de la ventana

    # Tamanos
    ANCHO  = 340
    ALTO   = 120
    RADIO  = 10   # radio del punto pulsante (canvas)

    def __init__(self, tk_root):
        """
        tk_root: el tk.Tk() oculto de la app principal.
        La ventana se crea oculta y se muestra/oculta con mostrar()/ocultar().
        """
        self.root    = tk_root
        self.ventana = None
        self._pulso_id   = None   # id del after() de la animacion
        self._pulso_grow = True   # direccion de la animacion
        self._pulso_r    = self.RADIO   # radio actual del punto
        self._visible    = False

        self._crear_ventana()

    def _crear_ventana(self):
        """Crea la ventana Toplevel sin bordes, oculta inicialmente."""
        v = tk.Toplevel(self.root)
        v.overrideredirect(True)          # sin bordes ni barra de titulo
        v.attributes("-topmost", True)    # siempre encima
        v.attributes("-alpha", self.ALPHA)
        v.configure(bg=self.COLOR_FONDO)
        v.withdraw()                      # empieza oculta

        # Centrar en pantalla
        sw = v.winfo_screenwidth()
        sh = v.winfo_screenheight()
        x  = (sw - self.ANCHO) // 2
        y  = (sh - self.ALTO)  // 2
        v.geometry(f"{self.ANCHO}x{self.ALTO}+{x}+{y}")

        # --- Layout interno ---
        # Canvas para el punto pulsante (lado izquierdo)
        self.canvas = tk.Canvas(
            v,
            width=40, height=self.ALTO,
            bg=self.COLOR_FONDO,
            highlightthickness=0
        )
        self.canvas.pack(side=tk.LEFT, padx=(18, 0))

        # Frame derecho: texto principal + texto secundario
        frame_texto = tk.Frame(v, bg=self.COLOR_FONDO)
        frame_texto.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        self.lbl_estado = tk.Label(
            frame_texto,
            text="",
            font=("Arial", 22, "bold"),
            bg=self.COLOR_FONDO,
            fg=self.COLOR_TEXTO_GRAB,
            anchor="w"
        )
        self.lbl_estado.pack(anchor="w", pady=(22, 2))

        self.lbl_info = tk.Label(
            frame_texto,
            text="",
            font=("Arial", 10),
            bg=self.COLOR_FONDO,
            fg=self.COLOR_TEXTO_INFO,
            anchor="w"
        )
        self.lbl_info.pack(anchor="w")

        # Borde redondeado simulado: frame exterior con borde de color
        v.configure(highlightbackground="#333333", highlightthickness=1)

        self.ventana = v

    def mostrar(self, estado, hotkey="Ctrl+Alt+Espacio"):
        """
        Muestra el indicador con el estado dado ("grabando" o "transcribiendo").
        hotkey: texto del atajo para mostrar en el subtitulo (ej: "CTRL+ALT+SPACE")
        Se puede llamar desde cualquier hilo via tk_root.after().
        """
        if estado == "grabando":
            color_punto = "#FF3333"
            color_texto = self.COLOR_TEXTO_GRAB
            texto_principal = "GRABANDO"
            texto_info      = f"Habla ahora  \u2022  {hotkey} para parar"
        elif estado == "transcribiendo":
            color_punto = "#FF9900"
            color_texto = self.COLOR_TEXTO_TRANS
            texto_principal = "Transcribiendo..."
            texto_info      = "Enviando audio a Whisper..."
        else:
            return

        self.lbl_estado.config(text=texto_principal, fg=color_texto)
        self.lbl_info.config(text=texto_info)
        self._color_punto = color_punto

        # Recentrar por si cambio la resolucion
        sw = self.ventana.winfo_screenwidth()
        sh = self.ventana.winfo_screenheight()
        x  = (sw - self.ANCHO) // 2
        y  = (sh - self.ALTO)  // 2
        self.ventana.geometry(f"{self.ANCHO}x{self.ALTO}+{x}+{y}")

        self.ventana.deiconify()
        self.ventana.lift()
        self._visible = True

        # Iniciar animacion de pulso
        self._pulso_r    = self.RADIO
        self._pulso_grow = True
        self._animar_pulso()

    def ocultar(self):
        """Oculta el indicador y detiene la animacion."""
        self._visible = False
        if self._pulso_id:
            try:
                self.ventana.after_cancel(self._pulso_id)
            except Exception:
                pass
            self._pulso_id = None
        if self.ventana:
            self.ventana.withdraw()

    def _animar_pulso(self):
        """
        Anima el punto pulsante: crece y achica suavemente.
        Se llama a si misma con after() cada 40ms (~25fps).
        """
        if not self._visible:
            return

        # Actualizar radio
        if self._pulso_grow:
            self._pulso_r += 1.2
            if self._pulso_r >= self.RADIO + 6:
                self._pulso_grow = False
        else:
            self._pulso_r -= 1.2
            if self._pulso_r <= self.RADIO - 4:
                self._pulso_grow = True

        r   = self._pulso_r
        cx  = 20   # centro x del canvas (canvas width=40)
        cy  = self.ALTO // 2

        # Redibujar punto
        self.canvas.delete("all")
        # Halo exterior semi-transparente (circulo mas grande, color mas tenue)
        halo_r = r + 5
        self.canvas.create_oval(
            cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r,
            fill="",
            outline=self._color_punto,
            width=1
        )
        # Punto solido
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self._color_punto,
            outline=""
        )

        # Programar siguiente frame
        self._pulso_id = self.ventana.after(40, self._animar_pulso)

    def destruir(self):
        """Destruye la ventana al cerrar la app."""
        self.ocultar()
        if self.ventana:
            try:
                self.ventana.destroy()
            except Exception:
                pass
            self.ventana = None


# ---------------------------------------------------------------------------
# Autostart con Windows
# ---------------------------------------------------------------------------

def autostart_activo():
    """Retorna True si el .bat de autostart existe en la carpeta Startup."""
    return os.path.exists(STARTUP_BAT)


def activar_autostart():
    """
    Crea un archivo .bat en la carpeta Startup del usuario que lanza la app
    con pythonw.exe (sin consola negra).
    """
    # Buscar pythonw.exe junto al python.exe del interprete actual
    import sys
    python_dir = os.path.dirname(sys.executable)
    pythonw    = os.path.join(python_dir, "pythonw.exe")
    if not os.path.exists(pythonw):
        # Fallback: usar pythonw sin ruta absoluta (tiene que estar en PATH)
        pythonw = "pythonw"

    script_path = os.path.abspath(__file__)

    # Si el script esta en una unidad de red (ej: G:\), esperar a que este montada
    unidad = os.path.splitdrive(script_path)[0]  # "G:" o "C:" etc.
    contenido   = (
        f'@echo off\n'
        f':esperar\n'
        f'if not exist "{unidad}\\" (\n'
        f'    timeout /t 2 /nobreak >nul\n'
        f'    goto esperar\n'
        f')\n'
        f'start "" "{pythonw}" "{script_path}"\n'
    )
    os.makedirs(STARTUP_DIR, exist_ok=True)
    with open(STARTUP_BAT, "w", encoding="utf-8") as f:
        f.write(contenido)


def desactivar_autostart():
    """Elimina el .bat de la carpeta Startup."""
    if os.path.exists(STARTUP_BAT):
        os.remove(STARTUP_BAT)


# ---------------------------------------------------------------------------
# Clase principal: DictadoApp
# ---------------------------------------------------------------------------

class DictadoApp:
    """
    Aplicacion de dictado por voz con icono en el system tray.
    - Hilo principal: loop de pystray (icono + menu)
    - Hilo tkinter:  ventana Tk() oculta para modales
    - Hilos daemon:  grabacion, transcripcion
    """

    def __init__(self, config):
        self.config  = config
        self.api_key = config.get("openai_api_key", "")
        self.hotkey  = config.get("hotkey", HOTKEY_DEFAULT)

        # Estado
        self.estado         = "listo"
        self.grabando       = False
        self.audio_chunks   = []
        self.hilo_grabacion = None

        # Icono pystray (se crea en run())
        self.icono_tray = None

        # Raiz tkinter oculta para ventanas modales (corre en su propio hilo)
        self.tk_root   = None
        self.indicador = None   # se crea despues de que el hilo tk este listo
        self._iniciar_hilo_tkinter()

        # Crear el indicador visual (requiere que tk_root ya exista)
        self._en_hilo_tk(self._crear_indicador)

        # Registrar hotkey global
        self._registrar_hotkey()

    # ------------------------------------------------------------------ #
    #  Hilo de tkinter (ventanas modales)
    # ------------------------------------------------------------------ #

    def _iniciar_hilo_tkinter(self):
        """Crea el tk.Tk() oculto en un hilo daemon separado."""
        hilo = threading.Thread(target=self._loop_tkinter, daemon=True)
        hilo.start()
        # Esperar a que el root este listo
        time.sleep(0.3)

    def _loop_tkinter(self):
        """Hilo que mantiene vivo el tk.Tk() oculto."""
        self.tk_root = tk.Tk()
        self.tk_root.withdraw()          # ocultarla, no aparece en taskbar
        self.tk_root.attributes("-topmost", True)
        self.tk_root.mainloop()

    def _en_hilo_tk(self, func):
        """Ejecuta func() de forma segura en el hilo de tkinter."""
        if self.tk_root:
            self.tk_root.after(0, func)

    def _mostrar_error(self, titulo, mensaje):
        """Muestra messagebox de error desde cualquier hilo."""
        def _mostrar():
            messagebox.showerror(titulo, mensaje)
        self._en_hilo_tk(_mostrar)

    def _mostrar_info(self, titulo, mensaje):
        """Muestra messagebox de info desde cualquier hilo."""
        def _mostrar():
            messagebox.showinfo(titulo, mensaje)
        self._en_hilo_tk(_mostrar)

    def _crear_indicador(self):
        """Crea el IndicadorVisual (debe llamarse desde el hilo tkinter)."""
        self.indicador = IndicadorVisual(self.tk_root)

    # ------------------------------------------------------------------ #
    #  Estado e icono
    # ------------------------------------------------------------------ #

    def _set_estado(self, nuevo_estado):
        """
        Actualiza el estado, el icono del tray, el menu y el indicador visual.
        Seguro para llamar desde cualquier hilo.
        """
        self.estado = nuevo_estado
        if self.icono_tray:
            self.icono_tray.icon  = crear_icono_microfono(nuevo_estado)
            self.icono_tray.title = TOOLTIPS.get(nuevo_estado, APP_NOMBRE)
            self.icono_tray.menu  = self._construir_menu()

        # Indicador visual: mostrar si graba/transcribe, ocultar si listo/error
        if nuevo_estado in ("grabando", "transcribiendo"):
            self._en_hilo_tk(lambda e=nuevo_estado: self._mostrar_indicador(e))
        else:
            self._en_hilo_tk(self._ocultar_indicador)

    def _mostrar_indicador(self, estado):
        """Muestra el indicador visual (debe llamarse desde el hilo tkinter)."""
        if self.indicador:
            hk = self.hotkey.replace("space", "Espacio").upper()
            self.indicador.mostrar(estado, hotkey=hk)

    def _ocultar_indicador(self):
        """Oculta el indicador visual (debe llamarse desde el hilo tkinter)."""
        if self.indicador:
            self.indicador.ocultar()

    # ------------------------------------------------------------------ #
    #  Menu del tray
    # ------------------------------------------------------------------ #

    def _construir_menu(self):
        """Construye el menu contextual del icono del tray."""
        texto_estado    = TEXTOS_ESTADO.get(self.estado, "Estado: Listo")
        texto_grabar    = "Parar grabacion" if self.grabando else "Iniciar grabacion"
        autostart_check = autostart_activo()

        return pystray.Menu(
            pystray.MenuItem(
                APP_NOMBRE,
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                texto_estado,
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                texto_grabar,
                self._menu_toggle_grabacion
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Configurar...",
                self._menu_configurar
            ),
            pystray.MenuItem(
                "Ayuda...",
                self._menu_ayuda
            ),
            pystray.MenuItem(
                "Acerca de...",
                self._menu_acerca_de
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Iniciar con Windows",
                self._menu_toggle_autostart,
                checked=lambda item: autostart_activo()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Salir",
                self._menu_salir
            ),
        )

    # ------------------------------------------------------------------ #
    #  Callbacks del menu
    # ------------------------------------------------------------------ #

    def _menu_toggle_grabacion(self, icon=None, item=None):
        """Inicia o para la grabacion desde el menu."""
        self._toggle_grabacion()

    def _menu_toggle_autostart(self, icon=None, item=None):
        """Activa o desactiva el inicio automatico con Windows."""
        if autostart_activo():
            desactivar_autostart()
        else:
            try:
                activar_autostart()
            except Exception as e:
                self._mostrar_error(
                    "Error de autostart",
                    f"No se pudo activar el inicio automatico:\n{e}"
                )

    def _menu_configurar(self, icon=None, item=None):
        """Abre la ventana de configuracion."""
        self._en_hilo_tk(self._abrir_ventana_config)

    def _menu_ayuda(self, icon=None, item=None):
        """Abre la ventana de ayuda."""
        self._en_hilo_tk(self._abrir_ventana_ayuda)

    def _menu_acerca_de(self, icon=None, item=None):
        """Abre la ventana Acerca de."""
        self._en_hilo_tk(self._abrir_ventana_acerca_de)

    def _menu_salir(self, icon=None, item=None):
        """Cierra la aplicacion limpiamente."""
        self._cerrar()

    # ------------------------------------------------------------------ #
    #  Grabacion de audio
    # ------------------------------------------------------------------ #

    def _registrar_hotkey(self):
        """Registra el hotkey global. Funciona aunque la app no tenga foco."""
        try:
            keyboard.add_hotkey(self.hotkey, self._toggle_grabacion,
                                suppress=False)
        except Exception as e:
            self._mostrar_error(
                "Error al registrar atajo",
                f"No se pudo registrar el atajo '{self.hotkey}':\n{e}\n\n"
                "Proba cambiar el atajo en 'Configurar...'."
            )

    def _toggle_grabacion(self):
        """Alterna entre iniciar y parar la grabacion."""
        if self.grabando:
            self._parar_grabacion()
        else:
            self._iniciar_grabacion()

    def _iniciar_grabacion(self):
        """Inicia la captura de audio en un hilo separado."""
        if self.grabando:
            return
        self.grabando     = True
        self.audio_chunks = []
        self._set_estado("grabando")

        self.hilo_grabacion = threading.Thread(
            target=self._loop_grabacion, daemon=True
        )
        self.hilo_grabacion.start()

    def _loop_grabacion(self):
        """
        Hilo de grabacion: captura audio con sounddevice hasta que
        self.grabando sea False.
        """
        def callback(indata, frames, time_info, status):
            if self.grabando:
                self.audio_chunks.append(indata[:, 0].copy())

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                callback=callback,
                blocksize=1024
            ):
                while self.grabando:
                    time.sleep(0.05)
        except Exception as e:
            self.grabando = False
            self._set_estado("error")
            self._mostrar_error(
                "Error de microfono",
                f"No se pudo acceder al microfono:\n{e}"
            )
            time.sleep(3)
            self._set_estado("listo")

    def _parar_grabacion(self):
        """Para la grabacion y lanza la transcripcion."""
        if not self.grabando:
            return
        self.grabando = False
        self._set_estado("transcribiendo")

        # Esperar que el stream se cierre limpiamente
        if self.hilo_grabacion and self.hilo_grabacion.is_alive():
            self.hilo_grabacion.join(timeout=1.5)

        chunks = self.audio_chunks[:]
        hilo_tx = threading.Thread(
            target=self._transcribir_y_escribir,
            args=(chunks,),
            daemon=True
        )
        hilo_tx.start()

    # ------------------------------------------------------------------ #
    #  Transcripcion y escritura
    # ------------------------------------------------------------------ #

    def _transcribir_y_escribir(self, chunks):
        """Convierte audio a WAV, llama a Whisper, escribe el texto."""
        if not chunks:
            self._set_estado("listo")
            return

        try:
            audio_np  = np.concatenate(chunks)
            wav_bytes = frames_a_wav(audio_np)
            texto     = self._llamar_whisper(wav_bytes)
        except Exception as e:
            self._set_estado("error")
            self._mostrar_error("Error de transcripcion", str(e))
            time.sleep(3)
            self._set_estado("listo")
            return

        if texto:
            self._escribir_texto(texto)

        self._set_estado("listo")

    def _llamar_whisper(self, wav_bytes):
        """
        POST a la API de Whisper de OpenAI.
        Retorna el texto o lanza Exception con mensaje claro.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files   = {
            "file":     ("audio.wav", wav_bytes, "audio/wav"),
            "model":    (None, "whisper-1"),
            "language": (None, "es"),
        }

        try:
            resp = requests.post(
                WHISPER_URL, headers=headers, files=files, timeout=30
            )
        except requests.exceptions.ConnectionError:
            raise Exception(
                "Sin conexion a internet.\n"
                "Verificar que la red este funcionando."
            )
        except requests.exceptions.Timeout:
            raise Exception(
                "La transcripcion tardo demasiado.\n"
                "Intenta de nuevo con una grabacion mas corta."
            )

        if resp.status_code == 401:
            raise Exception(
                "API key invalida o vencida.\n\n"
                "Ir a 'Configurar...' para actualizarla.\n"
                "Obtene una nueva en:\n" + URL_API_KEYS
            )
        if resp.status_code == 429:
            raise Exception(
                "Limite de uso de la API alcanzado.\n"
                "Espera un momento o revisa tu cuenta en:\n"
                "platform.openai.com/account/usage"
            )
        if resp.status_code != 200:
            raise Exception(
                f"Error de API (HTTP {resp.status_code}):\n"
                f"{resp.text[:300]}"
            )

        return resp.json().get("text", "").strip()

    def _escribir_texto(self, texto):
        """
        Escribe el texto donde este el cursor.
        Usa clipboard + Ctrl+V para soportar acentos y caracteres especiales.
        """
        try:
            try:
                clip_anterior = pyperclip.paste()
            except Exception:
                clip_anterior = ""

            pyperclip.copy(texto)
            time.sleep(0.06)
            keyboard.send("ctrl+v")
            time.sleep(0.35)

            try:
                pyperclip.copy(clip_anterior)
            except Exception:
                pass

        except Exception:
            # Fallback: caracter a caracter
            try:
                keyboard.write(texto, delay=0.01)
            except Exception as e2:
                self._mostrar_error(
                    "Texto transcripto",
                    f"No se pudo escribir automaticamente.\n\n"
                    f"Texto:\n{texto}\n\nError: {e2}"
                )

    # ------------------------------------------------------------------ #
    #  Ventanas modales (corren en el hilo tkinter)
    # ------------------------------------------------------------------ #

    def _abrir_ventana_config(self):
        """Ventana de configuracion: API key y hotkey."""
        ventana = tk.Toplevel(self.tk_root)
        ventana.title("Configurar - Dictado por voz")
        ventana.geometry("460x230")
        ventana.resizable(False, False)
        ventana.attributes("-topmost", True)
        ventana.grab_set()

        # Centrar en pantalla
        ventana.update_idletasks()
        sw = ventana.winfo_screenwidth()
        sh = ventana.winfo_screenheight()
        x  = (sw - 460) // 2
        y  = (sh - 230) // 2
        ventana.geometry(f"460x230+{x}+{y}")

        padx, pady = 12, 8

        tk.Label(ventana, text="Configuracion",
                 font=("Arial", 13, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(12, 6))

        # API Key
        tk.Label(ventana, text="API Key:", anchor="w",
                 font=("Arial", 10)).grid(
            row=1, column=0, padx=padx, pady=pady, sticky="w")
        entry_key = tk.Entry(ventana, width=36, show="*",
                             font=("Courier", 10))
        entry_key.insert(0, self.api_key)
        entry_key.grid(row=1, column=1, padx=5, sticky="w")

        # Atajo de teclado
        tk.Label(ventana, text="Atajo:", anchor="w",
                 font=("Arial", 10)).grid(
            row=2, column=0, padx=padx, pady=pady, sticky="w")
        entry_hk = tk.Entry(ventana, width=22, font=("Arial", 10))
        entry_hk.insert(0, self.hotkey)
        entry_hk.grid(row=2, column=1, sticky="w", padx=5)

        # Link
        tk.Label(ventana, text="Obtener key:", anchor="w",
                 font=("Arial", 10)).grid(
            row=3, column=0, padx=padx, pady=pady, sticky="w")
        lbl_link = tk.Label(
            ventana, text=URL_API_KEYS,
            fg="#1565C0", cursor="hand2",
            font=("Arial", 9, "underline")
        )
        lbl_link.grid(row=3, column=1, sticky="w", padx=5)
        lbl_link.bind("<Button-1>", lambda e: webbrowser.open(URL_API_KEYS))

        def guardar():
            nueva_key = entry_key.get().strip()
            nuevo_hk  = entry_hk.get().strip() or HOTKEY_DEFAULT
            if not nueva_key:
                messagebox.showerror("Error",
                                     "La API key no puede estar vacia.",
                                     parent=ventana)
                return
            try:
                cfg = guardar_config({
                    "openai_api_key": nueva_key,
                    "hotkey":        nuevo_hk
                })
            except Exception as e:
                messagebox.showerror("Error",
                                     f"No se pudo guardar:\n{e}",
                                     parent=ventana)
                return

            self.api_key = nueva_key
            self.config  = cfg

            if nuevo_hk != self.hotkey:
                try:
                    keyboard.remove_hotkey(self.hotkey)
                except Exception:
                    pass
                self.hotkey = nuevo_hk
                self._registrar_hotkey()

            ventana.destroy()
            self._mostrar_info("Configuracion guardada",
                               "Los cambios se guardaron correctamente.")

        tk.Button(
            ventana, text="Guardar",
            command=guardar,
            bg="#4CAF50", fg="white",
            font=("Arial", 11, "bold"),
            padx=12, pady=4
        ).grid(row=4, column=0, columnspan=2, pady=15)

    def _abrir_ventana_ayuda(self):
        """Ventana de ayuda rapida."""
        hk_display = self.hotkey.replace("space", "Espacio").upper()
        ventana    = tk.Toplevel(self.tk_root)
        ventana.title("Ayuda - Dictado por voz")
        ventana.geometry("400x340")
        ventana.resizable(False, False)
        ventana.attributes("-topmost", True)

        # Centrar
        ventana.update_idletasks()
        sw = ventana.winfo_screenwidth()
        sh = ventana.winfo_screenheight()
        ventana.geometry(f"400x340+{(sw-400)//2}+{(sh-340)//2}")

        texto = (
            f"Dictado por voz con Whisper\n"
            f"{'=' * 34}\n\n"
            f"Atajo actual: {hk_display}\n\n"
            "Como usar:\n"
            "  1. Coloca el cursor donde quieras escribir\n"
            "     (Word, Chrome, Notepad, Gmail, etc.)\n"
            f"  2. Presiona {hk_display} para INICIAR\n"
            "  3. Habla con claridad\n"
            f"  4. Presiona {hk_display} de nuevo para PARAR\n"
            "  5. El texto aparece donde estaba el cursor\n\n"
            "El icono del microfono cambia de color:\n"
            "  Verde oscuro = Listo\n"
            "  Rojo         = Grabando\n"
            "  Naranja      = Transcribiendo\n\n"
            f"Costo Whisper: ~$0.006 USD por minuto\n"
            "Ver uso: platform.openai.com/account/usage"
        )

        tk.Label(
            ventana, text=texto,
            font=("Courier", 10),
            justify="left",
            padx=15, pady=10
        ).pack(fill=tk.BOTH, expand=True)

        tk.Button(
            ventana, text="Cerrar",
            command=ventana.destroy,
            padx=10, pady=4
        ).pack(pady=8)

    def _abrir_ventana_acerca_de(self):
        """Ventana Acerca de con datos del autor."""
        ventana = tk.Toplevel(self.tk_root)
        ventana.title(f"Acerca de - {APP_NOMBRE}")
        ventana.geometry("400x370")
        ventana.resizable(False, False)
        ventana.attributes("-topmost", True)

        # Centrar en pantalla
        ventana.update_idletasks()
        sw = ventana.winfo_screenwidth()
        sh = ventana.winfo_screenheight()
        ventana.geometry(f"400x370+{(sw-400)//2}+{(sh-370)//2}")

        # Padding exterior
        frame_main = tk.Frame(ventana, padx=20, pady=15)
        frame_main.pack(fill=tk.BOTH, expand=True)

        # Titulo del programa
        tk.Label(
            frame_main,
            text=APP_NOMBRE,
            font=("Arial", 18, "bold"),
            anchor="center"
        ).pack(fill=tk.X)

        # Autor
        tk.Label(
            frame_main,
            text=f"por {APP_AUTOR}",
            font=("Arial", 10),
            fg="#555555",
            anchor="center"
        ).pack(fill=tk.X)

        # Version
        tk.Label(
            frame_main,
            text=f"Version {APP_VERSION}",
            font=("Arial", 9),
            fg="#888888",
            anchor="center"
        ).pack(fill=tk.X, pady=(0, 8))

        # Separador
        tk.Frame(frame_main, height=1, bg="#DDDDDD").pack(fill=tk.X, pady=6)

        # Descripcion
        tk.Label(
            frame_main,
            text="Transcripcion de voz con inteligencia artificial.\n"
                 "El texto aparece escrito donde este el cursor,\n"
                 "en cualquier programa de Windows.",
            font=("Arial", 10),
            fg="#333333",
            justify="center",
            anchor="center"
        ).pack(fill=tk.X, pady=4)

        # Separador
        tk.Frame(frame_main, height=1, bg="#DDDDDD").pack(fill=tk.X, pady=6)

        # Frame de contacto
        frame_contacto = tk.Frame(frame_main)
        frame_contacto.pack(fill=tk.X)

        # Email clickeable
        lbl_email = tk.Label(
            frame_contacto,
            text=APP_EMAIL,
            font=("Arial", 10, "underline"),
            fg="#1565C0",
            cursor="hand2"
        )
        lbl_email.pack()
        lbl_email.bind(
            "<Button-1>",
            lambda e: webbrowser.open(f"mailto:{APP_EMAIL}")
        )

        # Web clickeable
        lbl_web = tk.Label(
            frame_contacto,
            text=APP_WEB,
            font=("Arial", 10, "underline"),
            fg="#1565C0",
            cursor="hand2"
        )
        lbl_web.pack()
        lbl_web.bind(
            "<Button-1>",
            lambda e: webbrowser.open(f"https://{APP_WEB}")
        )

        # GitHub clickeable
        lbl_github = tk.Label(
            frame_contacto,
            text=APP_GITHUB,
            font=("Arial", 10, "underline"),
            fg="#1565C0",
            cursor="hand2"
        )
        lbl_github.pack()
        lbl_github.bind(
            "<Button-1>",
            lambda e: webbrowser.open(f"https://{APP_GITHUB}")
        )

        # Separador
        tk.Frame(frame_main, height=1, bg="#DDDDDD").pack(fill=tk.X, pady=6)

        # Nota de descarga
        tk.Label(
            frame_main,
            text="Para usar: solo descarga DictadoPorVoz.exe desde GitHub.\n"
                 "No necesitas instalar Python ni nada mas.",
            font=("Arial", 9),
            fg="#444444",
            justify="center",
            anchor="center"
        ).pack(fill=tk.X)

        # Separador
        tk.Frame(frame_main, height=1, bg="#DDDDDD").pack(fill=tk.X, pady=6)

        # Nota tecnica
        tk.Label(
            frame_main,
            text="Requiere cuenta en OpenAI con API key propia.",
            font=("Arial", 8),
            fg="#999999",
            anchor="center"
        ).pack(fill=tk.X)

        # Boton cerrar
        tk.Button(
            frame_main,
            text="Cerrar",
            command=ventana.destroy,
            padx=14, pady=4
        ).pack(pady=(10, 0))

    def _abrir_ventana_config_inicial(self, on_guardado):
        """
        Ventana de configuracion inicial (primera vez).
        Llama on_guardado(config) cuando el usuario guarda.
        """
        ventana = tk.Toplevel(self.tk_root)
        ventana.title("Dictado por voz - Configuracion inicial")
        ventana.resizable(False, False)
        ventana.attributes("-topmost", True)
        ventana.protocol("WM_DELETE_WINDOW", lambda: None)  # no se puede cerrar con X

        # Centrar
        ventana.update_idletasks()
        ancho, alto = 510, 360
        sw = ventana.winfo_screenwidth()
        sh = ventana.winfo_screenheight()
        ventana.geometry(f"{ancho}x{alto}+{(sw-ancho)//2}+{(sh-alto)//2}")

        pad = {"padx": 20, "pady": 6}

        tk.Label(
            ventana, text="Configuracion inicial",
            font=("Arial", 14, "bold")
        ).pack(pady=(15, 5))

        tk.Label(
            ventana,
            text="Necesitas una API key de OpenAI para usar Whisper.",
            font=("Arial", 10), wraplength=470, justify="left"
        ).pack(**pad)

        # API Key
        frame_key = tk.Frame(ventana)
        frame_key.pack(fill=tk.X, padx=20, pady=4)
        tk.Label(frame_key, text="API Key:", width=9, anchor="w",
                 font=("Arial", 10)).pack(side=tk.LEFT)
        entry_key = tk.Entry(frame_key, width=38, show="*",
                             font=("Courier", 10))
        entry_key.pack(side=tk.LEFT, padx=4)

        btn_ver = tk.Button(frame_key, text="Ver", width=5, font=("Arial", 9))
        btn_ver.pack(side=tk.LEFT)

        def toggle_ver():
            if entry_key.cget("show") == "*":
                entry_key.config(show="")
                btn_ver.config(text="Ocultar")
            else:
                entry_key.config(show="*")
                btn_ver.config(text="Ver")

        btn_ver.config(command=toggle_ver)

        # Hotkey
        frame_hk = tk.Frame(ventana)
        frame_hk.pack(fill=tk.X, padx=20, pady=4)
        tk.Label(frame_hk, text="Atajo:", width=9, anchor="w",
                 font=("Arial", 10)).pack(side=tk.LEFT)
        entry_hk = tk.Entry(frame_hk, width=22, font=("Arial", 10))
        entry_hk.insert(0, HOTKEY_DEFAULT)
        entry_hk.pack(side=tk.LEFT, padx=4)
        tk.Label(frame_hk, text="(ej: ctrl+alt+space, ctrl+shift+d)",
                 fg="gray", font=("Arial", 8)).pack(side=tk.LEFT)

        # Botones
        frame_btn = tk.Frame(ventana)
        frame_btn.pack(pady=12)

        def abrir_tutorial():
            webbrowser.open(URL_API_KEYS)
            messagebox.showinfo(
                "Como obtener API key",
                "Como obtener tu API key de OpenAI:\n\n"
                "1. El navegador se abrio en platform.openai.com/api-keys\n"
                "   (o entrar manualmente a esa direccion)\n\n"
                "2. Crear una cuenta si no tenes (es gratis)\n\n"
                "3. Hacer clic en 'Create new secret key'\n\n"
                "4. Darle un nombre (ej: 'Dictado por voz')\n\n"
                "5. Copiar la key que aparece (empieza con 'sk-...')\n"
                "   IMPORTANTE: solo se muestra una vez!\n\n"
                "6. Pegar la key en el campo 'API Key' de esta ventana\n\n"
                "Costo: ~$0.006 USD/min. Con $5 tenes +13hs de dictado.",
                parent=ventana
            )

        tk.Button(
            frame_btn, text="Como obtener API key?",
            command=abrir_tutorial,
            fg="#1565C0", cursor="hand2",
            font=("Arial", 10), relief=tk.FLAT,
            bg="#E3F2FD", padx=8, pady=4
        ).pack(side=tk.LEFT, padx=8)

        def guardar_inicial():
            key    = entry_key.get().strip()
            hotkey = entry_hk.get().strip() or HOTKEY_DEFAULT
            if not key:
                messagebox.showerror("Error",
                                     "Debes ingresar una API key.",
                                     parent=ventana)
                return
            if not key.startswith("sk-"):
                if not messagebox.askyesno(
                    "Advertencia",
                    "La API key no empieza con 'sk-'. Continuar de todas formas?",
                    parent=ventana
                ):
                    return
            try:
                cfg = guardar_config({"openai_api_key": key, "hotkey": hotkey})
            except Exception as e:
                messagebox.showerror("Error",
                                     f"No se pudo guardar:\n{e}",
                                     parent=ventana)
                return
            ventana.destroy()
            on_guardado(cfg)

        tk.Button(
            frame_btn, text="Guardar y continuar",
            command=guardar_inicial,
            bg="#4CAF50", fg="white",
            font=("Arial", 11, "bold"),
            padx=10, pady=4, cursor="hand2"
        ).pack(side=tk.LEFT, padx=8)

        tk.Label(
            ventana,
            text="Costo: ~$0.006 USD/minuto. Con $5 de credito tenes mas de 13 horas.",
            font=("Arial", 8), fg="gray", wraplength=470
        ).pack(pady=(0, 10))

    # ------------------------------------------------------------------ #
    #  Arranque y cierre
    # ------------------------------------------------------------------ #

    def run(self):
        """Inicia el icono en el system tray (bloquea el hilo principal)."""
        icono_img = crear_icono_microfono("listo")
        menu      = self._construir_menu()

        self.icono_tray = pystray.Icon(
            name=APP_NOMBRE,
            icon=icono_img,
            title=TOOLTIPS["listo"],
            menu=menu
        )
        self.icono_tray.run()

    def _cerrar(self):
        """Cierra la aplicacion limpiamente."""
        # Parar grabacion si estaba activa
        if self.grabando:
            self.grabando = False
            if self.hilo_grabacion and self.hilo_grabacion.is_alive():
                self.hilo_grabacion.join(timeout=1.5)
        # Liberar hotkeys
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        # Destruir indicador visual
        if self.indicador:
            try:
                self.indicador.destruir()
            except Exception:
                pass
        # Cerrar tkinter
        if self.tk_root:
            try:
                self.tk_root.quit()
            except Exception:
                pass
        # Cerrar icono del tray
        if self.icono_tray:
            self.icono_tray.stop()


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    config = cargar_config()

    if config is None:
        # Primera vez: mostrar formulario y esperar que el usuario guarde.
        # IMPORTANTE: pystray.run() debe correr en el hilo principal.
        # Usamos threading.Event como senial entre el hilo tkinter y el principal.
        app = DictadoApp({"openai_api_key": "", "hotkey": HOTKEY_DEFAULT})

        # El hilo tkinter activa este evento cuando el usuario guarda la config
        evento_listo = threading.Event()

        def on_config_inicial(cfg):
            # Corre en el hilo tkinter: SOLO actualiza datos y activa el evento.
            # No llama app.run() desde aqui (seria un error de threading).
            app.api_key = cfg.get("openai_api_key", "")
            app.hotkey  = cfg.get("hotkey", HOTKEY_DEFAULT)
            app.config  = cfg
            try:
                keyboard.unhook_all()
            except Exception:
                pass
            app._registrar_hotkey()
            evento_listo.set()   # senial al hilo principal: ya hay config

        # Mostrar el formulario en el hilo tkinter
        time.sleep(0.4)   # esperar a que el hilo tk este listo
        app._en_hilo_tk(
            lambda: app._abrir_ventana_config_inicial(on_config_inicial)
        )

        # Hilo principal espera bloqueado hasta que el usuario guarde
        evento_listo.wait()

        # Ahora app.run() corre en el hilo principal (correcto para pystray)
        app.run()

    else:
        # Ya tiene config: arrancar directo
        app = DictadoApp(config)
        app.run()


if __name__ == "__main__":
    main()
