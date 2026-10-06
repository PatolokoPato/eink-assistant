"""Ventana de control + icono en la bandeja del sistema.

Cerrar la ventana la oculta: el programa sigue en la bandeja actualizando la
E-Ink. Para salir del todo: menú del icono > Salir, o el botón Salir.

Hilos: tkinter solo se toca desde el hilo principal. El icono de la bandeja
(pystray) corre en su propio hilo y manda sus acciones por `_ui_queue`; la
pantalla la maneja DisplayController en otro hilo.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import queue
import sys
import threading
import tkinter as tk
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw, ImageOps, ImageTk

from device import list_serial_ports
from display import deco

from . import __version__, claude_desktop, startup
from .app_settings import APP_DIR, AppSettings
from .assistant import ASSISTANT
from .assistant_window import AssistantWindow
from .local_api import Handlers, LocalApi
from .controller import DisplayController, Status
from .hotkeys import MOD_ALT, MOD_CONTROL, VK_F1, VK_LEFT, VK_NEXT, VK_PRIOR, VK_RIGHT, GlobalHotkeys, Hotkey
from .views import VIEWS, cycle_view, get_view

log = logging.getLogger(__name__)

AUTO_PORT = "Automático"
WIFI_PORT = "Wi-Fi (eink.local)"
WIFI_TARGET = "wifi:eink.local"  # valor guardado en settings.port
POLL_MS = 200


def make_icon(size: int = 64) -> Image.Image:
    """Cuadrado negro redondeado con una estrella blanca de cuatro puntas."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, size - 3, size - 3], radius=size // 5, fill=(0, 0, 0, 255))
    deco.sparkle(d, size / 2, size / 2, size * 0.36, fill=(255, 255, 255, 255))
    return img


