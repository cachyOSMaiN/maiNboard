# maiNboard

Ein schlichter, aber funktionaler Linux-Soundboard mit **Virtual Mic** – perfekt für Discord, TeamSpeak und andere VoIP-Apps.

Sounds werden sowohl lokal über die Lautsprecher als auch direkt in dein Mikrofon eingespeist, sodass alle im Call es hören können.

![maiNboard Screenshot](maiNboard.svg)

---

## Features

- **24 Sound-Slots** (4×6 Grid), frei belegbar per Drag & Drop oder Datei-Dialog
- **Virtual Mic** – mischt Soundboard-Sounds und dein echtes Mikrofon in einen virtuellen PulseAudio-Sink, den Discord/TS3 als Mikrofon sieht
- **Lokal mithören** – Sounds werden parallel auf deinen echten Lautsprechern abgespielt
- **Globale Hotkeys** – Sounds per Numpad oder beliebiger Taste auslösen, auch wenn die App im Hintergrund ist
- **Overdrive** – Hard-Clip-Distortion für maximale Meme-Energie
- **Lautstärke-Boost** bis 150 %
- **Mic Gain** – digitale Mikrofon-Verstärkung (100–400 %)
- Konfiguration wird automatisch in `config.json` gespeichert

---

## Audio-Routing

```
Echtes Mikrofon (z. B. UR22mkII)  ──loopback──►  maiNboard_sink (Virtual Sink)
                                                           │
Soundboard (ffmpeg + paplay)  ──────────────►  maiNboard_sink
                                                           │
                                                maiNboard_sink.monitor
                                                           │
                                                Discord / TS3  ◄── hört Stimme + Sounds

Soundboard (ffmpeg + paplay)  ──────────────►  Echte Lautsprecher  (lokal mithören)
```

Discord/TS3 sieht ein Gerät namens **„maiNboard Microphone"** – dieses einfach als Eingabegerät auswählen.

---

## Voraussetzungen

### System (CachyOS / Arch Linux)

```bash
sudo pacman -S python-pyqt6 python-pynput ffmpeg pipewire pipewire-pulse wireplumber libpulse
```

| Paket | Zweck |
|---|---|
| `python-pyqt6` | GUI-Framework |
| `python-pynput` | Globale Hotkeys (auch im Hintergrund) |
| `ffmpeg` | Audio-Dekodierung & Lautstärke-Filterung |
| `pipewire` + `pipewire-pulse` | PulseAudio-kompatible Audio-Schicht |
| `wireplumber` | PipeWire Session Manager |
| `libpulse` | Stellt `paplay` und `pactl` bereit |

> **Hinweis:** Auf CachyOS KDE sind `pipewire`, `pipewire-pulse` und `wireplumber` in der Regel bereits vorinstalliert.

### Python-Pakete (alternativ via pip)

Falls `python-pynput` nicht über pacman verfügbar ist:

```bash
pip install pynput --break-system-packages
```

---

## Installation & Start

```bash
# Repository klonen
git clone https://github.com/maiNframe/maiNboard.git
cd maiNboard

# Direkt starten
python soundboard.py
```

Beim ersten Start wird der `sounds/`-Ordner automatisch angelegt.

---

## Sounds hinzufügen

1. Rechtsklick auf einen leeren Slot → **„Sound laden …"**
2. Audiodatei auswählen (MP3, WAV, OGG, FLAC, Opus, M4A, AAC, AIFF)
3. Optional: Slot umbenennen oder Hotkey festlegen

Sounds werden **nicht** im Repository mitgeliefert – du legst eigene Dateien in `sounds/` ab.

---

## Hotkeys

- Rechtsklick auf einen Sound-Slot → **„Hotkey festlegen"**
- Rechtsklick auf **„Stop All"** → Hotkey für globalen Stopp
- Hotkeys funktionieren auch wenn das Fenster im Hintergrund ist (via pynput)
- Auf Wayland ohne Compositor-Support greift der Fenster-Fokus-Fallback

---

## Virtual Mic einrichten

1. Mikrofon in der Dropdown-Liste auswählen
2. **„Virtual Mic aktivieren"** klicken
3. In Discord/TS3: Eingabegerät auf **„maiNboard Microphone"** setzen
4. Lautsprecher-Ausgabe ebenfalls korrekt setzen (verhindert Echo-Schleifen)

---

## Bekannte Einschränkungen

- Globale Hotkeys funktionieren unter **Wayland** nur eingeschränkt (pynput benötigt X11-Zugriff). Als Workaround: Fenster fokussiert lassen oder XWayland nutzen.
- Der Virtual Sink wird **nicht** persistent gespeichert – nach einem Neustart muss er erneut aktiviert werden (PulseAudio/PipeWire-Module sind Session-gebunden).

---

## Lizenz

MIT License – mach damit was du willst.
