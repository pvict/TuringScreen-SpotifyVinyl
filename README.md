<p align="center">
  <img src="docs/images/turzx-480x480-openrgb-setup.jpg" alt="Turing Vinyl running inside a PC with synchronized OpenRGB lighting" height="280">
  <img src="docs/images/turzx-spotify-true-colors.png" alt="Cyndi Lauper True Colors on the USB display with matching pink RGB lighting" height="280">
</p>

https://github.com/user-attachments/assets/f876053e-42a8-4e0f-b7f9-6a048da14437

<p align="center"><sub>24 seconds: pause, resume, playlist animations and RGB synchronization.</sub></p>

<h1 align="center">Turing Vinyl · Spotify for TURZX</h1>

<p align="center"><a href="README.pt-BR.md">Português</a> · English</p>

Turn a compatible **2.1-inch round TURZX / Turing Smart Screen (480 × 480)** into a **Spotify Now Playing vinyl display**. A Windows desktop app with rotating album artwork, track details, playback progress and optional **OpenRGB** or **Lotus Lantern Bluetooth RGB** sync.

The record slows down when paused and artwork flips on track changes. Choose a background video, adjust brightness and control Spotify from the app.

<p align="center"><a href="#install">Install</a> · <a href="#use-the-app">Use the app</a> · <a href="#compatible-display">Compatible display</a> · <a href="#optional-integrations">RGB & Spotify setup</a> · <a href="#help">Help</a></p>

## Install

### 1. Prepare your PC

| You need | Setup |
| --- | --- |
| **Windows 10/11** | A compatible USB display; see [the tested model](#compatible-display). |
| **Python 3.13, 64-bit** | Install from [python.org](https://www.python.org/downloads/windows/), including the Python launcher and Tcl/Tk. |
| **NVIDIA GPU with NVENC** | Install its driver. Live vinyl rendering currently requires the NVIDIA encoder. |
| **FFmpeg + FFprobe** | Get a Windows build through [ffmpeg.org](https://ffmpeg.org/download.html), with `h264_nvenc` and `libx264`. Add its `bin` folder to Windows **Path**. |
| **Spotify for Windows** | Needed for music modes. Basic artwork and playback controls work without a Spotify Developer app. |

<details>
<summary>How to add FFmpeg to Path</summary>

1. Extract FFmpeg into a permanent folder, for example `C:\ffmpeg`.
2. Locate the folder containing **ffmpeg.exe** and **ffprobe.exe**, usually `C:\ffmpeg\bin`.
3. Search Windows for **Edit environment variables for your account**. Under **User variables**, select **Path → Edit → New** and paste that folder's full path.
4. Confirm with **OK** and reopen PowerShell and Turing Vinyl after changing Path.

</details>

### 2. Download and set up once

[Download the project ZIP](https://github.com/pvict/TuringScreen-SpotifyVinyl/archive/refs/heads/master.zip) and extract it into a permanent folder. Open the extracted folder containing **README.md**. Type `powershell` in File Explorer's address bar and press **Enter**.

Paste this block into the PowerShell window:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe criar_atalho.py
```

### 3. Open Turing Vinyl

Double-click **Turing Vinyl.lnk** in the project folder. Use this shortcut every day; you can pin it to the taskbar. Keep the project folder in place so the shortcut and bundled videos remain available.

## Use the app

<p align="center">
  <img src="docs/images/turing-vinyl-interface.png" alt="Turing Vinyl Windows interface: rotating record, Spotify playback controls, display modes and brightness slider" width="860">
</p>

1. Connect the screen by USB and start a track in **Spotify for Windows**.
2. Open **Turing Vinyl**, choose a mode and click **Iniciar** (Start).
3. Click **Parar** (Stop) when finished.

The interface labels are currently in Portuguese.

| Mode | What the screen shows |
| --- | --- |
| **Dinâmico** | Vinyl while music plays; background video when paused or idle. |
| **Spotify** | Vinyl stays visible; it gently stops and the artwork shrinks on pause. |
| **Vídeo** | Background video only. |
| **Gaming** | Loops a prepared background at 30 FPS with reduced processing and no music overlays. Switch it off to restore your selected mode. |

| Control | What it does |
| --- | --- |
| **Brilho / Auto** | Adjust screen brightness, or let it follow the time of day. **0%** and the power button turn off the screen. |
| **Playback buttons** | Shuffle, previous, play/pause, next and repeat, when Spotify exposes those controls to Windows. |
| **Fundo → Escolher vídeo** | Pick your background; the app converts it and saves your choice. **Padrão** restores the included video. |

<details>
<summary>See the background video panel</summary>

<img src="docs/images/turing-vinyl-background.png" alt="Turing Vinyl background video picker with conversion progress" width="860">

</details>

## Compatible display

The photos show the **2.1-inch round USB IPS display, 480 × 480**, sold as *“2.1 Inch IPS Secondary Screen Water-Cooled Round Screen”*, with **TURZX** as the seller's customization app. [View the display on AliExpress](https://pt.aliexpress.com/item/1005006523861753.html).

Turing Vinyl communicates directly over USB using device ID **`1CBE:0021`**. Close TURZX while using it. Similar-looking displays can use a different protocol; **2.8-inch models and other displays have not been validated**.

## Optional integrations

| Add-on | What it adds | Setup guide |
| --- | --- | --- |
| **Spotify Web API** | Playlist artwork and **Up next** cards. | [Enable playlist & Up next](docs/integrations.md#playlist-and-up-next) |
| **OpenRGB** | PC LEDs follow album colors. Current preset: **ASRock B450M Steel Legend**. | [Connect OpenRGB](docs/integrations.md#pc-lighting-with-openrgb) |
| **Lotus Lantern** | Bluetooth strip follows album colors; tested with **ELK-BLEDDM**. | [Connect the RGB strip](docs/integrations.md#bluetooth-strip-with-lotus-lantern) |

These integrations are optional. The setup guide also covers strip calibration and connection logs.

## Help

| Problem | Try this |
| --- | --- |
| `py` is not recognized | Install Python 3.13 with the launcher, then reopen PowerShell. |
| Nothing appears after **Iniciar** | Check USB, [display compatibility](#compatible-display), FFmpeg on Path and NVENC support. Close other apps using the screen. |
| Playback buttons are disabled | Start a track in Spotify for Windows so its media session is available. |
| Playlist / Up next is missing | Follow the [Spotify setup](docs/integrations.md#playlist-and-up-next), including authorization and development-mode requirements. |
| PC LEDs or the strip do not respond | Follow the matching [RGB setup guide](docs/integrations.md). |

Still stuck? [Open an issue](https://github.com/pvict/TuringScreen-SpotifyVinyl/issues) with the time, what you clicked and the relevant lines from **tela.log** in the project folder. Remove personal information before sharing logs.

## Credits & license

USB backend: [Turing Smart Screen CLI](https://github.com/phstudy/turing-smart-screen-cli) ([MIT](turing-smart-screen-cli-main/LICENSE)). Fonts: Fraunces and DM Sans ([OFL](assets/fonts/fraunces-OFL.txt), [OFL](assets/fonts/dmsans-OFL.txt)). Bluetooth integration: [Lotus Lantern for Windows](https://github.com/razibit/Lotus-Lantern-for-Windows-PC). Related display project: [turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python).

An unofficial project by [Paulo](https://github.com/pvict). A license for this project's own code and media has not yet been declared.
