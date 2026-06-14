# W41K3RJ Biometric Payment

This project now has two coordinated parts:

1. `src/main.cpp`
   ESP32 firmware for keypad input, LCD status, buzzer, LED indicators, AS608 fingerprint enrollment/payment, fixed-IP WiFi, and machine heartbeat.
2. `server/app.py`
   HTTPS server for customer registration, wallet balances, payment transfer to the owner account, live dashboard, machine status, and optional Gmail payment alerts.

## Current Product Flow

### Register

1. Press `A` on the keypad.
2. Enter the customer account number suffix.
3. Enter the phone number.
4. Enter the 20-digit NIDA number.
5. Enter the 4-digit PIN.
6. The server allocates an AS608 local sensor slot.
7. The customer scans the same finger twice.
8. The ESP32 hashes the stored fingerprint template and sends the registration to the server.
9. The server creates the account code with the required prefix `W41K3RJ`.
10. New customer accounts start with `TZS 100,000.00`.

### Pay

1. Press `B` or `#`.
2. Enter the amount.
3. The minimum payment is `TZS 500.00`.
4. The customer scans a registered finger on the AS608 sensor.
5. The server identifies the mapped account.
6. The customer enters the 4-digit PIN.
7. The server deducts the amount from the customer wallet.
8. The server adds the same amount to the owner wallet `W41K3RJ000000`.
9. The dashboard updates automatically.
10. If email is configured, the server sends a payment alert with the amount and fixed location link.

## Dashboard

Open:

```text
https://YOUR_SERVER_IP:8443/
```

The dashboard shows:

- machine active/offline status
- machine location
- ZKTeco F12 model and RS485 wiring mode
- whether the F12 can do direct enrollment or server-side matching
- customer accounts
- account type
- local AS608 slot
- balance
- owner wallet balance
- recent payments

The dashboard title is `W41K3RJ Biometric Payment`.

## Fixed IP And WiFi

The firmware keeps WiFi in station mode and now supports a fixed local IP in [src/server_config.h](/media/RJ/video+pc/ZENO PAY BIOMETRICS/src/server_config.h).

Adjust these values for your network:

- `kDeviceIp`
- `kGateway`
- `kSubnet`
- `kDns1`
- `kDns2`

The WiFi protocol is not changed.

Current PC network setup on this machine:

- WiFi profile: `simon`
- WiFi password in firmware: `SIMON1234`
- fixed PC/server IP: `192.168.43.115`
- gateway: `192.168.43.15`

As long as you keep using the same `simon` hotspot/router, the PC should come back on the same IP after restart and the ESP32 will not need a new server IP.

## Email Alerts

The server supports Gmail app-password alerts. The code does not hardcode your password.

Copy the example env file and fill in your Gmail details:

```bash
cp server/.env.local.example server/.env.local
```

Then edit `server/.env.local` and set:

```bash
ZENO_SMTP_EMAIL="your-gmail-address@gmail.com"
ZENO_SMTP_APP_PASSWORD="YOUR_GMAIL_APP_PASSWORD"
ZENO_ALERT_EMAIL="where-you-want-alerts@gmail.com"
```

The server now loads `server/.env.local` automatically on startup.

## TLS Setup

Generate a certificate for the server LAN IP before flashing the ESP32:

```bash
python3 scripts/generate_tls_assets.py --host YOUR_SERVER_LAN_IP
```

Example:

```bash
python3 scripts/generate_tls_assets.py --host 192.168.1.50
```

This updates:

- `server/certs/server.crt`
- `server/certs/server.key`
- `src/generated_server_config.h`

## Run The Server

```bash
chmod +x scripts/start_server.sh
./scripts/start_server.sh
```

You can still run the Python file directly:

```bash
python3 server/app.py --host 0.0.0.0 --port 8443
```

Or use the helper script:

```bash
./scripts/manage_server.sh start
./scripts/manage_server.sh status
./scripts/manage_server.sh stop
```

Desktop launcher on this PC:

```text
~/Desktop/Start Zeno Pay Server.desktop
```

Automatic boot start on this PC:

```text
crontab @reboot -> /home/junior/.local/bin/zeno-pay-server-boot
```

## Build Firmware

PlatformIO now includes an ESP32-S3 environment in [platformio.ini](/media/RJ/video+pc/ZENO PAY BIOMETRICS/platformio.ini).

Default target:

```text
esp32-s3-devkitc-1
```

