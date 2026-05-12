#!/usr/bin/env python3
"""
Monitor de Subastas BOE - Portal subastas.boe.es
Detecta cambios en "Puja más alta" y notifica por Telegram y/o Email
Compatible con Railway (lee credenciales desde variables de entorno)
"""

import os
import time
import smtplib
import requests
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURACIÓN — Lee desde variables de entorno (Railway)
# o desde los valores hardcodeados como fallback local
# ============================================================

URL_SUBASTA      = "https://subastas.boe.es/reg/detalleSubasta.php?idSub=SUB-JA-2026-259491&ver=5&idLote=1"
LOTE_NOMBRE      = "Lote 1 - SUB-JA-2026-259491"
INTERVALO_SEGUNDOS = 60

# Telegram — Railway: añade variables TELEGRAM_TOKEN y TELEGRAM_CHAT_ID
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Email Gmail — Railway: añade EMAIL_REMITENTE, EMAIL_PASSWORD_APP, EMAIL_DESTINATARIO
EMAIL_REMITENTE      = os.environ.get("EMAIL_REMITENTE",      "")
EMAIL_PASSWORD_APP   = os.environ.get("EMAIL_PASSWORD_APP",   "")
EMAIL_DESTINATARIO   = os.environ.get("EMAIL_DESTINATARIO",   "")

# Cookies BOE — Railway: añade variables SESSID y SIMPLESAM
_sessid     = os.environ.get("SESSID",      "")
_simplesam  = os.environ.get("SimpleSAML",  "")
SESSION_COOKIES = {}
if _sessid:
    SESSION_COOKIES["SESSID"] = _sessid
if _simplesam:
    SESSION_COOKIES["SimpleSAML"] = _simplesam

# ============================================================
# LOGS
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("monitor_subasta.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ============================================================
# NOTIFICACIONES
# ============================================================

def enviar_telegram(mensaje: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("✅ Notificación Telegram enviada")
            return True
        else:
            log.error(f"❌ Telegram error {r.status_code}: {r.text}")
    except Exception as e:
        log.error(f"❌ Telegram excepción: {e}")
    return False


def enviar_email(asunto: str, cuerpo: str) -> bool:
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD_APP or not EMAIL_DESTINATARIO:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = EMAIL_REMITENTE
        msg["To"]      = EMAIL_DESTINATARIO
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as srv:
            srv.login(EMAIL_REMITENTE, EMAIL_PASSWORD_APP)
            srv.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
        log.info("✅ Notificación email enviada")
        return True
    except Exception as e:
        log.error(f"❌ Email excepción: {e}")
    return False


def notificar(asunto: str, cuerpo: str):
    enviar_telegram(cuerpo)
    enviar_email(asunto, cuerpo)

# ============================================================
# EXTRACCIÓN DEL VALOR
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://subastas.boe.es/",
}


def obtener_puja_mas_alta() -> str | None:
    try:
        resp = requests.get(
            URL_SUBASTA,
            headers=HEADERS,
            cookies=SESSION_COOKIES if SESSION_COOKIES else None,
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"⚠️  Error al descargar página: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    for h4 in soup.find_all("h4"):
        texto_h4 = h4.get_text(strip=True).lower()
        if "puja" in texto_h4 and "alta" in texto_h4:
            siguiente = h4.find_next_sibling()
            if siguiente:
                valor = siguiente.get_text(strip=True)
            else:
                valor = h4.find_next(string=True)
                valor = valor.strip() if valor else "(valor no encontrado)"
            return valor if valor else "(vacío)"

    for h4 in soup.find_all("h4"):
        if "puja" in h4.get_text(strip=True).lower():
            parent = h4.parent
            texto  = parent.get_text(separator=" ", strip=True)
            idx    = texto.lower().find("puja más alta")
            if idx != -1:
                return texto[idx + len("puja más alta"):].strip()[:120]

    log.warning("⚠️  No se encontró el campo 'Puja más alta' en el HTML")
    return None

# ============================================================
# BUCLE PRINCIPAL
# ============================================================

def main():
    log.info("=" * 60)
    log.info(f"🏁 Iniciando monitor: {LOTE_NOMBRE}")
    log.info(f"🔄 Intervalo: {INTERVALO_SEGUNDOS}s")
    log.info(f"📡 Telegram configurado: {'✅' if TELEGRAM_TOKEN else '❌ (no configurado)'}")
    log.info(f"📧 Email configurado:    {'✅' if EMAIL_REMITENTE else '❌ (no configurado)'}")
    log.info(f"🍪 Cookies BOE:          {'✅' if SESSION_COOKIES else '⚠️  (sin cookies)'}")
    log.info("=" * 60)

    ultimo_valor = None
    primer_check = True

    while True:
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        valor_actual = obtener_puja_mas_alta()

        if valor_actual is None:
            log.warning(f"[{ahora}] No se pudo obtener el valor — reintentando en {INTERVALO_SEGUNDOS}s")
        elif primer_check:
            log.info(f"[{ahora}] 📌 Valor inicial: «{valor_actual}»")
            ultimo_valor = valor_actual
            primer_check = False
        elif valor_actual != ultimo_valor:
            mensaje = (
                f"🔔 <b>Nueva puja en {LOTE_NOMBRE}</b>\n\n"
                f"💶 <b>Anterior:</b> {ultimo_valor}\n"
                f"💶 <b>Nueva:</b>    {valor_actual}\n\n"
                f"🕒 {ahora}\n"
                f"🔗 {URL_SUBASTA}"
            )
            log.info(f"[{ahora}] 🔔 CAMBIO: «{ultimo_valor}» → «{valor_actual}»")
            notificar(asunto=f"[BOE] Nueva puja: {valor_actual}", cuerpo=mensaje)
            ultimo_valor = valor_actual
        else:
            log.info(f"[{ahora}] ✔ Sin cambios — Puja más alta: «{valor_actual}»")

        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    main()
