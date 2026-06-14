#!/usr/bin/env python3
import argparse
import ipaddress
import socket
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CERTS_DIR = ROOT / "server" / "certs"
FIRMWARE_HEADER = ROOT / "src" / "generated_server_config.h"


def detect_host() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("192.0.2.1", 80))
        host = sock.getsockname()[0]
        sock.close()
        if host and not host.startswith("127."):
            return host
    except OSError:
        pass
    return "127.0.0.1"


def create_openssl_config(host: str) -> str:
    san_entries = [f"DNS.1 = {host}"]
    try:
        ipaddress.ip_address(host)
        san_entries = [f"IP.1 = {host}"]
    except ValueError:
        pass

    return "\n".join(
        [
            "[req]",
            "default_bits = 2048",
            "prompt = no",
            "default_md = sha256",
            "x509_extensions = v3_req",
            "distinguished_name = dn",
            "",
            "[dn]",
            f"CN = {host}",
            "",
            "[v3_req]",
            "subjectAltName = @alt_names",
            "extendedKeyUsage = serverAuth",
            "keyUsage = digitalSignature, keyEncipherment",
            "",
            "[alt_names]",
            *san_entries,
            "",
        ]
    )


def write_firmware_header(host: str, cert_text: str) -> None:
    content = f"""#pragma once

static const char *kServerBaseUrl = "https://{host}:8443/api";
static const char *kServerCaCert = R"CERT({cert_text})CERT";
"""
    FIRMWARE_HEADER.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local TLS assets for Zeno Pay.")
    parser.add_argument("--host", default=detect_host(), help="LAN hostname or IP the ESP32 will use.")
    parser.add_argument("--days", type=int, default=3650, help="Certificate lifetime.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    CERTS_DIR.mkdir(parents=True, exist_ok=True)

    cert_path = CERTS_DIR / "server.crt"
    key_path = CERTS_DIR / "server.key"
    config_path = CERTS_DIR / "openssl.cnf"

    config_path.write_text(create_openssl_config(args.host), encoding="utf-8")

    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            str(args.days),
            "-config",
            str(config_path),
        ],
        check=True,
    )

    cert_text = cert_path.read_text(encoding="utf-8").strip()
    write_firmware_header(args.host, cert_text)

    print(f"Certificate: {cert_path}")
    print(f"Private key: {key_path}")
    print(f"Firmware config updated: {FIRMWARE_HEADER}")
    print(f"Server URL: https://{args.host}:8443/api")


if __name__ == "__main__":
    main()
