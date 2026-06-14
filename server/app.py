#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import secrets
import smtplib
import sqlite3
import ssl
import threading
import traceback
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CERTS_DIR = BASE_DIR / "certs"
DB_PATH = DATA_DIR / "zeno_pay.db"
FINGERPRINT_INDEX_PATH = DATA_DIR / "fingerprint_hashes.json"
DEFAULT_CERT_PATH = CERTS_DIR / "server.crt"
DEFAULT_KEY_PATH = CERTS_DIR / "server.key"
PBKDF2_ROUNDS = 200_000

ACCOUNT_PREFIX = "W41K3RJ"
DEFAULT_OWNER_SUFFIX = "000000"
DEFAULT_OWNER_ACCOUNT_CODE = f"{ACCOUNT_PREFIX}{DEFAULT_OWNER_SUFFIX}"
DEFAULT_INITIAL_BALANCE = 100_000.0
MINIMUM_PAYMENT_AMOUNT = 500.0
MAX_LOCAL_SENSOR_SLOTS = 127
MACHINE_NAME = "ATC W41K3RJ BIOMETRIX"
SERVER_REGION = "ATC"
LOCATION_NAME = "ATC POINT"
LOCATION_LINK = "https://maps.google.com/?q=ATC+Arusha+Technical+College+Irrigation+Point"
DEFAULT_ALERT_EMAIL = "rustusjunior@gmail.com"
ACTIVE_WINDOW_SECONDS = 60


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ[key] = value