Legacy target still kept:

```text
esp32doit-devkit-v1
```

## ZKTeco F12 Reality

Your new reader matches the ZKTeco F12 slave-reader family. The project now reports that reader to the server/dashboard as:

- model: `ZKTeco F12 RS485 Slave Reader`
- transport: `RS485`
- power: external `12V DC`
- capability: slave reader only

The firmware also shows a ZKTeco info screen on keypad key `C`.

What the project now does with the F12:

- records the F12 model and wiring mode in heartbeat data
- shows the F12 power and RS485 transport state on the web dashboard
- keeps the AS608 flow working for real registration/payment

What the F12 still does not do directly in this project:

- raw fingerprint enrollment from F12 into ESP32
- raw fingerprint upload from F12 to the Python server
- true server-side fingerprint matching from F12 captures

Why:

- F12 is an RS485 slave reader, not the same class of device as a USB enrollment scanner
- ZKTeco’s own installation material for F12-style readers says fingerprint enrollment is done through compatible controllers/software or USB enrollment readers
- ZKTeco’s Linux SDK support is published for USB fingerprint scanners such as `ZK9500`, `ZK6500`, `ZK8500R`, and `SLK20R`, not for the F12 slave reader itself

If you want real server-side biometric enrollment/matching on Kali Linux, the better hardware path is:

1. Keep `AS608` for on-terminal local matching if you want.
2. Keep `F12` only as a slave reader if you later add a compatible ZKTeco controller.
3. Add a `ZK8500R` or another ZKTeco USB scanner supported by `ZKFinger SDK for Linux` for true server-side enrollment/matching work.

## Important Hardware Reality

What is working in this code now:

- AS608 registration on the machine
- AS608 local fingerprint matching for payment
- F12 model/status reporting to the server and dashboard
- server-created `W41K3RJ...` customer accounts
- `TZS 100,000.00` starting wallet for new customers
- owner wallet transfer
- live server dashboard
- machine heartbeat and active status
- buzzer and LED status outputs

What is not fully implemented yet:

- real ZKTeco F12 RS485 fingerprint capture into the ESP32
- true server-side biometric matching for pay-anywhere terminals

Why that part is not done yet:

- the current codebase uses the Adafruit AS608 workflow, which matches fingerprints on the sensor itself
- the F12 is a slave reader designed to work with ZKTeco controllers/masters over RS485
- “finger saved only on the server, not on the sensor, and usable anywhere” needs raw template capture plus a compatible server-side biometric matching engine, not just a template hash
- the official ZKTeco Linux SDK support that is publicly described is for USB fingerprint scanners, not the F12 slave reader

So the current project is a professional next step, but the ZKTeco multi-terminal part still needs one of these paths:

1. a compatible ZKTeco controller/master that manages the F12
2. a ZKTeco USB scanner with Linux SDK for server-side biometric work
3. a private/proprietary protocol or SDK for direct F12 template capture
4. a final decision on whether you want controller-managed matching or true server-managed matching

## Suggested Wiring Notes

For your F12 and RS485 converter:

- ZKTeco `485+` -> converter `A+`
- ZKTeco `485-` -> converter `B-`
- one F12 `GND` -> converter `GND`
- second F12 `GND` -> 12V power supply ground
- F12 `+12V` -> 12V power supply positive
- converter TTL `TXD` -> ESP32 RX pin
- converter TTL `RXD` -> ESP32 TX pin
- converter TTL `GND` -> ESP32 GND
- converter TTL `VCC` -> correct voltage for the converter board

The two grounds still need common reference between the 12V supply, the RS485 converter, and the ESP32.

More detailed notes are in [docs/zkteco-f12.md](/media/RJ/video+pc/ZENO PAY BIOMETRICS/docs/zkteco-f12.md).

The firmware currently reserves:

- `kZkRs485RxPin`
- `kZkRs485TxPin`

for the future ZKTeco driver.

## Files To Review

- [docs/zkteco-f12.md](/media/RJ/video+pc/ZENO PAY BIOMETRICS/docs/zkteco-f12.md)
- [src/main.cpp](/media/RJ/video+pc/ZENO PAY BIOMETRICS/src/main.cpp)
- [src/server_config.h](/media/RJ/video+pc/ZENO PAY BIOMETRICS/src/server_config.h)
- [server/app.py](/media/RJ/video+pc/ZENO PAY BIOMETRICS/server/app.py)