def write_icon_file() -> Path:
    """Guarda el icono como .ico (para los accesos directos) y devuelve su ruta."""
    path = startup.ICON_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    make_icon(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    return path


def _set_app_id() -> None:
    """Identidad propia en la barra de tareas: sin esto Windows la agrupa como
    pythonw.exe y muestra el icono de Python en vez del de la ventana."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EInkAssistant.App")
        except (AttributeError, OSError):
            pass


def _single_instance() -> bool:
    """True si somos la única instancia (dos programas no pueden compartir el COM)."""
    if sys.platform != "win32":
        return True
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\EInkAssistantSingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


class App:
    def __init__(self, root: tk.Tk, settings: AppSettings, *, minimized: bool) -> None:
        self.root = root
        self.settings = settings
        self._ui_queue: "queue.Queue[callable]" = queue.Queue()
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_token = 0
        self._last_status: Status | None = None

        self.ctrl = DisplayController(settings.port, view_id=settings.view_id, auto=settings.auto,
                                      interval_min=settings.interval_min, invert=settings.invert)

        root.title("E-Ink Assistant")
        root.resizable(False, False)
        # Varios tamaños: Windows usa el pequeño en la ventana y el grande en la barra de tareas.
        self._icon_photos = [ImageTk.PhotoImage(make_icon(s)) for s in (16, 32, 48, 256)]
        root.iconphoto(True, *self._icon_photos)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        self._build()
        self.assistant_win = AssistantWindow(root, post=self._ui_queue.put, show_on_eink=self._activate_view)

        self.tray = self._build_tray()
        self.tray.run_detached()
        self.hotkeys: GlobalHotkeys | None = None
        if settings.hotkeys:
            self._start_hotkeys()

        self.ctrl.start()
        self.api: LocalApi | None = None
        try:
            self.api = LocalApi(Handlers(show=self._api_show, page=self._api_page, home=self._api_home,
                                         status=self._api_status))
            self.api.start()
        except OSError as e:
            log.warning("No se pudo abrir la API local (¿puerto ocupado?): %s", e)
        if settings.update_on_start:
            self.ctrl.show()
        self._select_view(settings.view_id)
        if minimized:
            root.withdraw()
        root.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------ ventana
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=10)
        main.grid(sticky="nsew")

        # Columna izquierda: vistas
        left = ttk.LabelFrame(main, text="Vistas", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.view_list = tk.Listbox(left, height=8, width=26, activestyle="none", exportselection=False,
                                    font=("Segoe UI", 10))
        self.view_list.grid(row=0, column=0, sticky="nsew")
        self.view_list.bind("<<ListboxSelect>>", lambda e: self._on_view_selected())
        self.view_desc = ttk.Label(left, wraplength=200, foreground="#555")
        self.view_desc.grid(row=1, column=0, sticky="w", pady=(6, 6))
        ttk.Button(left, text="Mostrar en la E-Ink", command=self._show_selected).grid(row=2, column=0, sticky="ew")
        ttk.Button(left, text="Recargar vista previa", command=self._on_view_selected).grid(
            row=3, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(left, text="✦ Abrir asistente…", command=lambda: self.assistant_win.open()).grid(
            row=4, column=0, sticky="ew", pady=(14, 0))
        self.var_hotkeys = tk.BooleanVar(value=self.settings.hotkeys)
        ttk.Checkbutton(left, text="Atajos de teclado", variable=self.var_hotkeys,
                        command=self._on_hotkeys).grid(row=5, column=0, sticky="w", pady=(14, 0))
        self.lbl_hotkeys = ttk.Label(left, foreground="#555", justify="left", text=(
            "Ctrl+Alt+← →   vista anterior/siguiente\n"
            "Ctrl+Alt+F1…F4   ir a una vista\n"
            "Ctrl+Alt+Re Pág/Av Pág   página del asistente"))
        self.lbl_hotkeys.grid(row=6, column=0, sticky="w")

        # Centro: vista previa a tamaño real
        mid = ttk.LabelFrame(main, text="Vista previa", padding=8)
        mid.grid(row=0, column=1, sticky="n")
        self.canvas = tk.Canvas(mid, width=400, height=300, bg="white", highlightthickness=1,
                                highlightbackground="#999")
        self.canvas.grid(row=0, column=0)

        # Derecha: estado y opciones
        right = ttk.Frame(main)
        right.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        st = ttk.LabelFrame(right, text="Estado", padding=8)
        st.grid(row=0, column=0, sticky="ew")
        self.lbl_conn = ttk.Label(st, font=("Segoe UI", 10, "bold"))
        self.lbl_conn.grid(row=0, column=0, sticky="w")
        self.lbl_busy = ttk.Label(st)
        self.lbl_busy.grid(row=1, column=0, sticky="w")
        self.lbl_last = ttk.Label(st)
        self.lbl_last.grid(row=2, column=0, sticky="w")
        self.lbl_next = ttk.Label(st)
        self.lbl_next.grid(row=3, column=0, sticky="w")
        self.lbl_error = ttk.Label(st, foreground="#b00020", wraplength=230)
        self.lbl_error.grid(row=4, column=0, sticky="w")

        act = ttk.LabelFrame(right, text="Pantalla", padding=8)
        act.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(act, text="Actualizar ahora", command=lambda: self.ctrl.show()).grid(
            row=0, column=0, sticky="ew", **{"pady": 2})
        ttk.Button(act, text="Refresco completo (limpia restos)", command=lambda: self.ctrl.show(full=True)).grid(
            row=1, column=0, sticky="ew", pady=2)
        ttk.Button(act, text="Borrar pantalla", command=self._confirm_clear).grid(row=2, column=0, sticky="ew", pady=2)
        act.columnconfigure(0, weight=1)

        opt = ttk.LabelFrame(right, text="Opciones", padding=8)
        opt.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.var_auto = tk.BooleanVar(value=self.settings.auto)
        self.var_interval = tk.IntVar(value=self.settings.interval_min)
        row = ttk.Frame(opt)
        row.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(row, text="Actualizar cada", variable=self.var_auto, command=self._on_auto).pack(side="left")
        spin = ttk.Spinbox(row, from_=1, to=120, width=4, textvariable=self.var_interval, command=self._on_auto)
        spin.pack(side="left", padx=4)
        spin.bind("<Return>", lambda e: self._on_auto())
        spin.bind("<FocusOut>", lambda e: self._on_auto())
        ttk.Label(row, text="min").pack(side="left")

        self.var_on_start = tk.BooleanVar(value=self.settings.update_on_start)
        ttk.Checkbutton(opt, text="Actualizar al abrir el programa", variable=self.var_on_start,
                        command=self._on_options).grid(row=1, column=0, sticky="w")
        self.var_startup = tk.BooleanVar(value=startup.is_enabled())
        ttk.Checkbutton(opt, text="Iniciar con Windows (en la bandeja)", variable=self.var_startup,
                        command=self._on_startup).grid(row=2, column=0, sticky="w")
        self.var_invert = tk.BooleanVar(value=self.settings.invert)
        ttk.Checkbutton(opt, text="Blanco sobre negro (invertir)", variable=self.var_invert,
                        command=self._on_invert).grid(row=3, column=0, sticky="w")
        self.var_mcp_always = tk.BooleanVar(value=self.settings.mcp_always)
        ttk.Checkbutton(opt, text="Claude Desktop envía todas sus respuestas\n(se aplica al reiniciar Claude)",
                        variable=self.var_mcp_always, command=self._on_options).grid(row=4, column=0, sticky="w")

        port_row = ttk.Frame(opt)
        port_row.grid(row=5, column=0, sticky="w", pady=(6, 0))
        ttk.Label(port_row, text="Conexión:").pack(side="left")
        port = self.settings.port
        self.var_port = tk.StringVar(value=WIFI_PORT if port == WIFI_TARGET else port or AUTO_PORT)
        self.cmb_port = ttk.Combobox(port_row, textvariable=self.var_port, width=17, state="readonly")
        self.cmb_port.pack(side="left", padx=4)
        self.cmb_port.bind("<<ComboboxSelected>>", lambda e: self._on_port())
        ttk.Button(port_row, text="↻", width=3, command=self._refresh_ports).pack(side="left")
        self._refresh_ports()
        ttk.Button(opt, text="Crear acceso directo en el escritorio", command=self._desktop_shortcut).grid(
            row=6, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(opt, text="Conectar con Claude Desktop…",
                   command=lambda: claude_desktop.register_interactive(self.root)).grid(
            row=7, column=0, sticky="ew", pady=(4, 0))

        foot = ttk.Frame(main)
        foot.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Label(foot, text="Al cerrar la ventana, el programa sigue en la bandeja del sistema.",
                  foreground="#555").pack(side="left")
        ttk.Button(foot, text="Salir", command=self.quit).pack(side="right")

        for v in VIEWS:
            self.view_list.insert("end", v.name)

    def _build_tray(self) -> pystray.Icon:
        def ui(fn):
            return lambda icon, item: self._ui_queue.put(fn)

        def view_item(view_id: str, name: str) -> pystray.MenuItem:
            return pystray.MenuItem(name, ui(lambda: self._activate_view(view_id)), radio=True,
                                    checked=lambda item: self.ctrl.status.view_id == view_id)

        menu = pystray.Menu(
            pystray.MenuItem("Abrir", ui(self.show_window), default=True),
            pystray.MenuItem("Preguntar al asistente…", ui(lambda: self.assistant_win.open())),
            pystray.MenuItem("Actualizar ahora", ui(lambda: self.ctrl.show())),
            pystray.MenuItem("Refresco completo", ui(lambda: self.ctrl.show(full=True))),
            pystray.MenuItem("Vista", pystray.Menu(*(view_item(v.id, v.name) for v in VIEWS))),
            pystray.MenuItem("Actualización automática", ui(self._toggle_auto),
                             checked=lambda item: self.ctrl.status.auto),
            pystray.MenuItem("Blanco sobre negro", ui(self._toggle_invert),
                             checked=lambda item: self.ctrl.status.invert),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", ui(self.quit)),
        )
        return pystray.Icon("eink-assistant", make_icon(64), "E-Ink Assistant", menu)

    # ------------------------------------------------------------- acciones UI
    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()

    # ---------------------------------------------- API local (hilo del servidor)
    def _api_show(self, text: str, question: str) -> int:
        pages = ASSISTANT.show_text(text, question)
        self._ui_queue.put(lambda: (self.assistant_win.note_external(text, question),
                                    self._activate_view("assistant")))
        return pages

    # ------------------------------------------------- atajos (hilo de los atajos)
    def _start_hotkeys(self) -> None:
        def ui(fn):
            return lambda: self._ui_queue.put(fn)

        mods = MOD_CONTROL | MOD_ALT
        keys = [
            Hotkey("Ctrl+Alt+→", mods, VK_RIGHT, ui(lambda: self._step_view(1))),
            Hotkey("Ctrl+Alt+←", mods, VK_LEFT, ui(lambda: self._step_view(-1))),
            Hotkey("Ctrl+Alt+Av Pág", mods, VK_NEXT, ui(lambda: self._step_page(1))),
            Hotkey("Ctrl+Alt+Re Pág", mods, VK_PRIOR, ui(lambda: self._step_page(-1))),
        ]
        for i, v in enumerate(VIEWS[:12]):
            keys.append(Hotkey(f"Ctrl+Alt+F{i + 1}", mods, VK_F1 + i,
                               ui(lambda vid=v.id: self._activate_view(vid))))
        self.hotkeys = GlobalHotkeys(keys)
        failed = self.hotkeys.start()
        self.lbl_hotkeys.configure(foreground="#555")
        if failed:
            self.lbl_hotkeys.configure(foreground="#b00020")
            messagebox.showwarning("Atajos de teclado", "Otro programa ya usa estos atajos, no funcionarán:\n"
                                   + "\n".join(failed), parent=self.root)

    def _stop_hotkeys(self) -> None:
        if self.hotkeys:
            self.hotkeys.stop()
            self.hotkeys = None

    def _on_hotkeys(self) -> None:
        self.settings.hotkeys = self.var_hotkeys.get()
        self._save()
        self._stop_hotkeys()
        if self.settings.hotkeys:
            self._start_hotkeys()

    def _step_view(self, delta: int) -> None:
        # Desde la vista elegida en la lista (no la del controlador): así dos
        # pulsaciones rápidas avanzan dos vistas aunque la E-Ink siga refrescando.
        self._activate_view(cycle_view(self._selected_view_id(), delta))

    def _step_page(self, delta: int) -> None:
        if ASSISTANT.go(delta):
            self.assistant_win.refresh_pages()
            self._activate_view("assistant")

    def _api_page(self, delta: int) -> tuple[int, int]:
        if ASSISTANT.go(delta):
            self._ui_queue.put(lambda: (self.assistant_win.refresh_pages(), self._activate_view("assistant")))
        return ASSISTANT.page + 1, ASSISTANT.page_count

    def _api_home(self) -> None:
        self._ui_queue.put(lambda: self._activate_view("home"))

    def _api_status(self) -> dict:
        st = self.ctrl.status
        return {"connected": st.connected, "view": st.view_id, "busy": st.busy, "last_error": st.last_error,
                "page": ASSISTANT.page + 1, "pages": ASSISTANT.page_count}

    def quit(self) -> None:
        self._save()
        if self.api:
            self.api.stop()
        self.tray.stop()
        self._stop_hotkeys()
        self.root.withdraw()
        # Si está refrescando, esperar a que termine para no cortar una trama a medias.
        threading.Thread(target=lambda: (self.ctrl.stop(), self._ui_queue.put(self.root.destroy)),
                         daemon=True).start()

    def _save(self) -> None:
        try:
            self.settings.save()
        except OSError as e:
            log.warning("No se pudieron guardar las preferencias: %s", e)

    def _select_view(self, view_id: str) -> None:
        idx = next((i for i, v in enumerate(VIEWS) if v.id == view_id), 0)
        self.view_list.selection_clear(0, "end")
        self.view_list.selection_set(idx)
        self._on_view_selected()

    def _selected_view_id(self) -> str:
        sel = self.view_list.curselection()
        return VIEWS[sel[0]].id if sel else self.settings.view_id

    def _on_view_selected(self) -> None:
        view = get_view(self._selected_view_id())
        self.view_desc.configure(text=view.description)
        self._preview_token += 1
        token = self._preview_token
        self.canvas.delete("all")
        self.canvas.create_text(200, 150, text="Generando…", fill="#777", font=("Segoe UI", 11))

        def work():
            try:
                img = view.build()
            except Exception as e:  # noqa: BLE001
                log.exception("Error generando la vista previa")
                self._ui_queue.put(lambda: self._show_preview_error(token, e))
                return
            self._ui_queue.put(lambda: self._show_preview(token, img))

        threading.Thread(target=work, name="preview", daemon=True).start()

    def _show_preview(self, token: int, img: Image.Image) -> None:
        if token != self._preview_token:
            return  # ya se eligió otra vista
        img = img.convert("L")
        if self.settings.invert:
            img = ImageOps.invert(img)
        self._preview_photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._preview_photo, anchor="nw")

    def _show_preview_error(self, token: int, e: Exception) -> None:
        if token == self._preview_token:
            self.canvas.delete("all")
            self.canvas.create_text(200, 150, text=f"Error: {e}", fill="#b00020", width=360)

    def _activate_view(self, view_id: str) -> None:
        # Solo se recuerdan las vistas "vivas": al reabrir el programa no tiene
        # sentido volver a una respuesta del asistente que ya no existe.
        if get_view(view_id).auto_refresh:
            self.settings.view_id = view_id
            self._save()
        self._select_view(view_id)
        self.ctrl.show(view_id)

    def _show_selected(self) -> None:
        self._activate_view(self._selected_view_id())

    def _confirm_clear(self) -> None:
        if messagebox.askyesno("Borrar pantalla", "¿Dejar la E-Ink en blanco?", parent=self.root):
            self.ctrl.clear()

    def _on_auto(self) -> None:
        try:
            interval = max(1, min(120, int(self.var_interval.get())))
        except (tk.TclError, ValueError):
            interval = self.settings.interval_min
        self.settings.auto, self.settings.interval_min = self.var_auto.get(), interval
        self._save()
        self.ctrl.set_auto(self.settings.auto, interval)

    def _toggle_auto(self) -> None:
        self.var_auto.set(not self.var_auto.get())
        self._on_auto()

    def _on_invert(self) -> None:
        self.settings.invert = self.var_invert.get()
        self._save()
        self.ctrl.set_invert(self.settings.invert)
        self._on_view_selected()  # la vista previa también

    def _toggle_invert(self) -> None:
        self.var_invert.set(not self.var_invert.get())
        self._on_invert()

    def _on_options(self) -> None:
        self.settings.update_on_start = self.var_on_start.get()
        self.settings.mcp_always = self.var_mcp_always.get()
        self._save()

    def _on_startup(self) -> None:
        try:
            startup.enable() if self.var_startup.get() else startup.disable()
        except Exception as e:  # noqa: BLE001
            log.exception("No se pudo cambiar el inicio con Windows")
            messagebox.showerror("Iniciar con Windows", f"No se pudo cambiar: {e}", parent=self.root)
        self.var_startup.set(startup.is_enabled())

    def _desktop_shortcut(self) -> None:
        try:
            path = startup.create_desktop_shortcut()
        except Exception as e:  # noqa: BLE001
            log.exception("No se pudo crear el acceso directo")
            messagebox.showerror("Acceso directo", f"No se pudo crear: {e}", parent=self.root)
            return
        messagebox.showinfo("Acceso directo", f"Creado en:\n{path}", parent=self.root)

    def _refresh_ports(self) -> None:
        ports = [dev for dev, _ in list_serial_ports()]
        current = self.var_port.get()
        values = [AUTO_PORT, WIFI_PORT, *ports]
        if current not in values:
            values.append(current)
        self.cmb_port["values"] = values

    def _on_port(self) -> None:
        value = self.var_port.get()
        self.settings.port = {AUTO_PORT: None, WIFI_PORT: WIFI_TARGET}.get(value, value)
        self._save()
        self.ctrl.set_port(self.settings.port)

    # ----------------------------------------------------------------- sondeo
    def _poll(self) -> None:
        while True:
            try:
                self._ui_queue.get_nowait()()
            except queue.Empty:
                break
        st = self.ctrl.status
        if st != self._last_status:
            self._render_status(st)
            self._last_status = st
        self.root.after(POLL_MS, self._poll)

    def _render_status(self, st: Status) -> None:
        if st.connected:
            self.lbl_conn.configure(text=f"● Conectada ({(st.transport or '').removeprefix('usb:').replace('wifi:', 'Wi-Fi ')})",
                                    foreground="#1b7f3b")
        else:
            self.lbl_conn.configure(text="○ Desconectada", foreground="#777")
        self.lbl_busy.configure(text=st.busy or "En espera")
        if st.last_update:
            dur = f" ({st.last_duration:.0f} s)" if st.last_duration else ""
            self.lbl_last.configure(text=f"Última actualización: {st.last_update:%H:%M}{dur}")
        else:
            self.lbl_last.configure(text="Última actualización: —")
        nxt = f"{st.next_auto:%H:%M}" if st.auto and st.next_auto else "desactivada"
        self.lbl_next.configure(text=f"Próxima automática: {nxt}")
        self.lbl_error.configure(text=f"⚠ {st.last_error}" if st.last_error else "")

        # Vista activa marcada en la lista
        for i, v in enumerate(VIEWS):
            mark = "★ " if v.id == st.view_id else "    "
            if self.view_list.get(i) != mark + v.name:
                sel = self.view_list.curselection()
                self.view_list.delete(i)
                self.view_list.insert(i, mark + v.name)
                if sel:
                    self.view_list.selection_set(sel[0])

        state = "conectada" if st.connected else "desconectada"
        self.tray.title = f"E-Ink Assistant — {state}" + (f"\n{st.busy}" if st.busy else "")
        self.tray.update_menu()


def _setup_logging() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(APP_DIR / "app.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E-Ink Assistant: ventana + icono en la bandeja")
    ap.add_argument("--minimized", action="store_true", help="arrancar solo en la bandeja")
    ap.add_argument("--register-mcp", action="store_true",
                    help="registrar el servidor MCP en Claude Desktop y salir (lo usa el instalador)")
    ap.add_argument("--version", action="version", version=f"E-Ink Assistant {__version__}")
    args = ap.parse_args(argv)

    _setup_logging()
    _set_app_id()  # antes de crear cualquier ventana
    if args.register_mcp:
        root = tk.Tk()
        root.withdraw()
        root.iconphoto(True, ImageTk.PhotoImage(make_icon(32)))
        ok = claude_desktop.register_interactive(root)
        root.destroy()
        return 0 if ok else 1
    if not _single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("E-Ink Assistant", "El programa ya está abierto: búscalo en la bandeja del sistema.")
        return 0

    try:
        write_icon_file()
    except OSError as e:
        log.warning("No se pudo guardar el icono: %s", e)

    # Nítido en pantallas con escalado (125 %, 150 %...)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass

    root = tk.Tk()
    App(root, AppSettings.load(), minimized=args.minimized)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
