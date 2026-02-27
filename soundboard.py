#!/usr/bin/env python3
"""
maiNboard - Linux Soundboard
Audio-Routing-Architektur:

  Echtes Mikrofon (UR22mkII)  ──loopback──►  maiNboard_sink (Virtual Sink)
                                                       │
  Soundboard-mpv ─────────────────────────►  maiNboard_sink
                                                       │
                                              maiNboard_sink.monitor
                                                       │
                                              Discord / TS3 (hört Stimme + Sounds)

  Soundboard-mpv ─────────────────────────►  Echte Lautsprecher   (lokal mithören)
"""

import sys
import os
import json
import shutil
import subprocess
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout,
    QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QFileDialog, QMenu, QSizePolicy,
    QMessageBox, QInputDialog, QCheckBox, QFrame, QComboBox,
    QDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QAction, QKeySequence, QIcon

SCRIPT_DIR  = Path(__file__).parent
SOUNDS_DIR  = SCRIPT_DIR / "sounds"
CONFIG_FILE = SCRIPT_DIR / "config.json"
SINK_NAME       = "maiNboard_sink"
MIC_SOURCE_NAME = "maiNboard_mic"
ROWS, COLS  = 4, 6


# ── Config ─────────────────────────────────────────────────────────────────────
class Config:
    _defaults = {
        "buttons": {}, "volume": 80, "local_monitor": True,
        "mic_source": "", "mic_gain": 100, "overdrive": 1,
        "output_sink": "", "hotkeys": {},
    }

    def __init__(self):
        self.data = dict(self._defaults)
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                self.data = {**self._defaults, **json.loads(CONFIG_FILE.read_text())}
            except Exception:
                pass

    def save(self):
        CONFIG_FILE.write_text(json.dumps(self.data, indent=2))

    def get_button(self, idx: int) -> dict:
        return self.data["buttons"].get(str(idx), {"path": "", "label": f"Sound {idx + 1}"})

    def set_button(self, idx: int, path: str, label: str):
        self.data["buttons"][str(idx)] = {"path": path, "label": label}
        self.save()

    def clear_button(self, idx: int):
        self.data["buttons"].pop(str(idx), None)
        self.save()

    def get_hotkey(self, action_id: str) -> str:
        return self.data.get("hotkeys", {}).get(action_id, "")

    def set_hotkey(self, action_id: str, key_str: str):
        if "hotkeys" not in self.data:
            self.data["hotkeys"] = {}
        if key_str:
            self.data["hotkeys"][action_id] = key_str
        else:
            self.data["hotkeys"].pop(action_id, None)
        self.save()

    @property
    def volume(self) -> int:
        return self.data.get("volume", 80)

    @volume.setter
    def volume(self, v: int):
        self.data["volume"] = v
        self.save()

    @property
    def local_monitor(self) -> bool:
        return self.data.get("local_monitor", True)

    @local_monitor.setter
    def local_monitor(self, v: bool):
        self.data["local_monitor"] = v
        self.save()

    @property
    def mic_source(self) -> str:
        return self.data.get("mic_source", "")

    @mic_source.setter
    def mic_source(self, v: str):
        self.data["mic_source"] = v
        self.save()

    @property
    def mic_gain(self) -> int:
        return self.data.get("mic_gain", 100)

    @mic_gain.setter
    def mic_gain(self, v: int):
        self.data["mic_gain"] = v
        self.save()

    @property
    def overdrive(self) -> int:
        return self.data.get("overdrive", 1)

    @overdrive.setter
    def overdrive(self, v: int):
        self.data["overdrive"] = v
        self.save()

    @property
    def output_sink(self) -> str:
        return self.data.get("output_sink", "")

    @output_sink.setter
    def output_sink(self, v: str):
        self.data["output_sink"] = v
        self.save()


