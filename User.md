# VoiceEdge user guide

VoiceEdge lets two or more people talk by voice when their laptops are on the
same Wi-Fi network. It does not use Google Meet, Zoom, or the internet.

You need:

* One laptop to act as the **host**.
* One laptop for each friend.
* The `VoiceEdgeGateway.exe` file for the host.
* The `VoiceEdgeClient.exe` file for every person joining.
* A microphone and speaker or headphones.

## Host setup

1. Connect all laptops to the same Wi-Fi.
2. Double-click `VoiceEdgeGateway.exe`.
3. If Windows shows a firewall prompt, allow the application on **Private
   networks**. This is normally a one-time step.

If Windows does not show a prompt and friends cannot connect, ask an
administrator to allow `VoiceEdgeGateway.exe` through Windows Defender
Firewall. For a developer checkout, the one-time repair command is:

```powershell
.\scripts\open_firewall.ps1 -GatewayExecutable .\dist\VoiceEdgeGateway.exe
```

Windows Defender Firewall protects your laptop from unwanted incoming
connections. The command allows the other laptops to reach VoiceEdge.
4. Keep the gateway window open while chatting.
5. Find the host laptop's Wi-Fi address:

   ```powershell
   ipconfig
   ```

   Find the **IPv4 Address** under the Wi-Fi adapter. It will look similar to
   `192.168.1.25`.

The host can also join the conversation by opening `VoiceEdgeClient.exe` on
the same laptop and entering `127.0.0.1:8765`.

## Friend setup

1. Copy `VoiceEdgeClient.exe` to your laptop.
2. Double-click it. No Python, ffmpeg, pip, or Arduino is needed.
3. In **Gateway**, enter the host address and port, for example:

   ```text
   192.168.1.25:8765
   ```

4. Enter your name and keep the room as `lab`, unless everyone agreed on a
   different room.
5. Select your microphone and speaker.
6. Click **Connect**.

The **Find gateway** button may fill the address automatically. Manual entry
always works.

## During the call

* Use **Mute** when you do not want to send your microphone.
* Use headphones to prevent echo.
* Everyone must use the same room name.
* The host must keep the gateway window open.
* To leave, click **Disconnect** or close the client window.

## If it does not connect

1. Confirm all laptops are on the same Wi-Fi.
2. Confirm the host gateway window is still open.
3. Check that the host address is the host's Wi-Fi IPv4 address, not
   `localhost` or `127.0.0.1`.
4. Run the firewall command again as Administrator.
5. Check whether the Wi-Fi blocks devices from talking to each other. A
   mobile hotspot can be used to test this.
6. Confirm the microphone is connected and selected.
7. Close other applications that may be using the microphone.

If Windows shows a SmartScreen warning for the unsigned application, choose
**More info**, then **Run anyway** only if you received the executable from
the trusted VoiceEdge project folder.
