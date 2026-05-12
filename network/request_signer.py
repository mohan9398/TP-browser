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

class HmacRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, secret_key: str, parent=None):
        super().__init__(parent)
        self.secret_key = secret_key.encode('utf-8')

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        
        # Skip static resources and background tasks to keep logs clean and reduce overhead
        if any(x in url.lower() for x in [
            '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg',
            'theme', 'pluginfile', 'webservice'
        ]):
            return
            
        # Generate Timestamp
        timestamp = str(int(time.time()))
        
        # Generate Nonce (8 random bytes as hex = 16 characters)
        nonce = os.urandom(8).hex()
        
        # Calculate HMAC: HMAC-SHA256(secret_key, timestamp + ":" + nonce)
        payload = f"{timestamp}:{nonce}".encode('utf-8')
        signature = hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()
        
        url = info.requestUrl().toString()
        
        # Inject the Headers
        info.setHttpHeader(b"X-Exam-Time", timestamp.encode('utf-8'))
        info.setHttpHeader(b"X-Exam-Nonce", nonce.encode('utf-8'))
        info.setHttpHeader(b"X-Exam-Signature", signature.encode('utf-8'))