# ── Hotkey Dialog ───────────────────────────────────────────────────────────────
class HotkeyDialog(QDialog):
    """Dialog zum Aufzeichnen eines Tastendrucks als Hotkey."""

    _QT_KEY_MAP = {
        Qt.Key.Key_F1: "f1",   Qt.Key.Key_F2: "f2",   Qt.Key.Key_F3: "f3",
        Qt.Key.Key_F4: "f4",   Qt.Key.Key_F5: "f5",   Qt.Key.Key_F6: "f6",
        Qt.Key.Key_F7: "f7",   Qt.Key.Key_F8: "f8",   Qt.Key.Key_F9: "f9",
        Qt.Key.Key_F10: "f10", Qt.Key.Key_F11: "f11", Qt.Key.Key_F12: "f12",
        Qt.Key.Key_Space:  "space",
        Qt.Key.Key_Return: "enter",
        Qt.Key.Key_Enter:  "enter",
        Qt.Key.Key_Tab:    "tab",
        Qt.Key.Key_Delete: "delete",
        Qt.Key.Key_Left:   "left",
        Qt.Key.Key_Right:  "right",
        Qt.Key.Key_Up:     "up",
        Qt.Key.Key_Down:   "down",
    }

    def __init__(self, parent=None, current_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Hotkey festlegen")
        self.setModal(True)
        self.setFixedSize(340, 160)
        self._result_key = ""
        self._accepted = False

        self.setStyleSheet("""
            QDialog { background: #1e1e38; color: #d0d0f8; }
            QLabel { color: #d0d0f8; }
            QPushButton {
                background: #252540; color: #d0d0f8;
                border: 1px solid #404070; border-radius: 5px; padding: 4px 12px;
            }
            QPushButton:hover { background: #303060; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        self.lbl_prompt = QLabel("Drücke eine Taste …")
        self.lbl_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont()
        f.setPointSize(13)
        self.lbl_prompt.setFont(f)
        layout.addWidget(self.lbl_prompt)

        if current_key:
            lbl_cur = QLabel(f"Aktuell: [{current_key.upper()}]")
            lbl_cur.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_cur.setStyleSheet("color: #8888cc; font-size: 11px;")
            layout.addWidget(lbl_cur)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_remove = QPushButton("Entfernen")
        btn_remove.setToolTip("Hotkey löschen")
        btn_remove.clicked.connect(self._remove)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def keyPressEvent(self, event):
        key  = event.key()
        mods = event.modifiers()

        # Escape always cancels
        if key == Qt.Key.Key_Escape:
            self.reject()
            return

        # Skip bare modifier key presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift,
                   Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            return

        key_str = self._qt_key_to_str(key)
        if not key_str:
            return

        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mods & Qt.KeyboardModifier.KeypadModifier:
            parts.append("kp_" + key_str)
        else:
            parts.append(key_str)

        self._result_key = "+".join(parts)
        self._accepted = True
        self.accept()

    def _qt_key_to_str(self, key) -> str:
        if key in self._QT_KEY_MAP:
            return self._QT_KEY_MAP[key]
        kv = key.value if hasattr(key, "value") else int(key)
        if 65 <= kv <= 90:    # A–Z (Qt stores uppercase)
            return chr(kv + 32)
        if 48 <= kv <= 57:    # 0–9
            return chr(kv)
        return ""

    def _remove(self):
        self._result_key = ""
        self._accepted = True
        self.accept()

    @classmethod
    def get_hotkey(cls, parent, current_key: str = "") -> tuple[bool, str]:
        dlg = cls(parent, current_key)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg._accepted:
            return True, dlg._result_key
        return False, ""


# ── Hotkey Manager ──────────────────────────────────────────────────────────────
class HotkeyManager(QThread):
    """Globaler Keyboard-Listener via pynput. Läuft im Hintergrund."""

    hotkey_triggered = pyqtSignal(str)   # action_id

    def __init__(self):
        super().__init__()
        self._hotkeys: dict[str, str] = {}
        self._lock     = threading.Lock()
        self._listener = None
        self._modifiers: set[str] = set()

    def update_hotkeys(self, hotkeys: dict):
        with self._lock:
            self._hotkeys = dict(hotkeys)

    def run(self):
        try:
            from pynput import keyboard as kb
        except ImportError:
            return   # graceful fallback – pynput not installed

        # Build modifier map (safe against missing attributes)
        _MOD_MAP: dict = {}
        for attr, name in [
            ("ctrl",    "ctrl"), ("ctrl_l",  "ctrl"), ("ctrl_r",  "ctrl"),
            ("alt",     "alt"),  ("alt_l",   "alt"),  ("alt_r",   "alt"),
            ("alt_gr",  "alt"),
            ("shift",   "shift"),("shift_l", "shift"),("shift_r", "shift"),
        ]:
            if hasattr(kb.Key, attr):
                _MOD_MAP[getattr(kb.Key, attr)] = name

        # Build special-key map
        _KEY_MAP: dict = {}
        for attr, name in [
            ("f1","f1"),("f2","f2"),("f3","f3"),("f4","f4"),
            ("f5","f5"),("f6","f6"),("f7","f7"),("f8","f8"),
            ("f9","f9"),("f10","f10"),("f11","f11"),("f12","f12"),
            ("space","space"),("enter","enter"),("tab","tab"),
            ("delete","delete"),
            ("left","left"),("right","right"),("up","up"),("down","down"),
        ]:
            if hasattr(kb.Key, attr):
                _KEY_MAP[getattr(kb.Key, attr)] = name

        def on_press(key):
            mod = _MOD_MAP.get(key)
            if mod:
                self._modifiers.add(mod)
                return

            key_str = _KEY_MAP.get(key, "")
            if not key_str:
                # Character keys
                try:
                    char = key.char
                    if char and char.lower().isalnum():
                        key_str = char.lower()
                except AttributeError:
                    pass
            if not key_str:
                return

            mods = sorted(self._modifiers)
            full = "+".join(mods + [key_str]) if mods else key_str

            with self._lock:
                for action_id, hotkey in self._hotkeys.items():
                    if hotkey == full:
                        self.hotkey_triggered.emit(action_id)

        def on_release(key):
            mod = _MOD_MAP.get(key)
            if mod:
                self._modifiers.discard(mod)

        try:
            with kb.Listener(on_press=on_press, on_release=on_release) as listener:
                self._listener = listener
                listener.join()
        except Exception:
            pass

    def stop_listener(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        self.quit()
        self.wait(2000)


# ── Audio player thread ─────────────────────────────────────────────────────────
class AudioPlayer(QThread):
    """
    Spielt einen Sound gleichzeitig in den Virtual Sink UND lokal ab.

    Routing-Strategie:
      Für jeden benannten Sink:  ffmpeg → paplay --device <sink>
        (identisch zum funktionierenden Mic-Loopback-Routing)
      Für Standard-Ausgabe (kein Sink):  mpv direkt
    """
    sig_started = pyqtSignal(int)
    sig_stopped = pyqtSignal(int)

    def __init__(self, btn_idx: int, path: str,
                 sink: str | None, local_sink: str | None, volume: int, overdrive: int = 1):
        super().__init__()
        self.btn_idx    = btn_idx
        self.path       = path
        self.sink       = sink
        self.local_sink = local_sink
        self.volume     = volume
        self.overdrive  = overdrive
        self._procs: list[subprocess.Popen] = []

    def _af_filter(self) -> str:
        """ffmpeg -af Filterkette: Lautstärke + optionales Hard-Clipping.

        Overdrive-Prinzip: Volume wird x-fach geboosted, bei der Konvertierung
        nach s16le clippt ffmpeg automatisch bei ±32767 → Hard-Distortion.
        """
        vol = self.volume / 100.0
        total = vol * self.overdrive
        return f"volume={total}"

    def _spawn_to_sink(self, sink_name: str) -> list[subprocess.Popen]:
        """ffmpeg | paplay –– zuverlässigstes PulseAudio-Routing."""
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-i", self.path,
             "-af", self._af_filter(),
             "-f", "s16le", "-ar", "48000", "-ac", "2",
             "-loglevel", "quiet", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        paplay = subprocess.Popen(
            ["paplay", "--device", sink_name, "--raw",
             "--format=s16le", "--rate=48000", "--channels=2"],
            stdin=ffmpeg.stdout,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        ffmpeg.stdout.close()   # Pipe-Ende im Parent schließen
        return [ffmpeg, paplay]

    def _spawn_to_default(self) -> list[subprocess.Popen]:
        """ffmpeg | paplay → Standard-Ausgabe (auch mit Overdrive-Support)."""
        default_sink = subprocess.run(
            ["pactl", "get-default-sink"], capture_output=True, text=True
        ).stdout.strip()
        if default_sink:
            return self._spawn_to_sink(default_sink)
        # Fallback ohne Sink-Angabe
        p = subprocess.Popen(
            ["ffmpeg", "-i", self.path, "-af", self._af_filter(),
             "-f", "s16le", "-ar", "48000", "-ac", "2", "-loglevel", "quiet", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        p2 = subprocess.Popen(
            ["paplay", "--raw", "--format=s16le", "--rate=48000", "--channels=2"],
            stdin=p.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        p.stdout.close()
        return [p, p2]

    def run(self):
        self.sig_started.emit(self.btn_idx)
        self._procs = []

        try:
            if self.sink:
                self._procs.extend(self._spawn_to_sink(self.sink))
            if self.local_sink:
                self._procs.extend(self._spawn_to_sink(self.local_sink))
            if not self.sink and not self.local_sink:
                self._procs.extend(self._spawn_to_default())
        except Exception:
            pass

        for p in self._procs:
            try:
                p.wait()
            except Exception:
                pass

        self.sig_stopped.emit(self.btn_idx)

    def stop(self):
        for p in self._procs:
            if p.poll() is None:
                p.terminate()


# ── Sound button ───────────────────────────────────────────────────────────────
class SoundButton(QPushButton):
    triggered_sound = pyqtSignal(int)
    request_load    = pyqtSignal(int)
    request_rename  = pyqtSignal(int)
    request_clear   = pyqtSignal(int)
    request_hotkey  = pyqtSignal(str)   # emits str(idx)

    _CSS_IDLE = """
        QPushButton {
            background: #252538; color: #c8c8ff;
            border: 1px solid #3e3e66; border-radius: 7px;
            font-size: 11px; padding: 6px;
        }
        QPushButton:hover { background: #2e2e50; border-color: #6666bb; }
        QPushButton:pressed { background: #1e1e38; }
    """
    _CSS_EMPTY = """
        QPushButton {
            background: #18182a; color: #484870;
            border: 1px dashed #303050; border-radius: 7px;
            font-size: 11px; padding: 6px;
        }
        QPushButton:hover { background: #20203a; border-color: #5050a0; color: #8080c0; }
    """
    _CSS_PLAYING = """
        QPushButton {
            background: #1a5c32; color: #aaffcc;
            border: 2px solid #33ff88; border-radius: 7px;
            font-size: 11px; font-weight: bold; padding: 6px;
        }
    """

    def __init__(self, idx: int, config: Config):
        super().__init__()
        self.idx        = idx
        self.config     = config
        self.is_playing = False
        self.setMinimumSize(QSize(110, 75))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.refresh()

    def refresh(self):
        d   = self.config.get_button(self.idx)
        has = bool(d.get("path"))
        if has:
            raw = d.get("label", f"Sound {self.idx + 1}")
            import textwrap
            label = "\n".join(textwrap.wrap(raw, width=10, break_long_words=False) or [raw])
            hk = self.config.get_hotkey(str(self.idx))
            if hk:
                label += f"\n[{hk.upper()}]"
        else:
            label = f"＋  Slot {self.idx + 1}"
        self.setText(label)
        self.setStyleSheet(
            self._CSS_PLAYING if (has and self.is_playing) else
            self._CSS_IDLE    if has else
            self._CSS_EMPTY
        )
        tip = d.get("path", "")
        self.setToolTip(Path(tip).name if tip else "Rechtsklick → Sound laden")

    def set_playing(self, state: bool):
        self.is_playing = state
        self.refresh()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.config.get_button(self.idx).get("path"):
                self.triggered_sound.emit(self.idx)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#252538; border:1px solid #444466; color:#c8c8ff; }
            QMenu::item:selected { background:#3a3a6a; }
        """)
        has      = bool(self.config.get_button(self.idx).get("path"))
        hk       = self.config.get_hotkey(str(self.idx))
        hk_label = f"⌨  Hotkey festlegen  [{hk.upper()}]" if hk else "⌨  Hotkey festlegen"

        a_load   = menu.addAction("📂  Sound laden …")
        a_rename = menu.addAction("✏️  Umbenennen")
        a_hotkey = menu.addAction(hk_label)
        menu.addSeparator()
        a_clear  = menu.addAction("🗑️  Leeren")
        a_rename.setEnabled(has)
        a_clear.setEnabled(has)
        act = menu.exec(event.globalPos())
        if   act == a_load:   self.request_load.emit(self.idx)
        elif act == a_rename: self.request_rename.emit(self.idx)
        elif act == a_hotkey: self.request_hotkey.emit(str(self.idx))
        elif act == a_clear:  self.request_clear.emit(self.idx)


# ── Main window ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):

    SINK_CSS_ON  = "color: #44ff88; font-size: 12px; font-weight: bold;"
    SINK_CSS_OFF = "color: #ff4444; font-size: 12px;"

    def __init__(self):
        super().__init__()
        self.config          = Config()
        self.players: dict[int, list[AudioPlayer]] = {}
        self.buttons:  list[SoundButton]      = []
        self._sink_mod_ids: list[str]         = []

        # Global hotkey manager
        self._hotkey_mgr = HotkeyManager()
        self._hotkey_mgr.hotkey_triggered.connect(self._on_hotkey_triggered)
        self._hotkey_mgr.start()

        self.setWindowTitle("maiNboard")
        self.setMinimumSize(860, 580)
        self._build_ui()
        self._apply_theme()
        self._populate_sources()
        self._check_sink()
        self._refresh_hotkeys()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(10, 10, 10, 8)
        vbox.setSpacing(6)

        # ── Zeile 1: Titel + Virtual Mic Status ────────────────────────────────
        hdr = QHBoxLayout()
        lbl = QLabel("maiNboard")
        lbl.setFont(QFont("", 15, QFont.Weight.Bold))
        hdr.addWidget(lbl)
        hdr.addStretch()

        self.lbl_sink = QLabel("● Virtual Mic: Inaktiv")
        self.lbl_sink.setStyleSheet(self.SINK_CSS_OFF)
        hdr.addWidget(self.lbl_sink)

        self.btn_sink = QPushButton("Virtual Mic aktivieren")
        self.btn_sink.setFixedHeight(30)
        self.btn_sink.clicked.connect(self._toggle_sink)
        hdr.addWidget(self.btn_sink)
        vbox.addLayout(hdr)

        # ── Zeile 2: Mikrofon-Auswahl + Gain ──────────────────────────────────
        mic_row = QHBoxLayout()
        mic_row.addWidget(QLabel("Mikrofon:"))
        self.cmb_mic = QComboBox()
        self.cmb_mic.setMinimumWidth(280)
        self.cmb_mic.setToolTip(
            "Wähle dein echtes Mikrofon.\n"
            "Es wird per Loopback in den Virtual Mic gemischt,\n"
            "damit Discord/TS3 deine Stimme UND die Sounds hört."
        )
        self.cmb_mic.currentIndexChanged.connect(self._on_mic_changed)
        mic_row.addWidget(self.cmb_mic)

        mic_row.addSpacing(12)
        mic_row.addWidget(QLabel("Mic Gain:"))

        self.sld_mic_gain = QSlider(Qt.Orientation.Horizontal)
        self.sld_mic_gain.setRange(100, 400)
        self.sld_mic_gain.setValue(self.config.mic_gain)
        self.sld_mic_gain.setFixedWidth(140)
        self.sld_mic_gain.setToolTip(
            "Verstärkt das Mikrofon-Signal digital.\n"
            "100 % = normal · 200 % = doppelt · 400 % = maximum\n"
            "Wird sofort angewendet."
        )
        self.sld_mic_gain.valueChanged.connect(self._on_mic_gain_changed)
        mic_row.addWidget(self.sld_mic_gain)

        self.lbl_mic_gain = QLabel(f"{self.config.mic_gain} %")
        self.lbl_mic_gain.setFixedWidth(45)
        mic_row.addWidget(self.lbl_mic_gain)

        mic_row.addStretch()
        vbox.addLayout(mic_row)

        # ── Zeile 3: Lautsprecher-Auswahl ─────────────────────────────────────
        spk_row = QHBoxLayout()
        spk_row.addWidget(QLabel("Lautsprecher:"))
        self.cmb_output = QComboBox()
        self.cmb_output.setMinimumWidth(280)
        self.cmb_output.setToolTip(
            "Ausgabegerät für 'Lokal mithören'.\n"
            "Wähle dein Steinberg / deine Kopfhörer.\n"
            "Wird auch als Default-Sink gesetzt damit Discord-Audio "
            "nicht in den Virtual Mic läuft."
        )
        self.cmb_output.currentIndexChanged.connect(self._on_output_changed)
        spk_row.addWidget(self.cmb_output)
        spk_row.addStretch()
        vbox.addLayout(spk_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333355;")
        vbox.addWidget(sep)

        # ── Sound-Grid ────────────────────────────────────────────────────────
        grid_w = QWidget()
        self.grid = QGridLayout(grid_w)
        self.grid.setSpacing(5)
        for i in range(ROWS * COLS):
            btn = SoundButton(i, self.config)
            btn.triggered_sound.connect(self._play)
            btn.request_load.connect(self._load_sound)
            btn.request_rename.connect(self._rename_sound)
            btn.request_clear.connect(self._clear_sound)
            btn.request_hotkey.connect(self._set_hotkey)
            self.buttons.append(btn)
            self.grid.addWidget(btn, i // COLS, i % COLS)
        vbox.addWidget(grid_w, stretch=1)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #333355;")
        vbox.addWidget(sep2)

        # ── Footer: Lautstärke + Lokal + Stop ─────────────────────────────────
        ftr = QHBoxLayout()

        self.chk_local = QCheckBox("Lokal mithören")
        self.chk_local.setChecked(self.config.local_monitor)
        self.chk_local.setToolTip(
            "Spielt den Sound SEPARAT über deine echten Lautsprecher ab.\n"
            "(Kein Loopback-Echo, da direkt ans Ausgabegerät gesendet.)"
        )
        self.chk_local.stateChanged.connect(self._on_local_changed)
        ftr.addWidget(self.chk_local)

        ftr.addSpacing(16)
        ftr.addWidget(QLabel("Lautstärke:"))

        self.sld_vol = QSlider(Qt.Orientation.Horizontal)
        self.sld_vol.setRange(0, 150)
        self.sld_vol.setValue(self.config.volume)
        self.sld_vol.setFixedWidth(160)
        self.sld_vol.setToolTip("0–100 % = normal · > 100 % = Boost")
        self.sld_vol.valueChanged.connect(self._on_volume)
        ftr.addWidget(self.sld_vol)

        self.lbl_vol = QLabel(f"{self.config.volume} %")
        self.lbl_vol.setFixedWidth(45)
        ftr.addWidget(self.lbl_vol)

        ftr.addSpacing(16)
        lbl_od = QLabel("Overdrive:")
        lbl_od.setStyleSheet("color: #ff8844;")
        ftr.addWidget(lbl_od)

        self.sld_od = QSlider(Qt.Orientation.Horizontal)
        self.sld_od.setRange(1, 100)
        self.sld_od.setValue(self.config.overdrive)
        self.sld_od.setFixedWidth(130)
        self.sld_od.setToolTip(
            "1 = clean · >1 = Hard-Clip Distortion\n"
            "Ab ~5 hört es sich nach Meme-Verzerrung an.\n"
            "20 = maximale Übersteurung."
        )
        self.sld_od.valueChanged.connect(self._on_overdrive)
        ftr.addWidget(self.sld_od)

        self.lbl_od = QLabel(self._od_label(self.config.overdrive))
        self.lbl_od.setFixedWidth(55)
        self.lbl_od.setStyleSheet("color: #ff8844;")
        ftr.addWidget(self.lbl_od)

        ftr.addStretch()

        self.btn_stop = QPushButton("■  Stop All")
        self.btn_stop.setFixedHeight(30)
        self.btn_stop.setToolTip("Alle Sounds stoppen  [Escape]  |  Rechtsklick → Hotkey festlegen")
        self.btn_stop.setStyleSheet("""
            QPushButton { background:#7a1515; color:#fff; border-radius:5px; padding:0 14px; }
            QPushButton:hover { background:#aa2222; }
        """)
        self.btn_stop.clicked.connect(self._stop_all)
        self.btn_stop.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_stop.customContextMenuRequested.connect(self._stop_all_context_menu)
        ftr.addWidget(self.btn_stop)
        vbox.addLayout(ftr)

        esc = QAction(self)
        esc.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        esc.triggered.connect(self._stop_all)
        self.addAction(esc)

        self.statusBar().showMessage(
            "Rechtsklick auf Slot → Sound laden  |  "
            "Mikrofon wählen → Virtual Mic aktivieren → in Discord/TS3 als Eingang setzen"
        )

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #16162a; color: #d0d0f8; }
            QLabel { color: #d0d0f8; }
            QPushButton {
                background: #252540; color: #d0d0f8;
                border: 1px solid #404070; border-radius: 5px; padding: 3px 10px;
            }
            QPushButton:hover { background: #303060; }
            QComboBox {
                background: #252540; color: #d0d0f8;
                border: 1px solid #404070; border-radius: 4px;
                padding: 3px 8px; min-height: 26px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: #252538; color: #d0d0f8;
                border: 1px solid #404070; selection-background-color: #3a3a6a;
            }
            QCheckBox { color: #b0b0e0; }
            QCheckBox::indicator { width: 14px; height: 14px; }
            QSlider::groove:horizontal {
                height: 5px; background: #2e2e50; border-radius: 2px;
            }
            QSlider::sub-page:horizontal { background: #5555cc; border-radius: 2px; }
            QSlider::handle:horizontal {
                width: 15px; height: 15px;
                background: #7777ee; border-radius: 8px; margin: -5px 0;
            }
            QStatusBar { color: #6060a0; font-size: 11px; background: #12122a; }
            QMenu {
                background: #252538; border: 1px solid #444466;
                color: #c8c8ff; border-radius: 4px;
            }
            QMenu::item:selected { background: #3a3a6a; }
        """)

    # ── Mikrofon-Quellen ───────────────────────────────────────────────────────
    def _get_real_sources(self) -> list[tuple[str, str]]:
        """Gibt (name, description) aller echten Mikrofon-Quellen zurück."""
        r = subprocess.run(["pactl", "list", "sources"],
                           capture_output=True, text=True)
        sources, name, desc = [], "", ""
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
                desc = ""
            elif line.startswith("Description:"):
                desc = line.split(":", 1)[1].strip()
                # Nur echte Mikrofone, keine Monitor-Quellen
                if name and not name.endswith(".monitor") and name not in (SINK_NAME, MIC_SOURCE_NAME):
                    sources.append((name, desc))
        return sources

    def _get_real_sinks(self) -> list[tuple[str, str]]:
        """Gibt (name, description) aller echten Audio-Ausgaben zurück."""
        r = subprocess.run(["pactl", "list", "sinks"],
                           capture_output=True, text=True)
        sinks, name, desc = [], "", ""
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
                desc = ""
            elif line.startswith("Description:"):
                desc = line.split(":", 1)[1].strip()
                if name and name != SINK_NAME:
                    sinks.append((name, desc))
        return sinks

    def _populate_sources(self):
        """Befüllt Mikrofon- und Lautsprecher-ComboBox."""
        # Mikrofon
        self.cmb_mic.blockSignals(True)
        self.cmb_mic.clear()
        sources = self._get_real_sources()
        saved_mic = self.config.mic_source
        sel_mic = 0
        for i, (name, desc) in enumerate(sources):
            self.cmb_mic.addItem(desc, userData=name)
            if name == saved_mic:
                sel_mic = i
        self.cmb_mic.setCurrentIndex(sel_mic)
        self.cmb_mic.blockSignals(False)
        if sources:
            self._on_mic_changed(sel_mic)

        # Lautsprecher
        self.cmb_output.blockSignals(True)
        self.cmb_output.clear()
        sinks = self._get_real_sinks()
        saved_out = self.config.output_sink
        sel_out = 0
        for i, (name, desc) in enumerate(sinks):
            self.cmb_output.addItem(desc, userData=name)
            if name == saved_out:
                sel_out = i
        self.cmb_output.setCurrentIndex(sel_out)
        self.cmb_output.blockSignals(False)
        if sinks:
            self._on_output_changed(sel_out)

    def _selected_source(self) -> str:
        return self.cmb_mic.currentData() or ""

    def _selected_output(self) -> str:
        return self.cmb_output.currentData() or ""

    def _on_mic_changed(self, _idx: int):
        self.config.mic_source = self._selected_source()

    def _on_output_changed(self, _idx: int):
        self.config.output_sink = self._selected_output()

    def _on_mic_gain_changed(self, v: int):
        self.config.mic_gain = v
        self.lbl_mic_gain.setText(f"{v} %")
        self._apply_mic_gain()

    def _apply_mic_gain(self):
        src = self._selected_source()
        if not src:
            return
        subprocess.run(
            ["pactl", "set-source-volume", src, f"{self.config.mic_gain}%"],
            capture_output=True
        )

    # ── Virtual Sink ───────────────────────────────────────────────────────────
    def _check_sink(self):
        r = subprocess.run(["pactl", "list", "sinks", "short"],
                           capture_output=True, text=True)
        self._update_sink_ui(SINK_NAME in r.stdout)

    def _toggle_sink(self):
        r = subprocess.run(["pactl", "list", "sinks", "short"],
                           capture_output=True, text=True)
        if SINK_NAME in r.stdout:
            self._teardown_sink()
        else:
            self._create_sink()

    def _create_sink(self):
        # 1. Null-Sink als virtuelles Mikrofon erstellen
        r = subprocess.run(
            ["pactl", "load-module", "module-null-sink",
             f"sink_name={SINK_NAME}",
             "sink_properties=device.description=maiNboard\\ Virtual\\ Mic"],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            QMessageBox.critical(self, "Fehler",
                f"Konnte Virtual Sink nicht erstellen:\n{r.stderr.strip()}")
            return
        self._sink_mod_ids.append(r.stdout.strip())

        # 2. Loopback: echtes Mikrofon → Virtual Sink
        #    (damit deine Stimme über den Virtual Mic zu Discord/TS3 gelangt)
        mic_src = self._selected_source()
        if mic_src:
            r2 = subprocess.run(
                ["pactl", "load-module", "module-loopback",
                 f"source={mic_src}",
                 f"sink={SINK_NAME}",
                 "latency_msec=1"],
                capture_output=True, text=True
            )
            if r2.returncode == 0:
                self._sink_mod_ids.append(r2.stdout.strip())
            else:
                self.statusBar().showMessage(
                    f"⚠  Mikrofon-Loopback fehlgeschlagen: {r2.stderr.strip()}"
                )
        else:
            self.statusBar().showMessage(
                "⚠  Kein Mikrofon gewählt – nur Soundboard-Sounds werden übertragen."
            )

        # 3. Remap-Source: macht den Monitor als echtes Mikrofon sichtbar
        #    → Discord zeigt es als auswählbares Gerät an
        r3 = subprocess.run(
            ["pactl", "load-module", "module-remap-source",
             f"master={SINK_NAME}.monitor",
             f"source_name={MIC_SOURCE_NAME}",
             "source_properties=device.description=maiNboard\\ Microphone"],
            capture_output=True, text=True
        )
        if r3.returncode == 0:
            self._sink_mod_ids.append(r3.stdout.strip())

        # 4. Default-Sink auf echten Lautsprecher zurücksetzen
        #    → verhindert dass Discord-Audio in den Virtual Sink läuft (Echo-Schleife)
        out = self._selected_output()
        if out:
            subprocess.run(["pactl", "set-default-sink", out], capture_output=True)

        # Mic Gain sofort anwenden
        self._apply_mic_gain()

        self._update_sink_ui(True)
        self.statusBar().showMessage(
            "Virtual Mic aktiv!  Setze in Discord/TS3 das Mikrofon auf "
            "«maiNboard Microphone»"
        )

    def _teardown_sink(self):
        for mod_id in reversed(self._sink_mod_ids):
            subprocess.run(["pactl", "unload-module", mod_id], capture_output=True)
        self._sink_mod_ids.clear()

        # Sicherheitsnetz: restliche Module per Name entfernen
        r = subprocess.run(["pactl", "list", "modules", "short"],
                           capture_output=True, text=True)
        for line in r.stdout.splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 3 and SINK_NAME in parts[2]:
                subprocess.run(["pactl", "unload-module", parts[0]],
                               capture_output=True)

        # Mic-Lautstärke zurücksetzen damit andere Apps normal klingen
        src = self._selected_source()
        if src:
            subprocess.run(["pactl", "set-source-volume", src, "100%"],
                           capture_output=True)

        self._update_sink_ui(False)
        self.statusBar().showMessage("Virtual Mic deaktiviert.")

    def _update_sink_ui(self, active: bool):
        if active:
            self.lbl_sink.setText("● Virtual Mic: Aktiv")
            self.lbl_sink.setStyleSheet(self.SINK_CSS_ON)
            self.btn_sink.setText("Virtual Mic deaktivieren")
            self.cmb_mic.setEnabled(False)
        else:
            self.lbl_sink.setText("● Virtual Mic: Inaktiv")
            self.lbl_sink.setStyleSheet(self.SINK_CSS_OFF)
            self.btn_sink.setText("Virtual Mic aktivieren")
            self.cmb_mic.setEnabled(True)

    def _sink_is_active(self) -> bool:
        r = subprocess.run(["pactl", "list", "sinks", "short"],
                           capture_output=True, text=True)
        return SINK_NAME in r.stdout

    def _default_sink(self) -> str | None:
        r = subprocess.run(["pactl", "get-default-sink"],
                           capture_output=True, text=True)
        s = r.stdout.strip()
        return s if s and s != SINK_NAME else None

    # ── Playback ───────────────────────────────────────────────────────────────
    def _play(self, idx: int):
        d    = self.config.get_button(idx)
        path = d.get("path", "")
        if not path or not Path(path).exists():
            self.statusBar().showMessage(f"⚠  Datei nicht gefunden: {path}")
            return

        sink_active = self._sink_is_active()
        sink        = SINK_NAME if sink_active else None

        # Lautsprecher: explizit gewähltes Gerät (Steinberg), nicht default sink
        # (default sink könnte durch PipeWire auf maiNboard_sink gesetzt worden sein)
        out = self._selected_output()
        if self.config.local_monitor and out:
            local_sink = out
        elif self.config.local_monitor and not sink_active:
            local_sink = out or None
        else:
            local_sink = None

        player = AudioPlayer(idx, path, sink, local_sink, self.config.volume, self.config.overdrive)
        player.sig_started.connect(self._on_player_started)
        player.sig_stopped.connect(self._on_player_stopped)
        player.finished.connect(lambda: self._on_player_finished(idx))
        player.start()

        self.players.setdefault(idx, []).append(player)

        dest = SINK_NAME if sink else "Standard-Ausgabe"
        self.statusBar().showMessage(f"▶  {Path(path).name}  →  {dest}")

    def _on_player_started(self, idx: int):
        self.buttons[idx].set_playing(True)

    def _on_player_stopped(self, idx: int):
        pass  # Aufräumen passiert in _on_player_finished (nach Thread-Ende)

    def _on_player_finished(self, idx: int):
        # Abgeschlossene Player aus der Liste entfernen (isRunning() ist jetzt sicher False)
        self.players[idx] = [p for p in self.players.get(idx, []) if p.isRunning()]
        # Button nur ausschalten wenn wirklich alle Instanzen fertig sind
        if not self.players[idx]:
            self.buttons[idx].set_playing(False)

    def _stop_all(self):
        for players in self.players.values():
            for p in players:
                if p.isRunning():
                    p.stop()
        for btn in self.buttons:
            btn.set_playing(False)
        self.statusBar().showMessage("■  Alle Sounds gestoppt.")

    # ── Hotkey support ─────────────────────────────────────────────────────────
    def _set_hotkey(self, action_id: str):
        """Öffnet den Hotkey-Dialog und speichert das Ergebnis."""
        current_key = self.config.get_hotkey(action_id)
        accepted, key_str = HotkeyDialog.get_hotkey(self, current_key)
        if not accepted:
            return
        self.config.set_hotkey(action_id, key_str)
        self._refresh_hotkeys()
        if action_id.isdigit():
            self.buttons[int(action_id)].refresh()

    def _stop_all_context_menu(self, pos):
        """Rechtsklick-Menü auf den Stop-All-Button."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#252538; border:1px solid #444466; color:#c8c8ff; }
            QMenu::item:selected { background:#3a3a6a; }
        """)
        hk       = self.config.get_hotkey("stop_all")
        hk_label = f"⌨  Hotkey festlegen  [{hk.upper()}]" if hk else "⌨  Hotkey festlegen"
        a_hotkey = menu.addAction(hk_label)
        act = menu.exec(self.btn_stop.mapToGlobal(pos))
        if act == a_hotkey:
            self._set_hotkey("stop_all")

    def keyPressEvent(self, event):
        """Hotkeys abfangen wenn das Fenster aktiv ist (Wayland-Fallback)."""
        key  = event.key()
        mods = event.modifiers()

        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift,
                   Qt.Key.Key_Meta, Qt.Key.Key_AltGr, Qt.Key.Key_Escape):
            super().keyPressEvent(event)
            return

        key_str = HotkeyDialog._qt_key_to_str(HotkeyDialog, key)
        if not key_str:
            super().keyPressEvent(event)
            return

        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mods & Qt.KeyboardModifier.KeypadModifier:
            parts.append("kp_" + key_str)
        else:
            parts.append(key_str)
        full = "+".join(parts)

        hotkeys = self.config.data.get("hotkeys", {})
        for action_id, hotkey in hotkeys.items():
            if hotkey == full:
                self._on_hotkey_triggered(action_id)
                return

        super().keyPressEvent(event)

    def _on_hotkey_triggered(self, action_id: str):
        """Empfängt ausgelöste globale Hotkeys vom HotkeyManager."""
        if action_id == "stop_all":
            self._stop_all()
        elif action_id.isdigit():
            self._play(int(action_id))

    def _refresh_hotkeys(self):
        """Synchronisiert HotkeyManager und Stop-Button-Text mit der Config."""
        hotkeys = self.config.data.get("hotkeys", {})
        self._hotkey_mgr.update_hotkeys(hotkeys)
        hk = self.config.get_hotkey("stop_all")
        self.btn_stop.setText(
            f"■  Stop All  [{hk.upper()}]" if hk else "■  Stop All"
        )

    # ── Button-Slots ───────────────────────────────────────────────────────────
    def _load_sound(self, idx: int):
        path, _ = QFileDialog.getOpenFileName(
            self, "Sound auswählen", str(SOUNDS_DIR),
            "Audio (*.wav *.mp3 *.ogg *.flac *.opus *.m4a *.aac *.wma *.aiff);;Alle (*)"
        )
        if path:
            self.config.set_button(idx, path, Path(path).stem)
            self.buttons[idx].refresh()

    def _rename_sound(self, idx: int):
        d = self.config.get_button(idx)
        name, ok = QInputDialog.getText(
            self, "Umbenennen", "Name:", text=d.get("label", "")
        )
        if ok and name.strip():
            self.config.set_button(idx, d["path"], name.strip())
            self.buttons[idx].refresh()

    def _clear_sound(self, idx: int):
        self.config.clear_button(idx)
        self.buttons[idx].set_playing(False)
        self.buttons[idx].refresh()

    # ── Controls ───────────────────────────────────────────────────────────────
    def _on_volume(self, v: int):
        self.config.volume = v
        self.lbl_vol.setText(f"{v} %")

    def _on_local_changed(self, state: int):
        self.config.local_monitor = (state == Qt.CheckState.Checked.value)

    def _od_label(self, v: int) -> str:
        if v == 1:   return "clean"
        if v <= 5:   return f"{v}x  mild"
        if v <= 15:  return f"{v}x  crunch"
        if v <= 40:  return f"{v}x  meme"
        if v <= 70:  return f"{v}x  💀"
        return       f"{v}x  ☠️"

    def _on_overdrive(self, v: int):
        self.config.overdrive = v
        self.lbl_od.setText(self._od_label(v))
        r = min(255, 160 + v)
        self.lbl_od.setStyleSheet(f"color: rgb({r}, {max(20, 130 - v)}, 20);")

    def closeEvent(self, event):
        self._stop_all()
        self._hotkey_mgr.stop_listener()
        super().closeEvent(event)


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    SOUNDS_DIR.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    app.setApplicationName("maiNboard")

    icon_path = str(SCRIPT_DIR / "maiNboard.svg")
    app.setWindowIcon(QIcon(icon_path))

    win = MainWindow()
    win.setWindowIcon(QIcon(icon_path))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
