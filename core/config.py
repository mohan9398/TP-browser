# -*- coding: utf-8 -*-
import os
 
# Application Info
APP_VERSION = "1.0.1" # Incremented for new version
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "TeleBrowser/1.0"
)

# New Time-Based HMAC Security Config
# The key is stored encrypted (obfuscation-at-rest) so it does not appear in
# plaintext inside the compiled binary. See core/secrets.py. To rotate it,
# run:  python -c "from core.secrets import encrypt; print(encrypt('NEWKEY'))"
# and paste the token below.
_APP_SECRET_KEY_ENC = (
    "gAAAAABqOlPDOE_8PSOigsjRm23Aj9SxTJmzrl5imoZm0Mx0gyn7defKjesc-GX_c-Is75k4UbEZhpRey8oDXAhtPd8NmHyL29H3jDyYK4jsIUDn9WgvWgw="
)

try:
    from secure_browser.core.secrets import decrypt as _decrypt
    APP_SECRET_KEY = _decrypt(_APP_SECRET_KEY_ENC)
except Exception:
    # Fallback keeps the app running even if the crypto layer is unavailable.
    APP_SECRET_KEY = "my_production_secret_key_12345"
 
# TODO: Change to HTTPS when available
UPDATE_CHECK_URL = "https://kmit.in/download"


PROXY_TARGET_ORIGINS = [
    # TODO: add the servers that need camera/mic over HTTP, e.g.
      "http://10.11.52.100",
      "http://10.11.1.19",
      "http://10.11.36.18:81",
      "http://10.11.52.100:541",
      "https://toofaanonline.teleuniv.in:535"
      "http://192.168.2.5:81",
      "http://192.168.2.5/exam",
      "http://10.11.52.200",
      "http://192.168.6.5:81",
      "http://192.168.6.5/exam",
      "http://192.168.51.10:88/",
      "http://192.168.51.20:541/"

]

# Backwards-compatible single-target aliases (first entry, if any).
TARGET_ORIGIN = PROXY_TARGET_ORIGINS[0] if PROXY_TARGET_ORIGINS else ""
TARGET_NETLOC = TARGET_ORIGIN.split("://", 1)[-1] if TARGET_ORIGIN else ""

# Hosts the browser is allowed to navigate to. Proxied targets reach the browser
# as 127.0.0.1 (always allowed), but list their hosts here too so media
# permissions are granted and any direct fallback still works. Add the host of
# every portal used in labs.json — including direct-load ones.
ALLOWED_DOMAINS = [
    # KMIT
    "10.11.52.100",
    "10.11.1.19",
    "10.11.36.18",
    "toofaanlab.teleuniv.in",
    # NGIT
    "192.168.2.5",
    "10.11.53.100",
    "10.11.52.200",
    # KMEC
    "192.168.6.5",
    # KMCE
    "192.168.51.10",
    "192.168.51.20",
]

# Make sure every reverse-proxy target host is allowed, without duplicating
# entries the maintainer already listed above.
for _origin in PROXY_TARGET_ORIGINS:
    _host = _origin.split("://", 1)[-1].split(":", 1)[0]
    if _host not in ALLOWED_DOMAINS:
        ALLOWED_DOMAINS.append(_host)
 
# Security Configuration
# Apps that will be blocked/killed during the exam
FORBIDDEN_APPS = [
    # System Tools (Removed CMD/Powershell/TaskMgr to prevent self-kill during dev/launch)
    # We only block Task Manager via Registry, no need to kill it.
    "regedit.exe",
    
    # Browsers
    "chrome.exe", "firefox.exe", "edge.exe", "brave.exe", "opera.exe",
    
    # Communication
    "discord.exe", "slack.exe", "whatsapp.exe", "telegram.exe", "skype.exe", "zoom.exe",
    
    # Remote Desktop
    "anydesk.exe", "teamviewer.exe",
]
 
# Screen capture tools
SCREENSHOT_TOOLS = [
    "snippingtool.exe", "screenclip.exe", "clipchamp.exe",
    "obs64.exe", "obs32.exe", "bandicam.exe", "camtasia.exe",
    "lightshot.exe", "sharex.exe", "greenshot.exe",
]
 
# Combined blocklist
ALL_BLOCKED_APPS = list(set(FORBIDDEN_APPS + SCREENSHOT_TOOLS))
 
# Environment Flags for QtWebEngine
# NOTE: Chromium only honours ONE --disable-features= flag.
#       All features to disable must be in a single comma-separated list.
QT_FLAGS = (
    "--ignore-certificate-errors "
    "--disable-web-security "
    "--enable-gpu-rasterization "
    "--enable-zero-copy "
 
    # Merged single --disable-features list (two separate flags = last one wins, first ignored)
    "--disable-features=WebRtcHideLocalIpsWithMdns,IsolateOrigins,site-per-process "
 
    # Allow camera / mic on HTTP origins
    "--enable-media-stream "
 
    # Auto-approve the browser permission popup → uses the REAL camera, not a fake one.
    # (--use-fake-DEVICE-for-media-stream would use fake; this flag only skips the dialog.)
    "--use-fake-ui-for-media-stream "
 
    # Screen capture over HTTP (proctoring)
    "--enable-usermedia-screen-capturing "
    "--allow-http-screen-capture "
 
    # Allow localhost HTTP as secure origin (belt-and-suspenders)
    "--allow-insecure-localhost "
 
    # Video autoplay without requiring a user gesture first
    "--autoplay-policy=no-user-gesture-required"
)