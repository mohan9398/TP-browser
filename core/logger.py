# -*- coding: utf-8 -*-
import sys
import os
import time
import threading
from collections import deque

class Logger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Logger, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.buffer = deque(maxlen=1000)
        self.lock = threading.Lock()
        self.log_path = None
        self._initialized = True
        self._setup_path()

    def _setup_path(self):
        pass

    def log(self, msg: str):
        pass

# Global instance
logger = Logger()
