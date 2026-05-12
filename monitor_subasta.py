#!/usr/bin/env python3
"""
Monitor de Subastas BOE - Portal subastas.boe.es
Detecta cambios en "Puja más alta" y notifica por Telegram y/o Email
"""

import time
import smtplib
import requests
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURACIÓN — Rellena aquí tus datos
# ============================================================

# -- URL de la subasta (puedes cambiarla o añadir más lotes) --
URL_SUBASTA = "https://subastas.boe.es/reg/detalleSubasta.php?idSub=SUB-JA-2026-259491&ver=5&idLote=1"
LOTE_NOMBRE = "Lote 1 - SUB-JA-2026-259491"

# -- Intervalo de comprobación en segundos --
INTERVALO_SEGUNDOS = 60

# -- Telegram (deja en "" si no quieres usar Telegram) --
TELEGRAM_TOKEN = "8730961965:AAEOiZjFBOF4Sk97w3C16ZrY8OVpZD1ZVY0"       # Ejemplo: "7123456789:AAH..."
TELEGRAM_CHAT_ID = "543673812"     # Ejemplo: "123456789"

# -- Email Gmail (deja en "" si no quieres usar email) --
EMAIL_REMITENTE = ""      # tu_correo@gmail.com
EMAIL_PASSWORD_APP = ""   # Contraseña de aplicación Google (16 caracteres)
EMAIL_DESTINATARIO = ""   # Puede ser el mismo u otro correo

# -- Cookies de sesión del navegador (necesarias si la web pide login) --
# Ver instrucciones más abajo para obtenerlas desde Chrome/Firefox
SESSION_COOKIES = {
    "SESSID": "f1fd0ce2d095b053d990b3a8dcfcb8",
    "SimpleSAML": "07b565ab4c82afabe208c48bbbcd0a",
}

# ============================================================
# CONFIGURACIÓN DE LOGS
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),                          # consola
        logging.FileHandler("monitor_subasta.log", encoding="utf-8"),  # fichero
    ],
)
log = logging.getLogger(__name__)

# ============================================================
# FUNCIONES DE NOTIFICACIÓN
# ============================================================

def enviar_telegram(mensaje: str) -> bool:
    """Envía mensaje por Telegram usando Bot API."""
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
    """Envía email por Gmail usando contraseña de aplicación."""
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD_APP or not EMAIL_DESTINATARIO:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"] = EMAIL_REMITENTE
        msg["To"] = EMAIL_DESTINATARIO
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as servidor:
            servidor.login(EMAIL_REMITENTE, EMAIL_PASSWORD_APP)
            servidor.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
        log.info("✅ Notificación email enviada")
        return True
    except Exception as e:
        log.error(f"❌ Email excepción: {e}")
    return False


def notificar(asunto: str, cuerpo: str):
    """Envía notificación por todos los canales configurados."""
    enviar_telegram(cuerpo)
    enviar_email(asunto, cuerpo)

# ============================================================
# FUNCIÓN PRINCIPAL: EXTRAE PUJA MÁS ALTA
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
    """
    Descarga la página y extrae el valor del campo 'Puja más alta'.
    Devuelve el texto encontrado o None si hay error.
    """
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

    # Busca el encabezado <h4> que contiene "Puja más alta" (con o sin tilde)
    for h4 in soup.find_all("h4"):
        if "puja" in h4.get_text(strip=True).lower() and "alta" in h4.get_text(strip=True).lower():
            # El valor está en el siguiente nodo de texto o etiqueta hermana
            siguiente = h4.find_next_sibling()
            if siguiente:
                valor = siguiente.get_text(strip=True)
            else:
                # Puede ser texto directo después del h4
                valor = h4.find_next(string=True)
                if valor:
                    valor = valor.strip()
                else:
                    valor = "(valor no encontrado)"
            return valor if valor else "(vacío)"

    # Fallback: busca el texto "Sin pujas" cerca del h4
    for h4 in soup.find_all("h4"):
        if "puja" in h4.get_text(strip=True).lower():
            parent = h4.parent
            texto = parent.get_text(separator=" ", strip=True)
            # Recorta sólo la parte relevante
            idx = texto.lower().find("puja más alta")
            if idx != -1:
                return texto[idx + len("puja más alta"):].strip()[:120]

    log.warning("⚠️  No se encontró el campo 'Puja más alta' en el HTML")
    return None

# ============================================================
# BUCLE PRINCIPAL
# ============================================================

def main():
    log.info("=" * 60)
    log.info(f"🏁 Iniciando monitor de subasta: {LOTE_NOMBRE}")
    log.info(f"🔄 Comprobación cada {INTERVALO_SEGUNDOS} segundos")
    log.info(f"🔗 URL: {URL_SUBASTA}")
    log.info("=" * 60)

    # Comprobación de configuración
    if not TELEGRAM_TOKEN and not EMAIL_REMITENTE:
        log.warning(
            "⚠️  AVISO: No hay Telegram ni Email configurados. "
            "Las alertas sólo aparecerán en consola/log."
        )

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
                f"🔔 <b>Nueva puja detectada en {LOTE_NOMBRE}</b>\n\n"
                f"💶 <b>Puja más alta anterior:</b> {ultimo_valor}\n"
                f"💶 <b>Puja más alta actual:</b>   {valor_actual}\n\n"
                f"🕒 Hora: {ahora}\n"
                f"🔗 {URL_SUBASTA}"
            )
            log.info(f"[{ahora}] 🔔 CAMBIO DETECTADO: «{ultimo_valor}» → «{valor_actual}»")
            notificar(
                asunto=f"[BOE Subasta] Nueva puja: {valor_actual}",
                cuerpo=mensaje,
            )
            ultimo_valor = valor_actual
        else:
            log.info(f"[{ahora}] ✔ Sin cambios — Puja más alta: «{valor_actual}»")

        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    main()