DASHBOARD_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    *,
    *::before,
    *::after {
      box-sizing: border-box;
    }

    html {
      height: 100%;
      scroll-behavior: smooth;
    }

    :root {
      --page: #071427;
      --page-deep: #0f3b85;
      --frame: #09111d;
      --frame-soft: #101a2a;
      --panel: #131d2d;
      --panel-strong: #172335;
      --line: rgba(255, 255, 255, 0.08);
      --line-strong: rgba(93, 198, 255, 0.28);
      --text: #eef7ff;
      --muted: #89a0bc;
      --accent: #67c7ff;
      --accent-strong: #8de5ff;
      --accent-soft: rgba(103, 199, 255, 0.16);
      --teal: #42f4ff;
      --danger: #ff7a8b;
      --warning: #f2c86b;
      --shadow: 0 24px 70px rgba(2, 10, 26, 0.52);
      --glow: 0 0 0 1px rgba(103, 199, 255, 0.18), 0 18px 40px rgba(66, 244, 255, 0.08);
    }

    * {
      box-sizing: border-box;
    }

    html {
      color-scheme: dark;
    }

    body {
      margin: 0;
      min-height: 100vh;
      height: 100%;
      overflow-x: hidden;
      overflow-y: auto;
      font-family: "Segoe UI", "Trebuchet MS", "Lucida Grande", sans-serif;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
      text-transform: uppercase;
      color: var(--text);
      background:
        radial-gradient(circle at 15% 18%, rgba(93, 198, 255, 0.22), transparent 20%),
        radial-gradient(circle at 84% 12%, rgba(66, 244, 255, 0.14), transparent 24%),
        radial-gradient(circle at 80% 78%, rgba(17, 89, 188, 0.32), transparent 25%),
        linear-gradient(135deg, var(--page) 0%, #0b2451 40%, var(--page-deep) 100%);
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    button,
    input {
      font: inherit;
    }

    .scene {
      position: relative;
      min-height: 100vh;
      padding: 14px 14px 96px;
      overflow: visible;
    }

    .scene::before,
    .scene::after {
      content: "";
      position: absolute;
      border-radius: 999px;
      filter: blur(10px);
      opacity: 0.6;
      pointer-events: none;
    }

    .scene::before {
      width: 300px;
      height: 300px;
      inset: auto auto 8% 8%;
      background: radial-gradient(circle, rgba(103, 199, 255, 0.28), transparent 68%);
    }

    .scene::after {
      width: 260px;
      height: 260px;
      inset: 8% 8% auto auto;
      background: radial-gradient(circle, rgba(66, 244, 255, 0.22), transparent 70%);
    }

    .board {
      position: relative;
      z-index: 1;
      width: min(100%, 1800px);
      margin: 0 auto;
      display: grid;
      grid-template-columns: clamp(220px, 17vw, 270px) minmax(0, 1.36fr) minmax(290px, 22vw, 360px);
      gap: 16px;
      padding: 16px;
      min-height: calc(100vh - 110px);
      border-radius: 28px;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 12%),
        linear-gradient(135deg, rgba(20, 25, 34, 0.96), rgba(10, 12, 18, 0.98));
      box-shadow: var(--shadow);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .sidebar,
    .rail-panel,
    .panel,
    .stat-card {
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.01));
      border: 1px solid var(--line);
      box-shadow: var(--glow);
    }

    .sidebar,
    .workspace,
    .rightbar {
      min-width: 0;
    }

    .sidebar {
      border-radius: 24px;
      padding: 16px 14px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-height: 0;
      overflow: auto;
      position: sticky;
      top: 14px;
      max-height: calc(100vh - 124px);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-badge {
      width: 36px;
      height: 36px;
      border-radius: 12px;
      background:
        radial-gradient(circle at 30% 30%, #daf4ff, transparent 30%),
        linear-gradient(145deg, var(--accent), var(--teal));
      box-shadow: 0 12px 28px rgba(66, 244, 255, 0.24);
    }

    .brand-copy small,
    .nav-title,
    .section-label,
    .stat-label,
    .search-label,
    .machine-label,
    .entry-time,
    .hint,
    th {
      color: var(--muted);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.72rem;
    }

    .brand-copy strong,
    .topbar h1,
    .panel h2,
    .metric,
    .contact-name {
      font-family: "Consolas", "Liberation Mono", "Courier New", monospace;
      letter-spacing: -0.03em;
    }

    .brand-copy strong {
      display: block;
      font-size: 1rem;
    }

    .search {
      display: none;
    }

    .search-box {
      height: 42px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
      color: rgba(255, 255, 255, 0.72);
      padding: 0 14px;
      display: flex;
      align-items: center;
    }

    .nav-group {
      display: grid;
      gap: 10px;
    }

    .nav-items {
      display: grid;
      gap: 8px;
    }

    .nav-link {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 11px 14px;
      border-radius: 14px;
      color: rgba(255, 255, 255, 0.74);
      border: 1px solid transparent;
      transition: transform 160ms ease, background 160ms ease, border-color 160ms ease;
    }

    .nav-link:hover {
      transform: translateX(2px);
      background: rgba(255, 255, 255, 0.04);
    }

    .nav-link.active {
      background: linear-gradient(90deg, rgba(103, 199, 255, 0.24), rgba(103, 199, 255, 0.08));
      color: var(--text);
      border-color: rgba(103, 199, 255, 0.22);
    }

    .nav-pip {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.18);
    }

    .nav-link.active .nav-pip {
      background: var(--accent);
      box-shadow: 0 0 12px rgba(103, 199, 255, 0.8);
    }

    .sidebar-foot {
      margin-top: auto;
      padding: 12px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(103, 199, 255, 0.08), rgba(66, 244, 255, 0.06));
      border: 1px solid rgba(103, 199, 255, 0.14);
    }

    .sidebar-foot p {
      margin: 6px 0 0;
      color: rgba(255, 255, 255, 0.72);
      line-height: 1.35;
      font-size: 0.84rem;
    }

    .workspace {
      display: grid;
      gap: 14px;
      min-height: 0;
      grid-template-rows: auto auto minmax(0, 1fr);
    }

    .topbar {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      padding: 0;
    }

    .crumbs {
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .topbar h1 {
      margin: 0;
      font-size: clamp(1.5rem, 1.7vw, 2rem);
    }

    .topbar-copy p {
      margin: 6px 0 0;
      max-width: 48ch;
      color: rgba(255, 255, 255, 0.72);
      line-height: 1.42;
      font-size: 0.92rem;
    }

    .top-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .chip,
    .status-pill,
    .ghost-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 30px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 0.82rem;
      font-weight: 700;
    }

    .ghost-chip {
      background: rgba(255, 255, 255, 0.04);
      color: rgba(255, 255, 255, 0.72);
    }

    .chip.live {
      background: linear-gradient(90deg, rgba(103, 199, 255, 0.22), rgba(66, 244, 255, 0.16));
      color: var(--text);
      border-color: rgba(103, 199, 255, 0.24);
    }

    .status-pill {
      padding: 6px 12px;
      min-height: 28px;
      font-size: 0.72rem;
      letter-spacing: 0.04em;
    }

    .status-pill.ok {
      color: #c8f0ff;
      background: rgba(103, 199, 255, 0.12);
      border-color: rgba(103, 199, 255, 0.22);
    }

    .status-pill.warn {
      color: #ffe18e;
      background: rgba(242, 200, 107, 0.12);
      border-color: rgba(242, 200, 107, 0.2);
    }

    .status-pill.danger {
      color: #ffb5c0;
      background: rgba(255, 122, 139, 0.12);
      border-color: rgba(255, 122, 139, 0.22);
    }

    .stats-row {
      display: grid;
      grid-template-columns: repeat(4, minmax(180px, 1fr));
      gap: 12px;
    }

    .stat-card,
    .panel,
    .rail-panel {
      border-radius: 20px;
      padding: 14px;
      position: relative;
      overflow: hidden;
      animation: rise 0.72s ease both;
    }

    .stat-card::before,
    .panel::before,
    .rail-panel::before {
      content: "";
      position: absolute;
      inset: 0 auto auto 0;
      width: 100%;
      height: 1px;
      background: linear-gradient(90deg, rgba(103, 199, 255, 0.34), transparent 60%);
      opacity: 0.9;
    }

    .stat-card:nth-child(1) { animation-delay: 0.04s; }
    .stat-card:nth-child(2) { animation-delay: 0.08s; }
    .stat-card:nth-child(3) { animation-delay: 0.12s; }
    .stat-card:nth-child(4) { animation-delay: 0.16s; }

    .stat-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }

    .metric {
      margin: 10px 0 4px;
      font-size: clamp(1.35rem, 1.5vw, 1.8rem);
    }

    .stat-note {
      margin: 0;
      color: rgba(255, 255, 255, 0.66);
      font-size: 0.82rem;
      line-height: 1.35;
    }

    .content-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.16fr) minmax(320px, 0.84fr);
      gap: 14px;
      min-height: 0;
      align-content: start;
    }

    .panel-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }

    .panel-head h2 {
      margin: 6px 0 0;
      font-size: 1.04rem;
    }

    .overview-panel {
      min-height: 0;
    }

    .overview-split {
      display: grid;
      grid-template-columns: 210px minmax(0, 1fr);
      gap: 12px;
      align-items: stretch;
    }

    .ring-card {
      display: grid;
      justify-items: center;
      align-content: start;
      gap: 10px;
      padding: 10px 6px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid var(--line);
    }

    .ring {
      --coverage-angle: 0deg;
      width: 160px;
      height: 160px;
      border-radius: 50%;
      padding: 16px;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at center, rgba(66, 244, 255, 0.16), transparent 55%),
        conic-gradient(var(--accent) 0deg, var(--teal) var(--coverage-angle), rgba(255, 255, 255, 0.08) var(--coverage-angle), rgba(255, 255, 255, 0.08) 360deg);
      box-shadow: inset 0 0 20px rgba(66, 244, 255, 0.12), 0 12px 28px rgba(0, 0, 0, 0.22);
    }

    .ring-center {
      width: 100%;
      height: 100%;
      border-radius: 50%;
      background: linear-gradient(180deg, #121720, #0b0f16);
      border: 1px solid rgba(255, 255, 255, 0.08);
      display: grid;
      place-items: center;
      text-align: center;
      padding: 18px;
    }

    .ring-center strong {
      display: block;
      font-size: 2rem;
      line-height: 1;
    }

    .ring-center span {
      display: block;
      margin-top: 6px;
      color: rgba(255, 255, 255, 0.68);
      font-size: 0.82rem;
      line-height: 1.35;
    }

    .ring-note {
      margin: 0;
      color: rgba(255, 255, 255, 0.72);
      font-size: 0.82rem;
      line-height: 1.35;
      text-align: center;
    }

    .machine-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      align-content: start;
    }

    .machine-item,
    .mini-card,
    .entry,
    .contact-item {
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
    }

    .machine-item {
      position: relative;
      overflow: hidden;
      padding: 12px;
      min-height: 88px;
      border-radius: 24px;
      display: grid;
      align-content: start;
    }

    .machine-item::before {
      content: "";
      position: absolute;
      width: 56px;
      height: 56px;
      top: -12px;
      right: -12px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(103, 199, 255, 0.24), transparent 72%);
      pointer-events: none;
    }

    .machine-item.tone-ok::before {
      background: radial-gradient(circle, rgba(66, 244, 255, 0.22), transparent 72%);
    }

    .machine-item.tone-warn::before {
      background: radial-gradient(circle, rgba(242, 200, 107, 0.24), transparent 72%);
    }

    .machine-item.tone-danger::before {
      background: radial-gradient(circle, rgba(255, 122, 139, 0.26), transparent 72%);
    }

    .machine-item p {
      margin: 0;
    }

    .machine-value {
      margin-top: 9px;
      font-size: 0.92rem;
      line-height: 1.35;
      font-weight: 700;
      word-break: normal;
      overflow-wrap: anywhere;
      hyphens: auto;
      text-wrap: balance;
    }

    .machine-value a {
      color: #b7ebff;
      text-decoration: underline;
      text-decoration-color: rgba(183, 235, 255, 0.35);
    }

    .signals-panel {
      display: grid;
      gap: 12px;
      align-content: start;
    }

    .mini-cards {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .mini-card {
      padding: 12px;
    }

    .mini-card span {
      display: block;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.4;
    }

    .mini-card strong {
      display: block;
      margin-top: 10px;
      font-size: 1rem;
      line-height: 1.45;
      word-break: break-word;
    }

    .spark-card {
      padding: 16px;
      border-radius: 20px;
      background: linear-gradient(180deg, rgba(66, 244, 255, 0.08), rgba(66, 244, 255, 0.02));
      border: 1px solid rgba(66, 244, 255, 0.14);
    }

    .spark-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }

    .spark-head span {
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .spark-head strong {
      font-size: 0.96rem;
    }

    .sparkline {
      height: 108px;
      border-radius: 18px;
      overflow: hidden;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02)),
        linear-gradient(180deg, rgba(0, 0, 0, 0.14), rgba(0, 0, 0, 0.04));
      border: 1px solid rgba(255, 255, 255, 0.05);
    }

    .spark-placeholder,
    .empty-state {
      height: 100%;
      display: grid;
      place-items: center;
      color: rgba(255, 255, 255, 0.55);
      font-size: 0.9rem;
      text-align: center;
      padding: 18px;
    }

    .cta-card {
      display: grid;
      gap: 8px;
      padding: 14px;
      border-radius: 20px;
      background:
        radial-gradient(circle at top right, rgba(103, 199, 255, 0.22), transparent 35%),
        linear-gradient(135deg, rgba(17, 73, 144, 0.26), rgba(17, 103, 149, 0.18));
      border: 1px solid rgba(103, 199, 255, 0.18);
      transition: transform 160ms ease, box-shadow 160ms ease;
    }

    .cta-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 18px 36px rgba(34, 136, 201, 0.16);
    }

    .cta-card .pill {
      width: fit-content;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.1);
      color: #d9f4ff;
      font-size: 0.74rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .cta-card strong {
      font-size: 1.18rem;
    }

    .cta-card p {
      margin: 0;
      color: rgba(255, 255, 255, 0.74);
      line-height: 1.35;
      font-size: 0.84rem;
    }

    .table-panel {
      min-height: 0;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
    }

    .table-wrap {
      overflow-x: auto;
      overflow-y: auto;
      max-height: 340px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.018);
      scroll-padding: 12px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 620px;
    }

    th,
    td {
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      vertical-align: top;
    }

    td {
      color: rgba(255, 255, 255, 0.88);
      font-size: 0.94rem;
    }

    tr:last-child td {
      border-bottom: none;
    }

    .row-name {
      display: grid;
      gap: 6px;
    }

    .row-name strong {
      font-size: 0.96rem;
    }

    .row-sub {
      color: var(--muted);
      font-size: 0.84rem;
    }

    .amount.out {
      color: #8eeaff;
      font-weight: 700;
    }

    .rightbar {
      display: grid;
      gap: 12px;
      align-content: stretch;
      min-height: 0;
      grid-template-rows: repeat(3, minmax(0, 1fr));
    }

    .rail-panel {
      border-radius: 20px;
      padding: 14px;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      min-height: 0;
    }

    .feed-list,
    .contact-list {
      display: grid;
      gap: 10px;
      overflow: auto;
      padding-right: 4px;
    }

    .entry,
    .contact-item {
      padding: 12px;
    }

    .entry-top,
    .contact-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
    }

    .entry-title,
    .contact-name {
      margin: 0;
      font-size: 0.95rem;
    }

    .entry-copy,
    .contact-copy {
      margin: 8px 0 0;
      color: rgba(255, 255, 255, 0.68);
      line-height: 1.5;
      font-size: 0.88rem;
    }

    .entry-time {
      margin-top: 10px;
    }

    .contact-item {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .avatar {
      width: 40px;
      height: 40px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      font-size: 0.9rem;
      font-weight: 700;
      color: #f3fbff;
      background: linear-gradient(135deg, rgba(103, 199, 255, 0.56), rgba(66, 244, 255, 0.42));
      box-shadow: inset 0 0 18px rgba(255, 255, 255, 0.08);
      flex: none;
    }

    .contact-copy {
      margin: 4px 0 0;
    }

    .contact-balance {
      margin-left: auto;
      color: #cdefff;
      font-weight: 700;
      white-space: nowrap;
    }

    .float-chip {
      position: fixed;
      z-index: 2;
      min-height: 48px;
      border-radius: 18px;
      border: 1px solid rgba(14, 24, 18, 0.08);
      background: rgba(240, 255, 247, 0.78);
      color: #0a1423;
      box-shadow: 0 18px 36px rgba(17, 67, 122, 0.22);
      backdrop-filter: blur(12px);
    }

    * {
      scrollbar-width: thin;
      scrollbar-color: rgba(103, 199, 255, 0.36) rgba(255, 255, 255, 0.05);
    }

    *::-webkit-scrollbar {
      width: 10px;
      height: 10px;
    }

    *::-webkit-scrollbar-track {
      background: rgba(255, 255, 255, 0.04);
      border-radius: 999px;
    }

    *::-webkit-scrollbar-thumb {
      background: linear-gradient(180deg, rgba(103, 199, 255, 0.62), rgba(66, 244, 255, 0.42));
      border-radius: 999px;
      border: 2px solid rgba(8, 15, 27, 0.72);
    }

    .visit-chip {
      left: 12px;
      bottom: 12px;
      display: inline-flex;
      align-items: center;
      padding: 0 18px;
      font-weight: 700;
    }

    .refresh-chip {
      right: 12px;
      bottom: 12px;
      width: 52px;
      padding: 0;
      display: grid;
      place-items: center;
      cursor: pointer;
      font-weight: 700;
    }

    @keyframes rise {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @media (min-width: 1360px) {
      .board {
        gap: 20px;
        padding: 20px;
      }

      .sidebar {
        gap: 18px;
        padding: 20px 18px;
      }

      .brand {
        gap: 14px;
      }

      .brand-badge {
        width: 42px;
        height: 42px;
        border-radius: 14px;
      }

      .brand-copy small,
      .nav-title,
      .section-label,
      .stat-label,
      .search-label,
      .machine-label,
      .entry-time,
      .hint,
      th {
        font-size: 0.78rem;
      }

      .brand-copy strong {
        font-size: 1.14rem;
      }

      .nav-link {
        padding: 13px 16px;
        font-size: 0.97rem;
      }

      .sidebar-foot {
        padding: 14px;
      }

      .sidebar-foot p {
        font-size: 0.92rem;
      }

      .workspace {
        gap: 16px;
      }

      .topbar {
        gap: 16px;
      }

      .crumbs {
        font-size: 0.88rem;
      }

      .topbar h1 {
        font-size: clamp(1.95rem, 2vw, 2.45rem);
      }

      .topbar-copy p {
        max-width: 56ch;
        font-size: 1rem;
      }

      .chip,
      .status-pill,
      .ghost-chip {
        min-height: 34px;
        padding: 0 14px;
        font-size: 0.88rem;
      }

      .status-pill {
        padding: 7px 13px;
        min-height: 30px;
      }

      .stat-card,
      .panel,
      .rail-panel {
        padding: 18px;
      }

      .metric {
        font-size: clamp(1.65rem, 1.7vw, 2.15rem);
      }

      .stat-note {
        font-size: 0.9rem;
      }

      .content-grid {
        gap: 16px;
      }

      .panel-head h2 {
        font-size: 1.14rem;
      }

      .ring {
        width: 176px;
        height: 176px;
      }

      .ring-center strong {
        font-size: 2.2rem;
      }

      .ring-note {
        font-size: 0.9rem;
      }

      .machine-item {
        padding: 14px;
        min-height: 98px;
      }

      .machine-value {
        font-size: 1rem;
      }

      .mini-card {
        padding: 14px;
      }

      .mini-card span,
      .spark-head span {
        font-size: 0.88rem;
      }

      .mini-card strong,
      .spark-head strong {
        font-size: 1.08rem;
      }

      .spark-card,
      .cta-card {
        padding: 18px;
      }

      .cta-card strong {
        font-size: 1.26rem;
      }

      .cta-card p {
        font-size: 0.9rem;
      }

      .table-wrap {
        max-height: 380px;
      }

      th,
      td {
        padding: 12px 14px;
      }

      td,
      .row-name strong,
      .entry-title,
      .contact-name {
        font-size: 0.99rem;
      }

      .row-sub,
      .entry-copy,
      .contact-copy {
        font-size: 0.9rem;
      }

      .entry,
      .contact-item {
        padding: 14px;
      }

      .contact-balance {
        font-size: 1rem;
      }
    }

    @media (max-width: 1480px) {
      .board {
        grid-template-columns: clamp(220px, 18vw, 250px) minmax(0, 1fr);
      }

      .rightbar {
        grid-column: 1 / -1;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        grid-template-rows: none;
      }
    }

    @media (max-width: 1280px) {
      .stats-row {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .content-grid {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 1080px) {
      .board {
        grid-template-columns: 1fr;
      }

      .sidebar {
        position: static;
        max-height: none;
      }

      .nav-items {
        display: flex;
        gap: 10px;
        overflow-x: auto;
        padding-bottom: 4px;
        scrollbar-width: none;
      }

      .nav-items::-webkit-scrollbar {
        display: none;
      }

      .nav-link {
        flex: 0 0 auto;
        min-width: 170px;
      }

      .scene {
        padding: 12px 12px 88px;
      }

      .rightbar {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 860px) {
      .board {
        padding: 14px;
      }

      .stats-row {
        grid-template-columns: 1fr;
      }

      .mini-cards,
      .machine-grid,
      .overview-split {
        grid-template-columns: 1fr;
      }

      .topbar {
        flex-direction: column;
      }

      .top-actions {
        justify-content: flex-start;
      }

      .table-wrap {
        max-height: 300px;
      }

      .visit-chip {
        left: 16px;
      }
    }

    @media (max-width: 640px) {
      .scene {
        padding: 10px 10px 88px;
      }

      .board {
        border-radius: 22px;
        padding: 12px;
      }

      .sidebar,
      .stat-card,
      .panel,
      .rail-panel {
        border-radius: 18px;
      }

      .nav-link {
        min-width: 150px;
        padding: 10px 12px;
      }

      .ring {
        width: 144px;
        height: 144px;
      }

      table {
        min-width: 540px;
      }

      .visit-chip {
        max-width: calc(100vw - 94px);
      }
    }
  </style>
</head>
<body>
  <div class="scene">
    <main class="board">
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-badge" aria-hidden="true"></div>
          <div class="brand-copy">
            <small>ATC BIOMETRIX</small>
            <strong>W41K3RJ Console</strong>
          </div>
        </div>

        <div class="search">
          <span class="search-label">Search</span>
          <div class="search-box">Machine, account, reference</div>
        </div>

        <div class="nav-group">
          <p class="nav-title">Dashboards</p>
          <div class="nav-items">
            <a class="nav-link active" href="/">
              <span>Overview</span>
              <span class="nav-pip"></span>
            </a>
            <a class="nav-link" href="#accounts-panel">
              <span>Accounts</span>
              <span class="nav-pip"></span>
            </a>
            <a class="nav-link" href="#payments-panel">
              <span>Payments</span>
              <span class="nav-pip"></span>
            </a>
          </div>
        </div>

        <div class="nav-group">
          <p class="nav-title">Machine</p>
          <div class="nav-items">
            <a class="nav-link" href="#machine-overview">
              <span>Sensor status</span>
              <span class="nav-pip"></span>
            </a>
            <a class="nav-link" href="#notifications-panel">
              <span>Notifications</span>
              <span class="nav-pip"></span>
            </a>
            <a class="nav-link" href="__LOCATION_LINK__" target="_blank" rel="noreferrer">
              <span>Map link</span>
              <span class="nav-pip"></span>
            </a>
          </div>
        </div>

        <div class="sidebar-foot">
          <small class="nav-title">Live location</small>
          <p>LIVE FROM __LOCATION_NAME__.</p>
        </div>
      </aside>

      <section class="workspace">
        <div class="topbar">
          <div class="topbar-copy">
            <p class="crumbs">ATC POINT / LIVE BOARD</p>
            <h1>ATC W41K3RJ BIOMETRIX</h1>
            <p>FAST VIEW FOR HEARTBEAT, ENROLLMENT, PAYMENTS, AND BALANCES.</p>
          </div>
          <div class="top-actions">
            <span class="chip live">Live feed</span>
            <span class="ghost-chip" id="last-update-chip">Waiting for sync</span>
          </div>
        </div>

        <section class="stats-row">
          <article class="stat-card">
            <div class="stat-top">
              <span class="stat-label">Registered accounts</span>
              <span class="status-pill ok">Ready</span>
            </div>
            <p class="metric" id="registered-count">0</p>
            <p class="stat-note" id="registered-note">No customer records yet.</p>
          </article>

          <article class="stat-card">
            <div class="stat-top">
              <span class="stat-label">Customer float</span>
              <span class="status-pill ok">Wallets</span>
            </div>
            <p class="metric" id="total-balance">TZS 0.00</p>
            <p class="stat-note" id="float-note">Waiting for customer balances.</p>
          </article>

          <article class="stat-card">
            <div class="stat-top">
              <span class="stat-label">Owner wallet</span>
              <span class="status-pill ok">Collection</span>
            </div>
            <p class="metric" id="owner-balance">TZS 0.00</p>
            <p class="stat-note" id="owner-note">Owner account will rise after payments.</p>
          </article>

          <article class="stat-card">
            <div class="stat-top">
              <span class="stat-label">Enrollment rate</span>
              <span class="status-pill warn" id="coverage-status">Pending</span>
            </div>
            <p class="metric" id="coverage-rate">0%</p>
            <p class="stat-note" id="coverage-note-small">No fingerprint coverage yet.</p>
          </article>
        </section>

        <section class="content-grid">
          <section class="panel overview-panel" id="machine-overview">
            <div class="panel-head">
              <div>
                <p class="section-label">Machine</p>
                <h2>ATC POINT PULSE</h2>
              </div>
              <span class="chip" id="machine-state-chip">Waiting</span>
            </div>

            <div class="overview-split">
              <div class="ring-card">
                <div class="ring" id="coverage-ring">
                  <div class="ring-center">
                    <div>
                      <strong id="coverage-value">0%</strong>
                      <span>READY</span>
                    </div>
                  </div>
                </div>
                <p class="ring-note" id="coverage-note">Waiting for customer data.</p>
              </div>

              <div class="machine-grid" id="machine-grid"></div>
            </div>
          </section>

          <section class="panel signals-panel">
            <div class="panel-head">
              <div>
                <p class="section-label">Fast view</p>
                <h2>STATUS + SHORTCUTS</h2>
              </div>
            </div>

            <div class="mini-cards">
              <article class="mini-card">
                <span>Minimum payment</span>
                <strong>TZS 500.00</strong>
              </article>
              <article class="mini-card">
                <span>Owner account</span>
                <strong id="owner-account-code">W41K3RJ000000</strong>
              </article>
            </div>

            <div class="spark-card">
              <div class="spark-head">
                <span>Cash flow pulse</span>
                <strong id="payments-count">0 payments</strong>
              </div>
              <div class="sparkline" id="payments-sparkline">
                <div class="spark-placeholder">No payment pattern yet.</div>
              </div>
            </div>

            <a class="cta-card" href="__LOCATION_LINK__" target="_blank" rel="noreferrer">
              <span class="pill">Map link</span>
              <strong>OPEN ATC POINT</strong>
              <p>OPEN THE MAP AND CHECK THE INSTALL POINT.</p>
            </a>
          </section>

          <section class="panel table-panel" id="accounts-panel">
            <div class="panel-head">
              <div>
                <p class="section-label">Accounts</p>
                <h2>REGISTERED USERS</h2>
              </div>
              <span class="chip">Prefix __ACCOUNT_PREFIX__</span>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Phone</th>
                    <th>Local slot</th>
                    <th>Status</th>
                    <th>Balance</th>
                  </tr>
                </thead>
                <tbody id="accounts-body"></tbody>
              </table>
            </div>
          </section>

          <section class="panel table-panel" id="payments-panel">
            <div class="panel-head">
              <div>
                <p class="section-label">Payments</p>
                <h2>RECENT TRANSFERS</h2>
              </div>
              <span class="chip" id="machine-ip">Waiting for IP</span>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>From</th>
                    <th>To</th>
                    <th>Amount</th>
                    <th>Reference</th>
                  </tr>
                </thead>
                <tbody id="transactions-body"></tbody>
              </table>
            </div>
          </section>
        </section>
      </section>

      <aside class="rightbar">
        <section class="rail-panel" id="notifications-panel">
          <div class="panel-head">
            <div>
              <p class="section-label">Notifications</p>
              <h2>SYSTEM FEED</h2>
            </div>
          </div>
          <div class="feed-list" id="notifications-list"></div>
        </section>

        <section class="rail-panel">
          <div class="panel-head">
            <div>
              <p class="section-label">Activities</p>
              <h2>RECENT ACTIONS</h2>
            </div>
          </div>
          <div class="feed-list" id="activities-list"></div>
        </section>

        <section class="rail-panel">
          <div class="panel-head">
            <div>
              <p class="section-label">Contacts</p>
              <h2>TOP WALLETS</h2>
            </div>
          </div>
          <div class="contact-list" id="contacts-list"></div>
        </section>
      </aside>
    </main>

    <a class="float-chip visit-chip" href="__LOCATION_LINK__" target="_blank" rel="noreferrer">MAP</a>
    <button class="float-chip refresh-chip" id="manual-refresh" type="button">Sync</button>
  </div>

  <script>
    const currency = (value) => `TZS ${Number(value || 0).toFixed(2)}`;

    function escapeHtml(value) {
      const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      };
      return String(value ?? "").replace(/[&<>"']/g, (char) => map[char]);
    }

    function statusPill(label, tone) {
      return `<span class="status-pill ${tone}">${escapeHtml(label)}</span>`;
    }

    function compactWords(value) {
      return String(value ?? "")
        .trim()
        .replace(/ATC ARUSHA TECHNICAL(?: COLLEGE)?\\s*-\\s*IRRIGATION POINT/ig, "ATC POINT")
        .replace(/ARUSHA TECHNICAL(?: COLLEGE)?/ig, "ATC")
        .replace(/W41K3RJ BIOMETRIC PAYMENT/ig, "ATC W41K3RJ BIOMETRIX")
        .replace(/TERMINAL[- ]ARUSHA[- ]01/ig, "ATC POINT")
        .replace(/ZKTECO F12 RS485 SLAVE READER/ig, "F12 RS485")
        .replace(/\\s+/g, " ")
        .trim();
    }

    function upperCompact(value) {
      return compactWords(value).toUpperCase();
    }

    function relativeTime(value) {
      if (!value) {
        return "Waiting";
      }

      const now = Date.now();
      const then = new Date(value).getTime();
      const diffSeconds = Math.max(0, Math.round((now - then) / 1000));
      if (diffSeconds < 60) {
        return `${diffSeconds}s ago`;
      }
      if (diffSeconds < 3600) {
        return `${Math.round(diffSeconds / 60)}m ago`;
      }
      return `${Math.round(diffSeconds / 3600)}h ago`;
    }

    function initials(name) {
      const parts = String(name || "Customer").trim().split(/\\s+/).filter(Boolean).slice(0, 2);
      return parts.map((part) => part[0]?.toUpperCase() || "").join("") || "CU";
    }

    function createSparkline(values) {
      if (!values.length) {
        return `<div class="spark-placeholder">No approved transfers yet.</div>`;
      }

      const width = 420;
      const height = 126;
      const max = Math.max(...values, 1);
      const min = Math.min(...values, 0);
      const range = Math.max(max - min, 1);
      const step = values.length > 1 ? width / (values.length - 1) : width;
      const points = values.map((value, index) => {
        const x = index * step;
        const y = height - ((value - min) / range) * (height - 18) - 9;
        return `${x},${y}`;
      }).join(" ");

      const areaPoints = `0,${height} ${points} ${width},${height}`;

      return `
        <svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="sparkArea" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="rgba(39,230,167,0.42)"></stop>
              <stop offset="100%" stop-color="rgba(39,230,167,0.02)"></stop>
            </linearGradient>
            <linearGradient id="sparkLine" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="#b4ff45"></stop>
              <stop offset="100%" stop-color="#27e6a7"></stop>
            </linearGradient>
          </defs>
          <path d="M ${areaPoints}" fill="url(#sparkArea)"></path>
          <polyline points="${points}" fill="none" stroke="url(#sparkLine)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
        </svg>
      `;
    }

    function renderCoverage(users) {
      const total = users.length;
      const registered = users.filter((user) => user.registered).length;
      const coverage = total ? Math.round((registered / total) * 100) : 0;
      const ring = document.getElementById("coverage-ring");
      const coverageStatus = document.getElementById("coverage-status");
      const tone = coverage >= 75 ? "ok" : (coverage >= 35 ? "warn" : "danger");

      ring.style.setProperty("--coverage-angle", `${coverage * 3.6}deg`);
      document.getElementById("coverage-value").textContent = `${coverage}%`;
      document.getElementById("coverage-rate").textContent = `${coverage}%`;
      document.getElementById("coverage-note").textContent = total
        ? `${registered}/${total} READY ON SERVER.`
        : "WAITING FOR FIRST ENROLLMENT.";
      document.getElementById("coverage-note-small").textContent = total
        ? `${Math.max(total - registered, 0)} LEFT TO ENROLL.`
        : "NO COVERAGE YET.";
      coverageStatus.className = `status-pill ${tone}`;
      coverageStatus.textContent = coverage >= 75 ? "HIGH" : (coverage >= 35 ? "MID" : "LOW");
    }

    function renderMachine(machine, ownerAccount) {
      const grid = document.getElementById("machine-grid");
      const machineChip = document.getElementById("machine-state-chip");
      const ownerCode = ownerAccount?.account_code || machine?.owner_account_code || "W41K3RJ000000";
      document.getElementById("owner-account-code").textContent = ownerCode;

      if (!machine) {
        grid.innerHTML = `
          <article class="machine-item">
            <p class="machine-label">Status</p>
            <p class="machine-value">${statusPill("Waiting for heartbeat", "warn")}</p>
          </article>
        `;
        machineChip.textContent = "Waiting";
        machineChip.className = "chip";
        document.getElementById("machine-ip").textContent = "Waiting for IP";
        return;
      }

      const activeTone = machine.active ? "ok" : "danger";
      machineChip.textContent = machine.active ? "LIVE" : "OFFLINE";
      machineChip.className = `chip ${machine.active ? "live" : ""}`.trim();
      document.getElementById("machine-ip").textContent = upperCompact(machine.ip_address || "NO IP");

      const cards = [
        { label: "UNIT", value: escapeHtml(upperCompact(machine.machine_name || "NOT REPORTED")), tone: "accent" },
        { label: "POINT", value: escapeHtml(upperCompact(machine.terminal_id || "ATC POINT")), tone: "accent" },
        { label: "PULSE", value: statusPill(machine.active ? "LIVE" : "STALE", activeTone), tone: activeTone },
        { label: "LAST SYNC", value: `${escapeHtml(relativeTime(machine.last_seen_at).toUpperCase())}<br><span class="row-sub">${escapeHtml(machine.last_seen_at ? new Date(machine.last_seen_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "WAITING")}</span>`, tone: "accent" },
        { label: "WIFI", value: statusPill(machine.wifi_connected ? "ONLINE" : "OFFLINE", machine.wifi_connected ? "ok" : "danger"), tone: machine.wifi_connected ? "ok" : "danger" },
        { label: "AS608", value: statusPill(machine.local_sensor_active ? "READY" : "OFF", machine.local_sensor_active ? "ok" : "warn"), tone: machine.local_sensor_active ? "ok" : "warn" },
        { label: "F12 LINK", value: `${statusPill(machine.remote_sensor_active ? "PWR" : "OFF", machine.remote_sensor_active ? "ok" : "warn")} ${statusPill(machine.remote_sensor_transport_ready ? "RS485" : "HOLD", machine.remote_sensor_transport_ready ? "ok" : "warn")}`, tone: machine.remote_sensor_active && machine.remote_sensor_transport_ready ? "ok" : "warn" },
        { label: "MODE", value: `${statusPill(machine.remote_enrollment_supported ? "ENROLL" : "NO ENROLL", machine.remote_enrollment_supported ? "ok" : "warn")} ${statusPill(machine.remote_server_match_supported ? "MATCH" : "NO MATCH", machine.remote_server_match_supported ? "ok" : "danger")}`, tone: machine.remote_server_match_supported ? "ok" : "warn" },
        { label: "SITE", value: `<a href="${escapeHtml(machine.location_link || "__LOCATION_LINK__")}" target="_blank" rel="noreferrer">${escapeHtml(upperCompact(machine.location_name || "__LOCATION_NAME__"))}</a>`, tone: "accent" },
      ];

      grid.innerHTML = cards.map(({ label, value, tone }) => `
        <article class="machine-item ${tone ? `tone-${tone}` : ""}">
          <p class="machine-label">${label}</p>
          <p class="machine-value">${value}</p>
        </article>
      `).join("");
    }

    function renderAccounts(users) {
      const body = document.getElementById("accounts-body");
      if (!users.length) {
        body.innerHTML = `<tr><td colspan="5"><div class="empty-state">No customer accounts yet.</div></td></tr>`;
        return;
      }

      body.innerHTML = users.map((user) => `
        <tr>
          <td>
            <div class="row-name">
              <strong>${escapeHtml(user.account_code)}</strong>
              <span class="row-sub">${escapeHtml(user.name)}</span>
            </div>
          </td>
          <td>${escapeHtml(user.phone_number || "-")}</td>
          <td>${escapeHtml(user.local_sensor_slot ?? "-")}</td>
          <td>${statusPill(user.registered ? (user.fingerprint_source || "Ready") : "Needs fingerprint", user.registered ? "ok" : "warn")}</td>
          <td>${currency(user.balance)}</td>
        </tr>
      `).join("");
    }

    function renderTransactions(items) {
      const body = document.getElementById("transactions-body");
      if (!items.length) {
        body.innerHTML = `<tr><td colspan="5"><div class="empty-state">No successful payments yet.</div></td></tr>`;
        return;
      }

      body.innerHTML = items.map((item) => `
        <tr>
          <td>${escapeHtml(new Date(item.created_at).toLocaleString())}</td>
          <td>${escapeHtml(item.account_code || "-")}</td>
          <td>${escapeHtml(item.owner_account_code || "-")}</td>
          <td class="amount out">+${currency(item.amount)}</td>
          <td>${escapeHtml(item.reference || "-")}</td>
        </tr>
      `).join("");
    }

    function renderNotifications(data) {
      const machine = data.machine;
      const users = data.users || [];
      const transactions = data.transactions || [];
      const registered = users.filter((user) => user.registered).length;
      const list = document.getElementById("notifications-list");

      const items = [
        {
          title: machine?.active ? "HEARTBEAT LIVE" : "HEARTBEAT STALE",
          copy: machine?.active
            ? `${upperCompact(machine.machine_name || "MACHINE")} REPORTED ${relativeTime(machine.last_seen_at).toUpperCase()}.`
            : "NO FRESH MACHINE HEARTBEAT.",
          tone: machine?.active ? "ok" : "danger",
          time: machine?.last_seen_at,
        },
        {
          title: machine?.wifi_connected ? "WIFI ONLINE" : "WIFI OFFLINE",
          copy: machine?.wifi_connected
            ? `${upperCompact(machine.terminal_id || "ATC POINT")} ON ${upperCompact(machine.wifi_ssid || "NETWORK")}.`
            : "SYNC AND PAYMENTS ARE PAUSED.",
          tone: machine?.wifi_connected ? "ok" : "warn",
          time: machine?.last_seen_at,
        },
        {
          title: `${registered} READY ACCOUNT(S)`,
          copy: `${Math.max(users.length - registered, 0)} STILL NEED ENROLLMENT.`,
          tone: registered === users.length && users.length ? "ok" : "warn",
          time: new Date().toISOString(),
        },
        {
          title: `${transactions.length} PAYMENT(S) RECORDED`,
          copy: transactions.length
            ? `LAST REF: ${transactions[0].reference || "N/A"}.`
            : "PAYMENTS WILL APPEAR HERE.",
          tone: transactions.length ? "ok" : "warn",
          time: transactions[0]?.created_at || new Date().toISOString(),
        },
      ];

      list.innerHTML = items.map((item) => `
        <article class="entry">
          <div class="entry-top">
            <p class="entry-title">${escapeHtml(item.title)}</p>
            ${statusPill(item.tone === "danger" ? "Alert" : (item.tone === "warn" ? "Watch" : "Good"), item.tone)}
          </div>
          <p class="entry-copy">${escapeHtml(item.copy)}</p>
          <p class="entry-time">${escapeHtml(relativeTime(item.time))}</p>
        </article>
      `).join("");
    }

    function renderActivities(items) {
      const list = document.getElementById("activities-list");
      if (!items.length) {
        list.innerHTML = `
          <article class="entry">
            <p class="entry-title">No transfers yet</p>
            <p class="entry-copy">Approve the first biometric payment to populate the activity feed.</p>
            <p class="entry-time">Waiting</p>
          </article>
        `;
        return;
      }

      list.innerHTML = items.slice(0, 5).map((item) => `
        <article class="entry">
          <div class="entry-top">
            <p class="entry-title">${escapeHtml(item.account_code || "Unknown account")}</p>
            ${statusPill("Paid", "ok")}
          </div>
          <p class="entry-copy">${currency(item.amount)} moved to ${escapeHtml(item.owner_account_code || "owner wallet")}.</p>
          <p class="entry-time">${escapeHtml(new Date(item.created_at).toLocaleString())}</p>
        </article>
      `).join("");
    }

    function renderContacts(users) {
      const list = document.getElementById("contacts-list");
      if (!users.length) {
        list.innerHTML = `
          <article class="contact-item">
            <div class="avatar">NA</div>
            <div>
              <p class="contact-name">No accounts yet</p>
              <p class="contact-copy">Customer balances will appear here after registration.</p>
            </div>
          </article>
        `;
        return;
      }

      const topUsers = [...users]
        .sort((a, b) => Number(b.balance) - Number(a.balance))
        .slice(0, 5);

      list.innerHTML = topUsers.map((user) => `
        <article class="contact-item">
          <div class="avatar">${escapeHtml(initials(user.name || user.account_code))}</div>
          <div>
            <p class="contact-name">${escapeHtml(user.name || user.account_code)}</p>
            <p class="contact-copy">${escapeHtml(user.account_code)}${user.phone_number ? ` / ${escapeHtml(user.phone_number)}` : ""}</p>
          </div>
          <span class="contact-balance">${currency(user.balance)}</span>
        </article>
      `).join("");
    }

    function updateSummary(data) {
      const users = data.users || [];
      const transactions = data.transactions || [];
      const machine = data.machine;
      const registered = users.filter((user) => user.registered).length;
      const totalBalance = users.reduce((sum, user) => sum + Number(user.balance || 0), 0);
      const coverage = users.length ? Math.round((registered / users.length) * 100) : 0;

      document.getElementById("registered-count").textContent = registered;
      document.getElementById("registered-note").textContent = users.length
        ? `${users.length} USER ACCOUNT(S) ON SERVER.`
        : "NO USER ACCOUNTS YET.";
      document.getElementById("total-balance").textContent = currency(totalBalance);
      document.getElementById("float-note").textContent = users.length
        ? `AVG WALLET ${currency(totalBalance / Math.max(users.length, 1))}.`
        : "WAITING FOR BALANCES.";
      document.getElementById("owner-balance").textContent = currency(data.owner_account?.balance || 0);
      document.getElementById("owner-note").textContent = `OWNER ${data.owner_account?.account_code || "W41K3RJ000000"}.`;
      document.getElementById("payments-count").textContent = `${transactions.length} payment(s)`;
      document.getElementById("last-update-chip").textContent = machine?.last_seen_at
        ? `Synced ${relativeTime(machine.last_seen_at)}`
        : "Waiting for sync";
      document.getElementById("payments-sparkline").innerHTML = createSparkline(
        [...transactions].reverse().map((item) => Number(item.amount || 0)),
      );

      if (!users.length) {
        document.getElementById("coverage-rate").textContent = "0%";
      } else if (coverage === 100) {
        document.getElementById("coverage-note-small").textContent = "All customer accounts are fingerprint ready.";
      }
    }

    async function refresh() {
      try {
        const response = await fetch("/api/state", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Request failed with ${response.status}`);
        }

        const data = await response.json();
        updateSummary(data);
        renderCoverage(data.users || []);
        renderMachine(data.machine, data.owner_account);
        renderAccounts(data.users || []);
        renderTransactions(data.transactions || []);
        renderNotifications(data);
        renderActivities(data.transactions || []);
        renderContacts(data.users || []);
      } catch (error) {
        document.getElementById("last-update-chip").textContent = "Dashboard offline";
      }
    }

    document.getElementById("manual-refresh").addEventListener("click", refresh);
    refresh();
    setInterval(refresh, 1500);
  </script>
</body>
</html>
"""


def build_dashboard_html() -> str:
    return (
        DASHBOARD_HTML_TEMPLATE.replace("__TITLE__", MACHINE_NAME)
        .replace("__LOCATION_NAME__", LOCATION_NAME)
        .replace("__LOCATION_LINK__", LOCATION_LINK)
        .replace("__SERVER_REGION__", SERVER_REGION)
        .replace("__ACCOUNT_PREFIX__", ACCOUNT_PREFIX)
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_recent(value: str | None, window_seconds: int = ACTIVE_WINDOW_SECONDS) -> bool:
    moment = parse_utc(value)
    if not moment:
        return False
    return datetime.now(timezone.utc) - moment <= timedelta(seconds=window_seconds)


def money_to_cents(amount: Any) -> int:
    return int(round(float(amount) * 100))


def cents_to_money(cents: int) -> float:
    return round(cents / 100.0, 2)


def hash_pin(pin: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex(), derived.hex()


def digits_only(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def build_account_code(account_suffix: Any) -> tuple[str, str]:
    suffix = digits_only(account_suffix)
    if not suffix:
        raise ValueError("Account number is required.")
    if len(suffix) > 12:
        raise ValueError("Account number is too long.")
    return f"{ACCOUNT_PREFIX}{suffix}", suffix


def mask_text(value: str, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return value
    return f"{value[:visible]}{'*' * max(0, len(value) - (visible * 2))}{value[-visible:]}"


class NotificationService:
    def __init__(self) -> None:
        self.sender = str(os.getenv("ZENO_SMTP_EMAIL", DEFAULT_ALERT_EMAIL) or "").strip()
        raw_password = str(os.getenv("ZENO_SMTP_APP_PASSWORD", "") or "")
        # Gmail app passwords are often copied with spaces between 4-char groups.
        self.password = "".join(raw_password.split())
        self.recipient = str(os.getenv("ZENO_ALERT_EMAIL", DEFAULT_ALERT_EMAIL) or "").strip()
        self.smtp_host = str(os.getenv("ZENO_SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com").strip()
        self.smtp_port = int(os.getenv("ZENO_SMTP_PORT", "465"))

    @property
    def enabled(self) -> bool:
        return bool(self.sender and self.password and self.recipient)

    def send_payment_notice_async(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return

        worker = threading.Thread(target=self._send_payment_notice, args=(payload,), daemon=True)
        worker.start()

    def _send_payment_notice(self, payload: dict[str, Any]) -> None:
        try:
            account_code = str(payload.get("account_code") or "unknown")
            owner_account_code = str(payload.get("owner_account_code") or DEFAULT_OWNER_ACCOUNT_CODE)
            amount = float(payload.get("amount") or 0.0)
            reference = str(payload.get("reference") or "N/A")
            terminal_id = str(payload.get("terminal_id") or "unknown")
            location_name = str(payload.get("location_name") or LOCATION_NAME)
            location_link = str(payload.get("location_link") or LOCATION_LINK)
            created_at = str(payload.get("created_at") or utc_now())

            message = EmailMessage()
            message["Subject"] = (
                f"W41K3RJ payment received - {account_code} - "
                f"TZS {amount:.2f}"
            )
            message["From"] = self.sender
            message["To"] = self.recipient
            message.set_content(
                "\n".join(
                    [
                        "A biometric payment was approved.",
                        "",
                        f"Customer account: {account_code}",
                        f"Owner account: {owner_account_code}",
                        f"Amount received: TZS {amount:.2f}",
                        f"Reference: {reference}",
                        f"Terminal: {terminal_id}",
                        f"Location: {location_name}",
                        f"Map link: {location_link}",
                        f"Time: {created_at}",
                    ]
                )
            )

            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as smtp:
                smtp.login(self.sender, self.password)
                smtp.send_message(message)
            print(
                "Email notification sent "
                f"to {self.recipient} for {account_code} reference={reference}",
                flush=True,
            )
        except Exception as exc:
            print(f"Email notification failed: {exc}", flush=True)


class PaymentDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row["name"] for row in rows}

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_definition: str) -> None:
        column_name = column_definition.split()[0]
        if column_name not in self._columns(conn, table_name):
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY,
                  name TEXT NOT NULL,
                  pin_salt TEXT NOT NULL,
                  pin_hash TEXT NOT NULL,
                  balance_cents INTEGER NOT NULL,
                  fingerprint_hash TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transactions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  amount_cents INTEGER NOT NULL,
                  balance_after_cents INTEGER NOT NULL,
                  terminal_id TEXT,
                  status TEXT NOT NULL,
                  detail TEXT,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS machines (
                  terminal_id TEXT PRIMARY KEY,
                  machine_name TEXT NOT NULL,
                  ip_address TEXT,
                  wifi_ssid TEXT,
                  wifi_connected INTEGER NOT NULL DEFAULT 0,
                  local_sensor_active INTEGER NOT NULL DEFAULT 0,
                  remote_sensor_active INTEGER NOT NULL DEFAULT 0,
                  remote_sensor_transport_ready INTEGER NOT NULL DEFAULT 0,
                  remote_enrollment_supported INTEGER NOT NULL DEFAULT 0,
                  remote_server_match_supported INTEGER NOT NULL DEFAULT 0,
                  remote_sensor_model TEXT,
                  remote_sensor_transport TEXT,
                  remote_power_note TEXT,
                  remote_wiring_note TEXT,
                  owner_account_code TEXT,
                  location_name TEXT NOT NULL,
                  location_link TEXT NOT NULL,
                  firmware_version TEXT,
                  last_seen_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                """
            )
            self._migrate_schema(conn)
            self._cleanup_demo_users(conn)
            self._seed_owner(conn)
            self._seed_machine(conn)
            self._export_fingerprint_index(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        self._ensure_column(conn, "users", "account_code TEXT")
        self._ensure_column(conn, "users", "account_suffix TEXT")
        self._ensure_column(conn, "users", "phone_number TEXT DEFAULT ''")
        self._ensure_column(conn, "users", "nida_number TEXT DEFAULT ''")
        self._ensure_column(conn, "users", "account_type TEXT DEFAULT 'customer'")
        self._ensure_column(conn, "users", "fingerprint_source TEXT DEFAULT ''")
        self._ensure_column(conn, "users", "local_sensor_slot INTEGER")

        self._ensure_column(conn, "transactions", "account_code TEXT")
        self._ensure_column(conn, "transactions", "owner_account_code TEXT")
        self._ensure_column(conn, "transactions", "owner_balance_after_cents INTEGER DEFAULT 0")
        self._ensure_column(conn, "transactions", "reference TEXT")
        self._ensure_column(conn, "transactions", "location_name TEXT")
        self._ensure_column(conn, "transactions", "location_link TEXT")
        self._ensure_column(conn, "machines", "remote_sensor_transport_ready INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "machines", "remote_enrollment_supported INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "machines", "remote_server_match_supported INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "machines", "remote_sensor_model TEXT")
        self._ensure_column(conn, "machines", "remote_sensor_transport TEXT")
        self._ensure_column(conn, "machines", "remote_power_note TEXT")
        self._ensure_column(conn, "machines", "remote_wiring_note TEXT")

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_account_code ON users(account_code)"
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_local_slot
            ON users(local_sensor_slot)
            WHERE local_sensor_slot IS NOT NULL
            """
        )

        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        for row in rows:
            existing_code = row["account_code"] if "account_code" in row.keys() else None
            if existing_code:
                account_code = existing_code
                suffix = row["account_suffix"] or digits_only(existing_code.removeprefix(ACCOUNT_PREFIX))
            else:
                account_code, suffix = build_account_code(row["id"])

            account_type = row["account_type"] or (
                "owner" if account_code == DEFAULT_OWNER_ACCOUNT_CODE else "customer"
            )
            fingerprint_source = row["fingerprint_source"] or (
                "as608" if row["fingerprint_hash"] else ""
            )
            local_sensor_slot = row["local_sensor_slot"]
            if local_sensor_slot is None and account_type != "owner":
                local_sensor_slot = row["id"]

            conn.execute(
                """
                UPDATE users
                SET account_code = ?,
                    account_suffix = ?,
                    phone_number = COALESCE(phone_number, ''),
                    nida_number = COALESCE(nida_number, ''),
                    account_type = ?,
                    fingerprint_source = ?,
                    local_sensor_slot = ?
                WHERE id = ?
                """,
                (
                    account_code,
                    suffix,
                    account_type,
                    fingerprint_source,
                    local_sensor_slot,
                    row["id"],
                ),
            )

        conn.commit()

    def _cleanup_demo_users(self, conn: sqlite3.Connection) -> None:
        demo_account_codes = [build_account_code(user_id)[0] for user_id in range(1, 6)]
        demo_names = [f"Customer {user_id}" for user_id in range(1, 6)]
        cursor = conn.execute(
            f"""
            DELETE FROM users
            WHERE account_type = 'customer'
              AND account_code IN ({",".join("?" for _ in demo_account_codes)})
              AND name IN ({",".join("?" for _ in demo_names)})
              AND COALESCE(phone_number, '') = ''
              AND COALESCE(nida_number, '') = ''
              AND COALESCE(fingerprint_hash, '') = ''
              AND COALESCE(fingerprint_source, '') = ''
              AND balance_cents = ?
              AND NOT EXISTS (
                SELECT 1
                FROM transactions t
                WHERE t.user_id = users.id
              )
            """,
            (*demo_account_codes, *demo_names, money_to_cents(DEFAULT_INITIAL_BALANCE)),
        )
        removed = cursor.rowcount if cursor.rowcount is not None else 0
        if removed:
            print(f"Removed {removed} demo customer rows from database.")
            conn.commit()

    def _seed_users(self, conn: sqlite3.Connection) -> None:
        seeded_users = [
            (1, "Customer 1", "1111"),
            (2, "Customer 2", "2222"),
            (3, "Customer 3", "3333"),
            (4, "Customer 4", "4444"),
            (5, "Customer 5", "5555"),
        ]
        for user_id, name, pin in seeded_users:
            account_code, suffix = build_account_code(user_id)
            existing = conn.execute(
                "SELECT id FROM users WHERE account_code = ? OR id = ?",
                (account_code, user_id),
            ).fetchone()
            if existing:
                continue
            salt_hex, pin_hash_hex = hash_pin(pin)
            now = utc_now()
            conn.execute(
                """
                INSERT INTO users (
                  id, name, pin_salt, pin_hash, balance_cents, fingerprint_hash, created_at, updated_at,
                  account_code, account_suffix, phone_number, nida_number, account_type, fingerprint_source,
                  local_sensor_slot
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, '', '', 'customer', '', ?)
                """,
                (
                    user_id,
                    name,
                    salt_hex,
                    pin_hash_hex,
                    money_to_cents(DEFAULT_INITIAL_BALANCE),
                    now,
                    now,
                    account_code,
                    suffix,
                    user_id,
                ),
            )
        conn.commit()

    def _seed_owner(self, conn: sqlite3.Connection) -> None:
        existing = conn.execute(
            "SELECT id FROM users WHERE account_code = ?",
            (DEFAULT_OWNER_ACCOUNT_CODE,),
        ).fetchone()
        if existing:
            return

        salt_hex, pin_hash_hex = hash_pin("0000")
        now = utc_now()
        conn.execute(
            """
            INSERT INTO users (
              name, pin_salt, pin_hash, balance_cents, fingerprint_hash, created_at, updated_at,
              account_code, account_suffix, phone_number, nida_number, account_type, fingerprint_source,
              local_sensor_slot
            ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, '', '', 'owner', '', NULL)
            """,
            (
                "Machine Owner",
                salt_hex,
                pin_hash_hex,
                0,
                now,
                now,
                DEFAULT_OWNER_ACCOUNT_CODE,
                DEFAULT_OWNER_SUFFIX,
            ),
        )
        conn.commit()

    def _seed_machine(self, conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT terminal_id FROM machines LIMIT 1").fetchone()
        if existing:
            return
        now = utc_now()
        conn.execute(
            """
            INSERT INTO machines (
              terminal_id, machine_name, ip_address, wifi_ssid, wifi_connected, local_sensor_active,
              remote_sensor_active, remote_sensor_transport_ready, remote_enrollment_supported,
              remote_server_match_supported, remote_sensor_model, remote_sensor_transport,
              remote_power_note, remote_wiring_note, owner_account_code, location_name,
              location_link, firmware_version, last_seen_at, updated_at
            ) VALUES (?, ?, '', '', 0, 0, 0, 0, 0, 0, '', '', '', '', ?, ?, ?, '', ?, ?)
            """,
            (
                "terminal-arusha-01",
                MACHINE_NAME,
                DEFAULT_OWNER_ACCOUNT_CODE,
                LOCATION_NAME,
                LOCATION_LINK,
                now,
                now,
            ),
        )
        conn.commit()

    def _find_user_row(
        self,
        conn: sqlite3.Connection,
        *,
        account_code: str | None = None,
        local_sensor_slot: int | None = None,
        fingerprint_hash: str | None = None,
        include_owner: bool = False,
    ) -> sqlite3.Row | None:
        if account_code:
            query = "SELECT * FROM users WHERE account_code = ?"
            params = (account_code,)
        elif local_sensor_slot is not None:
            query = "SELECT * FROM users WHERE local_sensor_slot = ?"
            params = (local_sensor_slot,)
        elif fingerprint_hash:
            query = "SELECT * FROM users WHERE fingerprint_hash = ?"
            params = (fingerprint_hash,)
        else:
            return None

        if not include_owner:
            query += " AND account_type != 'owner'"

        return conn.execute(query, params).fetchone()

    def _row_to_user_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "account_code": row["account_code"],
            "account_suffix": row["account_suffix"],
            "name": row["name"],
            "account_type": row["account_type"],
            "phone_number": row["phone_number"] or "",
            "nida_number_masked": mask_text(row["nida_number"] or ""),
            "balance": cents_to_money(row["balance_cents"]),
            "registered": bool(row["fingerprint_hash"]),
            "fingerprint_source": row["fingerprint_source"] or "",
            "local_sensor_slot": row["local_sensor_slot"],
            "updated_at": row["updated_at"],
        }

    def _export_fingerprint_index(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT account_code, name, fingerprint_hash, updated_at
            FROM users
            WHERE fingerprint_hash IS NOT NULL AND account_type != 'owner'
            ORDER BY account_code
            """
        ).fetchall()
        payload = {
            "generated_at": utc_now(),
            "users": [
                {
                    "account_code": row["account_code"],
                    "name": row["name"],
                    "fingerprint_hash": row["fingerprint_hash"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ],
        }
        FINGERPRINT_INDEX_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_user(
        self,
        *,
        account_code: str | None = None,
        local_sensor_slot: int | None = None,
        include_owner: bool = False,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = self._find_user_row(
                conn,
                account_code=account_code,
                local_sensor_slot=local_sensor_slot,
                include_owner=include_owner,
            )
        if not row:
            return None
        return self._row_to_user_payload(row)

    def get_owner_account(self) -> dict[str, Any] | None:
        return self.get_user(account_code=DEFAULT_OWNER_ACCOUNT_CODE, include_owner=True)

    def get_machine_state(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM machines
                ORDER BY last_seen_at DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return {
            "terminal_id": row["terminal_id"],
            "machine_name": row["machine_name"],
            "ip_address": row["ip_address"] or "",
            "wifi_ssid": row["wifi_ssid"] or "",
            "wifi_connected": bool(row["wifi_connected"]),
            "local_sensor_active": bool(row["local_sensor_active"]),
            "remote_sensor_active": bool(row["remote_sensor_active"]),
            "remote_sensor_transport_ready": bool(row["remote_sensor_transport_ready"]),
            "remote_enrollment_supported": bool(row["remote_enrollment_supported"]),
            "remote_server_match_supported": bool(row["remote_server_match_supported"]),
            "remote_sensor_model": row["remote_sensor_model"] or "",
            "remote_sensor_transport": row["remote_sensor_transport"] or "",
            "remote_power_note": row["remote_power_note"] or "",
            "remote_wiring_note": row["remote_wiring_note"] or "",
            "owner_account_code": row["owner_account_code"] or DEFAULT_OWNER_ACCOUNT_CODE,
            "location_name": row["location_name"] or LOCATION_NAME,
            "location_link": row["location_link"] or LOCATION_LINK,
            "firmware_version": row["firmware_version"] or "",
            "last_seen_at": row["last_seen_at"],
            "active": bool(row["wifi_connected"]) and is_recent(row["last_seen_at"]),
        }

    def get_state(self) -> dict[str, Any]:
        with self._connect() as conn:
            user_rows = conn.execute(
                """
                SELECT *
                FROM users
                WHERE account_type != 'owner'
                ORDER BY account_code
                """
            ).fetchall()
            tx_rows = conn.execute(
                """
                SELECT
                  t.account_code,
                  t.owner_account_code,
                  t.amount_cents,
                  t.balance_after_cents,
                  t.owner_balance_after_cents,
                  t.reference,
                  t.location_name,
                  t.location_link,
                  t.created_at
                FROM transactions t
                WHERE t.status = 'success'
                ORDER BY t.id DESC
                LIMIT 20
                """
            ).fetchall()

        return {
            "machine": self.get_machine_state(),
            "owner_account": self.get_owner_account(),
            "users": [self._row_to_user_payload(row) for row in user_rows],
            "transactions": [
                {
                    "account_code": row["account_code"],
                    "owner_account_code": row["owner_account_code"],
                    "amount": cents_to_money(row["amount_cents"]),
                    "balance_after": cents_to_money(row["balance_after_cents"]),
                    "owner_balance_after": cents_to_money(row["owner_balance_after_cents"]),
                    "reference": row["reference"],
                    "location_name": row["location_name"] or LOCATION_NAME,
                    "location_link": row["location_link"] or LOCATION_LINK,
                    "created_at": row["created_at"],
                }
                for row in tx_rows
            ],
        }

    def allocate_local_slot(self, account_suffix: Any) -> dict[str, Any]:
        account_code, _ = build_account_code(account_suffix)
        with self.lock, self._connect() as conn:
            row = self._find_user_row(conn, account_code=account_code, include_owner=False)
            if row and row["local_sensor_slot"]:
                return {"account_code": account_code, "local_sensor_slot": row["local_sensor_slot"]}

            used_slots = {
                slot
                for (slot,) in conn.execute(
                    "SELECT local_sensor_slot FROM users WHERE local_sensor_slot IS NOT NULL"
                ).fetchall()
            }
            for slot_id in range(1, MAX_LOCAL_SENSOR_SLOTS + 1):
                if slot_id not in used_slots:
                    return {"account_code": account_code, "local_sensor_slot": slot_id}

        raise RuntimeError("No free AS608 local fingerprint slots are left.")

    def register_user(
        self,
        *,
        account_suffix: Any,
        phone_number: Any,
        nida_number: Any,
        pin: str,
        fingerprint_hash: str,
        local_sensor_slot: int,
        fingerprint_source: str = "as608",
        account_type: str = "customer",
        initial_balance: float | None = None,
    ) -> dict[str, Any]:
        if len(pin) != 4 or not pin.isdigit():
            raise ValueError("PIN must be exactly 4 digits.")
        if len(fingerprint_hash) < 32:
            raise ValueError("Fingerprint hash is too short.")

        phone = digits_only(phone_number)
        nida = digits_only(nida_number)
        if len(phone) < 10 or len(phone) > 15:
            raise ValueError("Phone number must be 10 to 15 digits.")
        if len(nida) != 20:
            raise ValueError("NIDA number must be exactly 20 digits.")
        if local_sensor_slot < 1 or local_sensor_slot > MAX_LOCAL_SENSOR_SLOTS:
            raise ValueError(f"Local sensor slot must be 1 to {MAX_LOCAL_SENSOR_SLOTS}.")

        account_code, suffix = build_account_code(account_suffix)
        normalized_source = (fingerprint_source or "as608").strip().lower()
        normalized_type = (account_type or "customer").strip().lower()
        if normalized_type != "customer":
            raise ValueError("Only customer registrations are allowed from the terminal.")

        with self.lock, self._connect() as conn:
            now = utc_now()
            salt_hex, pin_hash_hex = hash_pin(pin)
            conn.execute(
                """
                UPDATE users
                SET local_sensor_slot = NULL
                WHERE local_sensor_slot = ? AND account_code != ?
                """,
                (local_sensor_slot, account_code),
            )

            row = self._find_user_row(conn, account_code=account_code, include_owner=False)
            created_new_user = row is None
            if row:
                balance_cents = (
                    money_to_cents(initial_balance)
                    if initial_balance is not None
                    else row["balance_cents"]
                )
                conn.execute(
                    """
                    UPDATE users
                    SET name = ?,
                        pin_salt = ?,
                        pin_hash = ?,
                        balance_cents = ?,
                        fingerprint_hash = ?,
                        updated_at = ?,
                        account_suffix = ?,
                        phone_number = ?,
                        nida_number = ?,
                        account_type = ?,
                        fingerprint_source = ?,
                        local_sensor_slot = ?
                    WHERE id = ?
                    """,
                    (
                        f"Customer {account_code}",
                        salt_hex,
                        pin_hash_hex,
                        balance_cents,
                        fingerprint_hash,
                        now,
                        suffix,
                        phone,
                        nida,
                        normalized_type,
                        normalized_source,
                        local_sensor_slot,
                        row["id"],
                    ),
                )
            else:
                balance_cents = money_to_cents(
                    initial_balance if initial_balance is not None else DEFAULT_INITIAL_BALANCE
                )
                conn.execute(
                    """
                    INSERT INTO users (
                      name, pin_salt, pin_hash, balance_cents, fingerprint_hash, created_at, updated_at,
                      account_code, account_suffix, phone_number, nida_number, account_type,
                      fingerprint_source, local_sensor_slot
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"Customer {account_code}",
                        salt_hex,
                        pin_hash_hex,
                        balance_cents,
                        fingerprint_hash,
                        now,
                        now,
                        account_code,
                        suffix,
                        phone,
                        nida,
                        normalized_type,
                        normalized_source,
                        local_sensor_slot,
                    ),
                )

            conn.commit()
            self._export_fingerprint_index(conn)
            total_customers = conn.execute(
                "SELECT COUNT(*) FROM users WHERE account_type != 'owner'"
            ).fetchone()[0]

        user = self.get_user(account_code=account_code) or {}
        action = "created" if created_new_user else "updated"
        print(
            f"Registration {action}: {account_code} slot={local_sensor_slot} "
            f"total_customers={total_customers}"
        )
        return user

    def identify_user(
        self,
        *,
        account_code: str | None = None,
        local_sensor_slot: int | None = None,
        fingerprint_hash: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = self._find_user_row(
                conn,
                account_code=account_code,
                local_sensor_slot=local_sensor_slot,
                fingerprint_hash=fingerprint_hash,
                include_owner=False,
            )
        if not row:
            return None
        return self._row_to_user_payload(row)

    def verify_payment(
        self,
        *,
        pin: str,
        amount: float,
        terminal_id: str | None,
        account_code: str | None = None,
        local_sensor_slot: int | None = None,
        fingerprint_hash: str | None = None,
    ) -> dict[str, Any]:
        amount_cents = money_to_cents(amount)
        minimum_cents = money_to_cents(MINIMUM_PAYMENT_AMOUNT)
        if amount_cents < minimum_cents:
            return {
                "success": False,
                "message": f"Minimum payment is TZS {MINIMUM_PAYMENT_AMOUNT:.2f}.",
                "balance": 0.0,
            }

        with self.lock, self._connect() as conn:
            customer = self._find_user_row(
                conn,
                account_code=account_code,
                local_sensor_slot=local_sensor_slot,
                fingerprint_hash=fingerprint_hash,
                include_owner=False,
            )
            if not customer:
                return {"success": False, "message": "Customer account not found.", "balance": 0.0}

            if not customer["fingerprint_hash"]:
                return {
                    "success": False,
                    "message": "Fingerprint is not registered on the server.",
                    "balance": cents_to_money(customer["balance_cents"]),
                }

            _, submitted_hash = hash_pin(pin, customer["pin_salt"])
            if not secrets.compare_digest(submitted_hash, customer["pin_hash"]):
                self._record_transaction(
                    conn,
                    user_id=customer["id"],
                    amount_cents=amount_cents,
                    balance_after_cents=customer["balance_cents"],
                    owner_balance_after_cents=0,
                    terminal_id=terminal_id,
                    status="failed",
                    detail="Invalid PIN",
                    account_code=customer["account_code"],
                    owner_account_code=DEFAULT_OWNER_ACCOUNT_CODE,
                    reference="",
                )
                conn.commit()
                return {
                    "success": False,
                    "message": "Invalid PIN.",
                    "balance": cents_to_money(customer["balance_cents"]),
                }

            if customer["balance_cents"] < amount_cents:
                self._record_transaction(
                    conn,
                    user_id=customer["id"],
                    amount_cents=amount_cents,
                    balance_after_cents=customer["balance_cents"],
                    owner_balance_after_cents=0,
                    terminal_id=terminal_id,
                    status="failed",
                    detail="Insufficient balance",
                    account_code=customer["account_code"],
                    owner_account_code=DEFAULT_OWNER_ACCOUNT_CODE,
                    reference="",
                )
                conn.commit()
                return {
                    "success": False,
                    "message": "Insufficient balance.",
                    "balance": cents_to_money(customer["balance_cents"]),
                }

            owner = self._find_user_row(
                conn,
                account_code=DEFAULT_OWNER_ACCOUNT_CODE,
                include_owner=True,
            )
            if not owner:
                raise RuntimeError("Owner account is missing from the database.")

            now = utc_now()
            new_customer_balance = customer["balance_cents"] - amount_cents
            new_owner_balance = owner["balance_cents"] + amount_cents
            reference = f"TX-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{customer['id']}"

            conn.execute(
                "UPDATE users SET balance_cents = ?, updated_at = ? WHERE id = ?",
                (new_customer_balance, now, customer["id"]),
            )
            conn.execute(
                "UPDATE users SET balance_cents = ?, updated_at = ? WHERE id = ?",
                (new_owner_balance, now, owner["id"]),
            )

            self._record_transaction(
                conn,
                user_id=customer["id"],
                amount_cents=amount_cents,
                balance_after_cents=new_customer_balance,
                owner_balance_after_cents=new_owner_balance,
                terminal_id=terminal_id,
                status="success",
                detail="Payment approved",
                account_code=customer["account_code"],
                owner_account_code=owner["account_code"],
                reference=reference,
            )
            conn.commit()

            print(
                f"Payment approved: {customer['account_code']} amount=TZS {cents_to_money(amount_cents):.2f} "
                f"reference={reference}"
            )
            return {
                "success": True,
                "message": "Payment approved.",
                "balance": cents_to_money(new_customer_balance),
                "owner_balance": cents_to_money(new_owner_balance),
                "amount": cents_to_money(amount_cents),
                "account_code": customer["account_code"],
                "owner_account_code": owner["account_code"],
                "reference": reference,
                "location_name": LOCATION_NAME,
                "location_link": LOCATION_LINK,
                "created_at": now,
                "terminal_id": terminal_id,
            }

    def _record_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: int,
        amount_cents: int,
        balance_after_cents: int,
        owner_balance_after_cents: int,
        terminal_id: str | None,
        status: str,
        detail: str,
        account_code: str,
        owner_account_code: str,
        reference: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO transactions (
              user_id,
              amount_cents,
              balance_after_cents,
              owner_balance_after_cents,
              terminal_id,
              status,
              detail,
              created_at,
              account_code,
              owner_account_code,
              reference,
              location_name,
              location_link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                amount_cents,
                balance_after_cents,
                owner_balance_after_cents,
                terminal_id,
                status,
                detail,
                utc_now(),
                account_code,
                owner_account_code,
                reference,
                LOCATION_NAME,
                LOCATION_LINK,
            ),
        )

    def record_machine_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        terminal_id = str(payload.get("terminal_id") or "").strip()
        if not terminal_id:
            raise ValueError("terminal_id is required.")

        machine_name = str(payload.get("machine_name") or MACHINE_NAME).strip() or MACHINE_NAME
        now = utc_now()
        with self.lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO machines (
                  terminal_id,
                  machine_name,
                  ip_address,
                  wifi_ssid,
                  wifi_connected,
                  local_sensor_active,
                  remote_sensor_active,
                  remote_sensor_transport_ready,
                  remote_enrollment_supported,
                  remote_server_match_supported,
                  remote_sensor_model,
                  remote_sensor_transport,
                  remote_power_note,
                  remote_wiring_note,
                  owner_account_code,
                  location_name,
                  location_link,
                  firmware_version,
                  last_seen_at,
                  updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(terminal_id) DO UPDATE SET
                  machine_name = excluded.machine_name,
                  ip_address = excluded.ip_address,
                  wifi_ssid = excluded.wifi_ssid,
                  wifi_connected = excluded.wifi_connected,
                  local_sensor_active = excluded.local_sensor_active,
                  remote_sensor_active = excluded.remote_sensor_active,
                  remote_sensor_transport_ready = excluded.remote_sensor_transport_ready,
                  remote_enrollment_supported = excluded.remote_enrollment_supported,
                  remote_server_match_supported = excluded.remote_server_match_supported,
                  remote_sensor_model = excluded.remote_sensor_model,
                  remote_sensor_transport = excluded.remote_sensor_transport,
                  remote_power_note = excluded.remote_power_note,
                  remote_wiring_note = excluded.remote_wiring_note,
                  owner_account_code = excluded.owner_account_code,
                  location_name = excluded.location_name,
                  location_link = excluded.location_link,
                  firmware_version = excluded.firmware_version,
                  last_seen_at = excluded.last_seen_at,
                  updated_at = excluded.updated_at
                """,
                (
                    terminal_id,
                    machine_name,
                    str(payload.get("ip_address") or ""),
                    str(payload.get("wifi_ssid") or ""),
                    int(bool(payload.get("wifi_connected"))),
                    int(bool(payload.get("local_sensor_active"))),
                    int(bool(payload.get("remote_sensor_active"))),
                    int(bool(payload.get("remote_sensor_transport_ready"))),
                    int(bool(payload.get("remote_enrollment_supported"))),
                    int(bool(payload.get("remote_server_match_supported"))),
                    str(payload.get("remote_sensor_model") or ""),
                    str(payload.get("remote_sensor_transport") or ""),
                    str(payload.get("remote_power_note") or ""),
                    str(payload.get("remote_wiring_note") or ""),
                    str(payload.get("owner_account_code") or DEFAULT_OWNER_ACCOUNT_CODE),
                    str(payload.get("location_name") or LOCATION_NAME),
                    str(payload.get("location_link") or LOCATION_LINK),
                    str(payload.get("firmware_version") or ""),
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get_machine_state() or {}


class ZenoPayHandler(BaseHTTPRequestHandler):
    database: PaymentDatabase
    notifications: NotificationService

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True

    def _send_html(self, markup: str) -> None:
        encoded = markup.encode("utf-8")
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self._send_html(build_dashboard_html())
            return

        if parsed.path == "/api/health":
            self._send_json(
                {
                    "status": "ok",
                    "time": utc_now(),
                    "machine": self.database.get_machine_state(),
                }
            )
            return

        if parsed.path == "/api/state":
            self._send_json(self.database.get_state())
            return

        if parsed.path == "/api/user":
            query = parse_qs(parsed.query)
            account_code = query.get("account_code", [None])[0]
            slot_text = query.get("slot", [None])[0]
            legacy_id = query.get("id", [None])[0]
            local_sensor_slot = None
            if slot_text and slot_text.isdigit():
                local_sensor_slot = int(slot_text)
            elif legacy_id and legacy_id.isdigit():
                local_sensor_slot = int(legacy_id)
            user = self.database.get_user(account_code=account_code, local_sensor_slot=local_sensor_slot)
            if not user:
                self._send_json({"error": "User not found."}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(user)
            return

        self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON body."}, HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/register-slot":
            try:
                account_suffix = payload.get("account_suffix", payload.get("user_id"))
                slot_payload = self.database.allocate_local_slot(account_suffix)
            except (TypeError, ValueError, RuntimeError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"success": True, **slot_payload})
            return

        if parsed.path == "/api/register":
            try:
                account_suffix = payload.get("account_suffix", payload.get("user_id"))
                local_sensor_slot = int(payload.get("local_sensor_slot", payload.get("user_id")))
                user = self.database.register_user(
                    account_suffix=account_suffix,
                    phone_number=payload.get("phone_number"),
                    nida_number=payload.get("nida_number"),
                    pin=str(payload["pin"]),
                    fingerprint_hash=str(payload["fingerprint_hash"]),
                    local_sensor_slot=local_sensor_slot,
                    fingerprint_source=str(payload.get("fingerprint_source") or "as608"),
                    account_type=str(payload.get("account_type") or "customer"),
                    initial_balance=payload.get("initial_balance"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"success": True, "message": "Registration saved.", "user": user})
            return

        if parsed.path == "/api/identify":
            try:
                local_sensor_slot = payload.get("local_sensor_slot", payload.get("slot"))
                local_sensor_slot = int(local_sensor_slot) if local_sensor_slot is not None else None
                fingerprint_hash = payload.get("fingerprint_hash")
                account_code = payload.get("account_code")
                user = self.database.identify_user(
                    account_code=account_code,
                    local_sensor_slot=local_sensor_slot,
                    fingerprint_hash=fingerprint_hash,
                )
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if not user:
                self._send_json({"error": "Fingerprint/account not found."}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"success": True, "user": user})
            return

        if parsed.path == "/api/verify":
            try:
                local_sensor_slot = payload.get("local_sensor_slot", payload.get("user_id"))
                local_sensor_slot = int(local_sensor_slot) if local_sensor_slot is not None else None
                result = self.database.verify_payment(
                    pin=str(payload["pin"]),
                    amount=float(payload["amount"]),
                    terminal_id=payload.get("terminal_id"),
                    account_code=payload.get("account_code"),
                    local_sensor_slot=local_sensor_slot,
                    fingerprint_hash=payload.get("fingerprint_hash"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except Exception:
                traceback.print_exc()
                self._send_json(
                    {"success": False, "error": "Server error.", "message": "Server error."},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            if result.get("success"):
                self.notifications.send_payment_notice_async(result)

            self._send_json(result)
            return

        if parsed.path == "/api/heartbeat":
            try:
                machine = self.database.record_machine_heartbeat(payload)
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"success": True, "machine": machine})
            return

        self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64
    handshake_timeout_s = 8.0
    client_timeout_s = 15.0
    ssl_context: ssl.SSLContext | None = None

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(self.handshake_timeout_s)
        if self.ssl_context is not None:
            request = self.ssl_context.wrap_socket(
                request,
                server_side=True,
                do_handshake_on_connect=False,
            )
            request.settimeout(self.handshake_timeout_s)
        return request, client_address

    def process_request_thread(self, request, client_address) -> None:
        try:
            if isinstance(request, ssl.SSLSocket):
                request.do_handshake()
                request.settimeout(self.client_timeout_s)
        except (ssl.SSLError, TimeoutError, OSError):
            self.shutdown_request(request)
            return
        super().process_request_thread(request, client_address)


def build_ssl_context(cert_path: Path, key_path: Path) -> ssl.SSLContext:
    if not cert_path.exists() or not key_path.exists():
        raise FileNotFoundError(
            "TLS certificate files are missing. Run scripts/generate_tls_assets.py first."
        )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="W41K3RJ biometric HTTPS server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--cert", type=Path, default=DEFAULT_CERT_PATH)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    load_env_file(BASE_DIR / ".env.local")

    db = PaymentDatabase(args.db)
    ZenoPayHandler.database = db
    ZenoPayHandler.notifications = NotificationService()

    server = ReusableThreadingHTTPServer((args.host, args.port), ZenoPayHandler)
    server.ssl_context = build_ssl_context(args.cert, args.key)

    print(f"W41K3RJ HTTPS server running on https://{args.host}:{args.port}")
    print(f"Database: {args.db}")
    print(f"Dashboard: https://{args.host}:{args.port}/")
    if ZenoPayHandler.notifications.enabled:
        print(f"Email notifications: enabled -> {ZenoPayHandler.notifications.recipient}")
    else:
        print("Email notifications: disabled (set ZENO_SMTP_EMAIL and ZENO_SMTP_APP_PASSWORD)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")


if __name__ == "__main__":
    main()
