import sys
import os
import json
import urllib.request
import subprocess
import zipfile
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QLabel, QPushButton, QComboBox, QMessageBox, QTextEdit
)

def get_exe_dir():
    exe_path = os.path.join(os.getcwd(), "Apps", "exe")
    os.makedirs(exe_path, exist_ok=True)
    return exe_path

class GitHubStoreApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aether GitHub Store")
        self.setFixedSize(550, 480)
        self.setStyleSheet("background-color: #0B0C10; color: white;")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("🛍️ Aether GitHub Store")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #00E5FF;")

        subtitle = QLabel("Wähle eines deiner Repositories aus, um das Release zu laden:")
        subtitle.setStyleSheet("color: #AAAAAA; font-size: 12px;")

        self.repo_combo = QComboBox()
        self.repo_combo.setStyleSheet("background-color: #161822; color: white; padding: 10px; border-radius: 6px; border: 1px solid #333;")
        
        self.repos = [
            {"name": "Aether-Launcher", "repo": "pralle7747-max/Aether-Launcher"},
            {"name": "Bany-AI", "repo": "pralle7747-max/Bany-AI"},
            {"name": "Bany-AI-Phone-VERSION", "repo": "pralle7747-max/Bany-AI-Phone-VERSION"}
        ]
        for r in self.repos:
            self.repo_combo.addItem(f"{r['name']} ({r['repo']})", r['repo'])

        self.btn_download = QPushButton("📥 Herunterladen, Entpacken & Starten")
        self.btn_download.setFixedHeight(45)
        self.btn_download.setStyleSheet("background-color: #00E5FF; color: black; font-weight: bold; border-radius: 8px; font-size: 14px;")
        self.btn_download.clicked.connect(self.fetch_and_run_release)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("background-color: #08090C; color: #00E5FF; font-family: monospace; font-size: 11px; border: 1px solid #1A1D2A; border-radius: 6px;")
        self.log_box.setText("Bereit. Wähle ein Repository aus.")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(self.repo_combo)
        layout.addSpacing(10)
        layout.addWidget(self.btn_download)
        layout.addSpacing(15)
        layout.addWidget(self.log_box)

    def log(self, text):
        self.log_box.append(text)

    def fetch_and_run_release(self):
        repo = self.repo_combo.currentData()
        self.log(f"\nFrage GitHub Releases ab für: {repo}...")
        
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(api_url, headers={'User-Agent': 'AetherStore'})
        
        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                assets = data.get("assets", [])
                
                target_asset = None
                # Priorität auf .zip oder .exe
                for asset in assets:
                    name_lower = asset["name"].lower()
                    if name_lower.endswith(".zip") or name_lower.endswith(".exe"):
                        target_asset = asset
                        break
                
                if not target_asset and assets:
                    target_asset = assets[0]
                
                if not target_asset:
                    QMessageBox.warning(self, "Kein Asset", "Dieses Release enthält keine Dateien/Assets.")
                    self.log("Fehler: Keine Assets im Release gefunden.")
                    return
                
                file_url = target_asset["browser_download_url"]
                file_name = target_asset["name"]
                target_dir = get_exe_dir()
                target_path = os.path.join(target_dir, file_name)
                
                self.log(f"Lade {file_name} herunter...")
                urllib.request.urlretrieve(file_url, target_path)
                self.log(f"Gespeichert unter: {target_path}")
                
                # Prüfen, ob es eine ZIP-Datei ist -> Entpacken
                if file_name.lower().endswith(".zip"):
                    self.log("ZIP-Datei erkannt, entpacke...")
                    extract_path = os.path.join(target_dir, os.path.splitext(file_name)[0])
                    os.makedirs(extract_path, exist_ok=True)
                    
                    with zipfile.ZipFile(target_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_path)
                    self.log(f"Erfolgreich entpackt nach: {extract_path}")
                    
                    # Suche nach einer .exe im entpackten Ordner zum direkten Starten
                    exe_to_run = None
                    for root, dirs, files in os.walk(extract_path):
                        for file in files:
                            if file.lower().endswith(".exe"):
                                exe_to_run = os.path.join(root, file)
                                break
                        if exe_to_run:
                            break
                    
                    if exe_to_run:
                        self.log(f"Starte gefundene EXE: {exe_to_run}")
                        subprocess.Popen([exe_to_run], cwd=os.path.dirname(exe_to_run), shell=True)
                    else:
                        subprocess.Popen(f'explorer "{extract_path}"')
                        
                elif file_name.lower().endswith(".exe"):
                    self.log(f"Führe EXE aus: {target_path}")
                    subprocess.Popen([target_path], cwd=target_dir, shell=True)
                else:
                    subprocess.Popen(f'explorer "{target_dir}"')

                QMessageBox.information(self, "Erfolg", f"Aktion erfolgreich abgeschlossen für:\n{file_name}")

        except Exception as e:
            self.log(f"Fehler beim Abrufen: {e}")
            QMessageBox.warning(self, "Fehler", f"Konnte Release nicht laden: {e}\n(Hat das Repo ein gültiges Release mit Assets?)")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GitHubStoreApp()
    window.show()
    sys.exit(app.exec())