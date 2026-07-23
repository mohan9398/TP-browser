# -*- coding: utf-8 -*-
"""
Small standalone window shown by main.py (launcher / parent process only,
never inside the secure exam desktop) when a newer version is available.
Downloading starts automatically; installing requires an explicit click.
"""
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QProgressBar

from secure_browser.network.updater import (
    download_installer,
    launch_silent_install_and_relaunch,
)


class _DownloadWorker(QThread):
    finished_ok = pyqtSignal(str)   # installer_path
    finished_failed = pyqtSignal()

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        installer_path = download_installer(self._url)
        if installer_path:
            self.finished_ok.emit(installer_path)
        else:
            self.finished_failed.emit()


class UpdateProgressWindow(QWidget):
    """
    Call show_and_start(remote_version, url) after construction. The window
    closes itself if the download fails; if the user clicks "install", the
    process exits (see updater.launch_silent_install_and_relaunch) and this
    window never needs to close normally in that path.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Secure Exam Browser — Update")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self.resize(380, 160)

        self.installer_path = None
        self._worker = None

        self.status_label = QLabel("Downloading update...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 15px;")

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setTextVisible(False)

        self.install_button = QPushButton("Update ready — click to install")
        self.install_button.setVisible(False)
        self.install_button.clicked.connect(self._on_install_clicked)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.install_button)
        self.setLayout(layout)

    def start_download(self, remote_version: str, url: str):
        self.status_label.setText(f"Downloading update {remote_version}...")
        self._worker = _DownloadWorker(url, parent=self)
        self._worker.finished_ok.connect(self._on_download_finished)
        self._worker.finished_failed.connect(self._on_download_failed)
        self._worker.start()

    def _on_download_finished(self, installer_path: str):
        self.installer_path = installer_path
        self.status_label.setText("Update downloaded.")
        self.progress.setVisible(False)
        self.install_button.setVisible(True)

    def _on_download_failed(self):
        self.close()

    def _on_install_clicked(self):
        self.install_button.setEnabled(False)
        self.status_label.setText("Installing... the app will restart.")
        # Does not return -- terminates this process.
        launch_silent_install_and_relaunch(self.installer_path)
