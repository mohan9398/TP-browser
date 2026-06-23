# -*- coding: utf-8 -*-
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineSettings,
    QWebEngineProfile,
    QWebEngineCertificateError,
)
from secure_browser.core.config import ALLOWED_DOMAINS, USER_AGENT
 
class SecurePage(QWebEnginePage):
    def __init__(self, parent=None, browser_window=None):
        super().__init__(parent)
        self.browser_window = browser_window
        self._inject_webrtc_monitor()
        self._configure_settings()
 
    def _inject_webrtc_monitor(self):
        """Inject JS to intercept and log all camera/microphone requests from the website."""
        from PyQt6.QtWebEngineCore import QWebEngineScript
        
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setName("webrtc-monitor")
        
        # Check if the API even exists, and log the Secure Context status
        js_code = """
        (function() {
            console.log("[INJECTED JS] Page loaded. SecureContext:", window.isSecureContext);
            console.log("[INJECTED JS] navigator.mediaDevices exists:", !!navigator.mediaDevices);
            
            if (!navigator.mediaDevices) {
                console.error("[INJECTED JS] CRITICAL FATAL: navigator.mediaDevices is completely missing. Chromium has disabled the Camera API because it considers this page INSECURE.");
            } else if (!navigator.mediaDevices.getUserMedia) {
                console.error("[INJECTED JS] CRITICAL FATAL: navigator.mediaDevices exists, but getUserMedia is missing.");
            } else {
                const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                navigator.mediaDevices.getUserMedia = function(constraints) {
                    console.log("[INJECTED JS] Site requested media:", JSON.stringify(constraints));
                    return originalGetUserMedia(constraints).then(function(stream) {
                        console.log("[INJECTED JS] Camera access GRANTED by browser engine.");
                        return stream;
                    }).catch(function(err) {
                        console.error("[INJECTED JS] Camera access DENIED. Error details:", err.name, err.message);
                        throw err;
                    });
                };
            }
        })();
        """
        script.setSourceCode(js_code)
        self.profile().scripts().insert(script)
 
    def _configure_settings(self):
        # ── Diagnostic: log exactly what flags Chromium received ────────────
        import os as _os
        _active_flags = _os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "<NOT SET>")
        _is_secure_origin_flag_present = "--unsafely-treat-insecure-origin-as-secure" in _active_flags
 
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, False)
 
        # WebRTC: allow LAN ICE candidates (required for local-network proctoring)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
 
        # Allow HTTP pages full access
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)
 
        self.profile().setHttpUserAgent(USER_AGENT)
        # Memory cache avoids stale permission-denied entries from disk
        self.profile().setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
 
        # Try Qt 6.8+ profile-level permission grant (most reliable)
        self._try_grant_profile_permissions()
 
        # Always connect signal as fallback for ALL Qt versions
        self.featurePermissionRequested.connect(self._aggressively_grant)
 
    # All media features we want to auto-grant
    _MEDIA_FEATURES = [
        QWebEnginePage.Feature.MediaAudioCapture,
        QWebEnginePage.Feature.MediaVideoCapture,
        QWebEnginePage.Feature.MediaAudioVideoCapture,
        QWebEnginePage.Feature.DesktopVideoCapture,
        QWebEnginePage.Feature.DesktopAudioVideoCapture,
    ]
 
    def _aggressively_grant(self, url, feature):
        """Page-level fallback: grant any media permission the moment it is requested."""
        if feature in self._MEDIA_FEATURES:
            self.setFeaturePermission(
                url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            )
 
    def _try_grant_profile_permissions(self):
        """
        Qt 6.8+ only: pre-grant camera + mic at the profile level for every
        allowed domain so Chromium never even raises a permission prompt.
        Silently skipped on older Qt (signal fallback covers those).
        """
        try:
            from PyQt6.QtWebEngineCore import QWebEnginePermission
            profile = self.profile()
            for domain in ALLOWED_DOMAINS:
                for scheme in ("http", "https"):
                    origin = QUrl(f"{scheme}://{domain}")
                    for ptype in (
                        QWebEnginePermission.PermissionType.MediaAudioCapture,
                        QWebEnginePermission.PermissionType.MediaVideoCapture,
                        QWebEnginePermission.PermissionType.MediaAudioVideoCapture,
                    ):
                        try:
                            profile.setPermission(
                                origin, ptype, QWebEnginePermission.State.Granted
                            )
                        except Exception:
                            pass
        except (ImportError, AttributeError):
            pass
 
    def createWindow(self, _type):
        """Handle requests for new windows/tabs."""
        if self.browser_window:
            return self.browser_window.create_new_tab()
        return None
 
    def acceptNavigationRequest(self, url, nav_type, is_main):
        """Strict domain filtering."""
        host = url.host().lower()
        scheme = url.scheme().lower()
 
        # Allow internal schemes
        if scheme in ("about", "data", "chrome"):
            return True
        
        # Always allow proxied localhost requests
        if host in ("127.0.0.1", "localhost"):
            return True
 
        # Check allowed domains
        for domain in ALLOWED_DOMAINS:
            if host == domain or host.endswith(f".{domain}"):
                return True
        
        return False
 
    def certificateError(self, error: QWebEngineCertificateError):
        """
        Handle SSL errors.
        WARNING: Generous acceptance for now due to self-signed certs in exam environment.
        TODO: Implement proper certificate pinning or CA check later.
        """
        return True # Accepted for now based on user requirements
 
    def javaScriptConsoleMessage(self, level, message, line, source):
        # Intentionally a no-op: suppresses Chromium's default console output to
        # stderr (which ran on every page log/warn/error) with zero per-message
        # work. Re-add lightweight handling here only if real diagnostics are needed.
        return
 