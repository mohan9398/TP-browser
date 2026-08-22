# -*- coding: utf-8 -*-
import time
import hmac
import hashlib
import os
import logging
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo

# Setup a null handler for the network signer in production
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Hoisted out of the hot path: skip signing static/background requests.
_SKIP_TOKENS = (
    '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg',
    'theme', 'pluginfile', 'webservice',
)

class HmacRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, secret_key: str, parent=None):
        super().__init__(parent)
        self.secret_key = secret_key.encode('utf-8')

    def interceptRequest(self, info):
        # Single toString() + single lower() per request.
        url_l = info.requestUrl().toString().lower()
        for tok in _SKIP_TOKENS:
            if tok in url_l:
                return

        # HMAC-SHA256(secret_key, "timestamp:nonce"). Header output is unchanged
        # so the exam server keeps validating exactly as before.
        timestamp = str(int(time.time()))
        nonce = os.urandom(8).hex()
        signature = hmac.new(
            self.secret_key, f"{timestamp}:{nonce}".encode('utf-8'), hashlib.sha256
        ).hexdigest()

        info.setHttpHeader(b"X-Exam-Time", timestamp.encode('utf-8'))
        info.setHttpHeader(b"X-Exam-Nonce", nonce.encode('utf-8'))
        info.setHttpHeader(b"X-Exam-Signature", signature.encode('utf-8'))
