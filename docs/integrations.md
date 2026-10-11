# Optional integrations

[Back to the README](../README.md) · [Português](integrations.pt-BR.md)

Install Turing Vinyl first. Configure only the integrations you want; basic music display uses Spotify's Windows media session.

## Playlist and Up next

**Adds:** playlist artwork, playlist name when available, and the next-track announcement.

1. Create your own app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), selecting **Web API**.
2. In its settings, add this **Redirect URI** and save:

   ```text
   http://127.0.0.1:8765/callback
   ```

3. Copy the **Client ID**. In the Turing Vinyl folder, create **spotify_client_id.txt** containing only that ID. In Notepad, use **Save as type: All files** so the name does not become `spotify_client_id.txt.txt`.
4. Open Turing Vinyl, click **Iniciar** and authorize your Spotify account in the browser when prompted.

No Client Secret is needed. In Spotify's development mode, the app owner must have **Premium**. Other accounts must be added under **Settings → Users Management**; otherwise requests can fail with **403**. See [Spotify's development-mode requirements](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).

The playlist card lasts **5 seconds**. **Up next** appears around **22 seconds before the end**, for **7 seconds**, when Spotify supplies queue information. Internet access is required for these extras.

## PC lighting with OpenRGB

**Adds:** album-color synchronization for supported PC LEDs.

1. Install [OpenRGB](https://openrgb.org/) and confirm that it detects your motherboard.
2. Enable its **SDK server** at `127.0.0.1:6742`.
3. Leave OpenRGB running, then open Turing Vinyl and click **Iniciar**.

The current preset targets **ASRock B450M Steel Legend** zones **Addressable Header, PCH and IO Cover**. The background/idle color comes from the cached `purple rain` profile. Other controllers need their own configuration; RGB device selection is not available in the app yet.

Close other lighting programs controlling the same device to prevent conflicting commands.

## Bluetooth strip with Lotus Lantern

**Adds:** album-color synchronization for a Bluetooth RGB strip, independently of OpenRGB. Experimental; validated with **ELK-BLEDDM**.

### 1. Prepare Lotus once

Install [Node.js](https://nodejs.org/) **18 or newer**, then download and extract [Lotus Lantern for Windows](https://github.com/razibit/Lotus-Lantern-for-Windows-PC). Open PowerShell in its extracted folder and run:

```powershell
npm.cmd ci
```

Keep the folder containing **config.cmd**, **src/ble-device.cjs** and **node_modules**.

### 2. Set your strip's address

Turn on Bluetooth and the strip. After Windows detects it, run this in PowerShell:

```powershell
Get-PnpDevice -Class Bluetooth |
  Where-Object FriendlyName -Like 'ELK*' |
  Select-Object FriendlyName, InstanceId
```

In an ID such as `BTHLE\DEV_AA11BB22CC33\...`, **AA11BB22CC33** is the address. Edit **config.cmd** in the Lotus folder and set the existing line to your address, without colons or hyphens:

```bat
set LED_DEVICE_UUID=AA11BB22CC33
```

Use your own address, not the example. If no device appears, check Windows Bluetooth settings. If the address changes later, update this line.

### 3. Connect through Turing Vinyl

1. Close Lotus on the phone and any other program controlling the strip.
2. Open **Turing Vinyl** and click **Fita RGB**. On the first use, select the **Lotus folder** you prepared.
3. Click **Iniciar** in the main window. The strip follows album colors and the brightness used for the PC LEDs, with smooth transitions.

Right-click **Fita RGB** to change the Lotus folder. Hover over it for connection status. Clicking it again disables synchronization; stopping the app leaves the strip at its last color.

Turing Vinyl starts its own Bluetooth bridge. Keep the Lotus launcher closed; you do not need OpenRGB or its Effects plugin for this integration. On connection failure, the bridge retries the configured address.

### Color calibration and logs

The included [calibracao_lotus.example.json](../calibracao_lotus.example.json) is used by default. Each strip can render colors differently. To tune yours:

1. Copy that file to **calibracao_lotus.json** in the Turing Vinyl folder.
2. Adjust **ganhos_rgb** for the red, green and blue balance; **ganhos_quentes** adjusts warm tones gradually.
3. Each gain accepts **0–2**. `[1, 1, 1]` makes the corresponding adjustment neutral. Changes are read while the app runs.

Your local calibration file is excluded from Git. Connection logs are in **diagnostico_leds/lotus.log**; timestamps in that file use **UTC**.

If the strip does not respond, check its power, Bluetooth, the address, Node.js and the Lotus dependencies. Also make sure no other Lotus bridge is using local port `4048`.
