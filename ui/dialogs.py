# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, 
    QProgressBar, QPushButton, QListWidgetItem, QInputDialog, 
    QLineEdit, QMessageBox
)
from secure_browser.network.wifi_manager import WiFiManager

class WifiDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wi-Fi Manager")
        self.setMinimumSize(400, 300)
        self.setModal(True)
        self.wifi_mgr = WiFiManager()
        self.wifi_mgr.scan_complete.connect(self.on_scan_complete)
        self.wifi_mgr.connect_complete.connect(self.on_connect_complete)

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
        self.btn_close = QPushButton("✖ Close")
        
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_connect)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_connect.clicked.connect(self.connect)
        self.btn_close.clicked.connect(self.close)

        self.refresh()

    def refresh(self):
        self.list.clear()
        self.status_label.setText("Scanning for networks...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.btn_refresh.setEnabled(False)
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
            self.list.addItem(QListWidgetItem(f"📶 {ssid}"))

    def connect(self):
        item = self.list.currentItem()
        if not item: return

        ssid = item.text().replace("📶 ", "")
        password, ok = QInputDialog.getText(
            self, "Network Password", f"Password for '{ssid}':",
            QLineEdit.EchoMode.Password
        )
        if not ok: return

        self.status_label.setText(f"Connecting to {ssid}...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.btn_connect.setEnabled(False)
        self.wifi_mgr.connect_async(ssid, password)

    def on_connect_complete(self, success, message):
        self.progress.setVisible(False)
        self.btn_connect.setEnabled(True)
        if success:
            QMessageBox.information(self, "Success", message)
            self.accept() # Checks QDialog.DialogCode.Accepted
        else:
            QMessageBox.critical(self, "Connection Failed", message)
            self.status_label.setText("Connection failed")
