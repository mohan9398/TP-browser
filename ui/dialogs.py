# -*- coding: utf-8 -*-
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QProgressBar, QPushButton, QListWidgetItem, QInputDialog,
    QLineEdit, QMessageBox
)
from secure_browser.network.wifi_manager import WiFiManager

# Role used to stash the raw SSID on each list item (separate from the
# decorated display text, which carries emoji / "Saved" markers).
SSID_ROLE = Qt.ItemDataRole.UserRole

class WifiDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wi-Fi Manager")
        self.setMinimumSize(400, 300)
        self.setModal(True)
        self.wifi_mgr = WiFiManager()
        self.wifi_mgr.scan_complete.connect(self.on_scan_complete)
        self.wifi_mgr.connect_complete.connect(self.on_connect_complete)
        self._saved_ssids = set()

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Select a network to connect")
        layout.addWidget(self.status_label)

        self.list = QListWidget()
        layout.addWidget(self.list)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_connect = QPushButton("🔗 Connect")
        self.btn_show_pw = QPushButton("🔑 Show Password")
        self.btn_close = QPushButton("✖ Close")

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_connect)
        btn_layout.addWidget(self.btn_show_pw)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_connect.clicked.connect(self.connect)
        self.btn_show_pw.clicked.connect(self.show_password)
        self.btn_close.clicked.connect(self.close)

        self.refresh()

    def refresh(self):
        self.list.clear()
        self.status_label.setText("Scanning for networks...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.btn_refresh.setEnabled(False)
        # Networks the PC already has credentials for → one-click reconnect.
        self._saved_ssids = self.wifi_mgr.get_saved_ssids()
        self.wifi_mgr.scan_async()

    def on_scan_complete(self, ssids):
        self.progress.setVisible(False)
        self.btn_refresh.setEnabled(True)
        self.list.clear()

        if not ssids or ssids[0].startswith(("No ", "Error", "Scan")):
            self.status_label.setText(ssids[0] if ssids else "No networks found")
            return

        self.status_label.setText(f"Found {len(ssids)} network(s)")
        for ssid in ssids:
            saved = ssid in self._saved_ssids
            label = f"🔒 {ssid}  —  Saved (tap Connect)" if saved else f"📶 {ssid}"
            item = QListWidgetItem(label)
            item.setData(SSID_ROLE, ssid)  # keep the clean SSID for connecting
            self.list.addItem(item)

    def _selected_ssid(self):
        item = self.list.currentItem()
        return item.data(SSID_ROLE) if item else None

    def connect(self):
        ssid = self._selected_ssid()
        if not ssid:
            return

        # Saved network: the OS already holds the password → connect directly,
        # no prompt needed. Only ask for a password on brand-new networks.
        if ssid in self._saved_ssids:
            password = ""
        else:
            password, ok = QInputDialog.getText(
                self, "Network Password", f"Password for '{ssid}':",
                QLineEdit.EchoMode.Password
            )
            if not ok:
                return

        self.status_label.setText(f"Connecting to {ssid}...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.btn_connect.setEnabled(False)
        self.wifi_mgr.connect_async(ssid, password)

    def show_password(self):
        """Reveal the stored password for a saved network (Windows + admin)."""
        ssid = self._selected_ssid()
        if not ssid:
            return
        if ssid not in self._saved_ssids:
            QMessageBox.information(
                self, "No Saved Password",
                f"'{ssid}' has no saved profile on this PC yet."
            )
            return
        pw = self.wifi_mgr.get_saved_password(ssid)
        if pw:
            QMessageBox.information(self, "Saved Password", f"{ssid}:\n\n{pw}")
        else:
            QMessageBox.warning(
                self, "Password Unavailable",
                "Could not read the saved password.\n\n"
                "Windows only reveals it when the browser is run as "
                "Administrator. You can still connect with one click."
            )

    def closeEvent(self, event):
        # Don't leave a scan running in the background after the dialog closes.
        self.wifi_mgr.cancel_scan()
        super().closeEvent(event)

    def on_connect_complete(self, success, message):
        self.progress.setVisible(False)
        self.btn_connect.setEnabled(True)
        if success:
            QMessageBox.information(self, "Success", message)
            self.accept() # Checks QDialog.DialogCode.Accepted
        else:
            QMessageBox.critical(self, "Connection Failed", message)
            self.status_label.setText("Connection failed")
