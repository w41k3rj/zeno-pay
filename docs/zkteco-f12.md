# ZKTeco F12 Integration Notes

## Confirmed Hardware

From your screenshot and model description, the reader matches the `ZKTeco F12 RFID & Fingerprint Outdoor Slave Reader` family.

This matters because the F12 is not a generic USB scanner module. It is an `RS485 slave reader` built to work with compatible ZKTeco controllers or master devices.

## What The Project Supports Now

- The ESP32 project keeps using `AS608` for working registration and payment.
- The project now reports the `ZKTeco F12` to the server/dashboard as a powered RS485 slave reader.
- The dashboard now shows:
  - F12 model
  - RS485 transport state
  - whether direct ESP32 enrollment is supported
  - whether direct server-side matching is supported

## What The F12 Does Not Give Us Directly Here

This project does not currently enroll or match fingerprints from the F12 directly on the ESP32 or Python server.

Reason:

- The F12 is a slave reader.
- Public ZKTeco documentation for F12-style readers describes them as working with controllers/masters over RS485.
- Public ZKTeco Linux SDK documentation describes support for USB scanners like `SLK20R`, `ZK9500`, `ZK6500`, and `ZK8500R`.

That means:

- `AS608` can stay as your working local biometric sensor.
- `F12` can be wired and represented correctly in the system.
- True `server-only fingerprint registration/matching` should use a scanner with Linux SDK support, or a full ZKTeco controller architecture.

## Recommended Wiring

Your reader wires:

- `485+`
- `485-`
- `GND`
- `+12V`
- `GND`

Use them like this:

- `F12 485+` -> `RS485 converter A+`
- `F12 485-` -> `RS485 converter B-`
- `F12 GND` -> `RS485 converter GND`
- `F12 +12V` -> `12V DC power supply +`
- `F12 second GND` -> `12V DC power supply -`
- `RS485 converter TXD` -> `ESP32 RX`
- `RS485 converter RXD` -> `ESP32 TX`
- `RS485 converter GND` -> `ESP32 GND`
- `RS485 converter VCC` -> converter logic supply as required by the converter board

Important:

- All grounds must share common reference.
- The ESP32 must not take the F12 `12V` directly into GPIO.
- The reader power comes from the external `12V DC` supply, not from the ESP32.

## Best Path For True Server-Side Matching

If your goal is:

- register fingerprint on the server
- match fingerprint on the server
- pay from any machine

then the cleanest next step is one of these:

1. Add a `ZK8500R` or another ZKTeco USB scanner supported by `ZKFinger SDK for Linux`.
2. Use a full ZKTeco controller/master that officially supports the F12 over RS485.
3. Replace the F12 integration goal with a sensor whose raw template/image protocol is open enough for direct ESP32 capture.

## Why Hashing Alone Is Not Enough

The existing server stores a fingerprint hash for tracking, but a plain hash is not a biometric matcher.

For real server-side fingerprint verification, we need:

- raw image capture or raw biometric template extraction
- a matcher library/SDK that can compare new scans to stored templates
- a supported sensor/protocol that exposes that data

Without that, “same finger on another machine” cannot be made reliable just by hashing.

## Helpful Official References

These were the key references used to shape the project changes:

- ZKTeco South Africa F12 page: `https://zkteco.co.za/product/f12/`
- F12 installation manual PDF: `https://fscompras.com/wp-content/uploads/2019/05/F12-USER-MANUAL.pdf`
- ZKTeco Linux fingerprint SDK page: `https://zkteco.com/en/Biometrics_Module_SDK/ZKFinger-SDK-for-Linux`
- ZKTeco ZK8500R page: `https://zkteco.technology/en/product/reader/`
