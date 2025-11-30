# ============================================================
#               Linua Updater v2.0 – Final Build
# ============================================================

import os
import sys
import shutil
import zipfile
import tempfile
import subprocess
import requests
import webbrowser

from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, pyqtSlot
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QFileDialog,
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QCheckBox, QScrollArea,
    QMessageBox, QProgressBar, QButtonGroup
)


# ============================================================
#                     LOG WRITER
# ============================================================

class LogWriter:
    def __init__(self, widget):
        self.widget = widget

    def write(self, text):
        self.widget.append(text)
        self.widget.ensureCursorVisible()


# ============================================================
#                   7ZIP DETECTOR (HYBRID)
# ============================================================

class SevenZipFinder:
    POSSIBLE_LOCATIONS = [
        "7z.exe",
        "7za.exe",
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files\7-Zip\7za.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7za.exe",
    ]

    def __init__(self, logger):
        self.logger = logger

    def find(self):
        # 1) check local directory (same folder as EXE)
        local = os.path.join(os.path.dirname(sys.argv[0]), "7z.exe")
        if os.path.exists(local):
            if self.logger:
                self.logger.write("Using local 7z.exe")
            return local

        # 2) check system locations
        for p in self.POSSIBLE_LOCATIONS:
            if os.path.exists(p):
                if self.logger:
                    self.logger.write(f"Found 7zip at: {p}")
                return p

        # 3) check via PATH
        try:
            result = subprocess.run(["where", "7z"], capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if self.logger:
                    self.logger.write(f"Found 7zip via PATH: {path}")
                return path
        except:
            pass

        # 4) 7zip not found
        if self.logger:
            self.logger.write("7z.exe not found. Multipart DLC will not extract.")
        return None


# ============================================================
#                  ADVANCED DOWNLOAD ENGINE
# ============================================================

class DownloadEngine:
    """
    Stable downloader with mirrors
    """

    def __init__(self, logger):
        self.logger = logger

    def log(self, text):
        if self.logger:
            self.logger.write(text)

    def download(self, url, out_path, dlc_name=None):
        """Основной метод скачивания"""
        try:
            # Показываем название DLC вместо ссылки
            display_text = dlc_name if dlc_name else url
            self.log(f"Downloading: {display_text}")

            # Для MediaFire используем прямые ссылки без зеркал
            if 'mediafire.com' in url:
                return self.download_direct(url, out_path)
            else:
                # Для GitHub используем зеркала
                return self.download_with_mirrors(url, out_path)

        except Exception as e:
            return False, f"Download error: {str(e)}"

    def download_direct(self, url, out_path):
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                if r.status_code != 200:
                    return False, f"HTTP {r.status_code}"
                
                # Проверка content-type для безопасности
                content_type = r.headers.get('content-type', '')
                if 'application/zip' not in content_type and 'application/octet-stream' not in content_type:
                    return False, f"Invalid content type: {content_type}"

                total = int(r.headers.get("content-length", 0))
                
                # УВЕЛИЧИМ ЛИМИТ ДО 10GB ДЛЯ КРУПНЫХ DLC
                if total > 10 * 1024 * 1024 * 1024:  # 10GB
                    return False, "File too large (max 10GB)"

                downloaded = 0
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                # Проверить что файл не пустой
                if downloaded == 0:
                    return False, "Empty file downloaded"

                if total > 0 and downloaded < total * 0.90:
                    return False, f"File incomplete ({downloaded}/{total})"

                return True, "OK"

        except Exception as e:
            return False, f"Direct download error: {str(e)}"

    def download_with_mirrors(self, url, out_path):
        """Скачивание с зеркалами (для GitHub)"""
        mirrors = self.build_mirrors(url)

        for m in mirrors:
            try:
                self.log(f"Trying mirror: {m}")

                with requests.get(m, stream=True, timeout=25) as r:
                    if r.status_code != 200:
                        self.log(f"Mirror failed: {m}")
                        continue

                    total = int(r.headers.get("content-length", 0))
                    downloaded = 0

                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)

                    # Validate download
                    if total > 0 and downloaded < total * 0.90:
                        self.log("File incomplete. Trying next mirror.")
                        continue

                    return True, "OK"

            except Exception as e:
                self.log(f"Mirror error: {str(e)}")
                continue

        return False, "All mirrors failed"

    def build_mirrors(self, url):
        """Создать список зеркал для GitHub"""
        return [
            url,
            f"https://ghproxy.com/{url}",
            f"https://raw.kkgithub.com/{url.replace('https://github.com/', '')}",
            f"https://mirror.ghproxy.com/{url}",
        ]


# ============================================================
#                     ZIP / 7Z SAFE EXTRACTOR
# ============================================================

class Extractor:
    def __init__(self, logger):
        self.logger = logger

    def log(self, text):
        if self.logger:
            self.logger.write(text)

    def extract_zip(self, file, out_dir):
        """Распаковать ZIP архив"""
        try:
            with zipfile.ZipFile(file, "r") as z:
                z.extractall(out_dir)
            return True, "OK"
        except Exception as e:
            return False, f"ZIP extraction error: {str(e)}"

    def extract_7z(self, seven, archive_path, out_dir):
        """Распаковать 7z архив"""
        try:
            cmd = [
                seven,
                "x",
                archive_path,
                f"-o{out_dir}",
                "-y"
            ]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            return True, "OK"

        except subprocess.CalledProcessError as e:
            return False, f"7z error: {e.stderr}"
        except subprocess.TimeoutExpired:
            return False, "7z extraction timeout"
        except Exception as e:
            return False, f"7z error: {str(e)}"


# ============================================================
#                    DLC INSTALL ENGINE
# ============================================================

class SingleDLCInstaller:
    """Установка одиночных DLC"""

    def __init__(self, dlc_id, info, game_path, downloader, extractor, logger):
        self.dlc = dlc_id
        self.info = info
        self.game = game_path
        self.dl = downloader
        self.ex = extractor
        self.logger = logger

    def log(self, t):
        if self.logger:
            self.logger.write(f"[{self.dlc}] {t}")

    def run(self):
        try:
            url = self.info.get("url")
            if not url:
                return False, "URL missing"

            temp = os.path.join(tempfile.gettempdir(), f"{self.dlc}.zip")

            self.log("Downloading...")
            # Передаем название DLC для красивого логирования
            dlc_name = f"{self.dlc} - {self.info.get('name', 'Unknown DLC')}"
            ok, reason = self.dl.download(url, temp, dlc_name)
            if not ok:
                return False, reason

            self.log("Extracting...")
            ok, reason = self.ex.extract_zip(temp, self.game)
            if not ok:
                return False, reason

            # Cleanup
            try:
                os.remove(temp)
            except:
                pass

            self.log("Installation completed successfully")
            return True, "OK"

        except Exception as e:
            return False, f"Installation error: {str(e)}"


# ============================================================
#               MULTIPART DLC INSTALLER
# ============================================================

class MultiPartInstaller:
    """Установка многодольных DLC"""

    def __init__(self, dlc_id, info, game_path, downloader, extractor, seven_path, logger):
        self.dlc = dlc_id
        self.info = info
        self.game = game_path
        self.dl = downloader
        self.ex = extractor
        self.seven = seven_path
        self.logger = logger

    def log(self, t):
        if self.logger:
            self.logger.write(f"[{self.dlc}] {t}")

    def run(self):
        try:
            if not self.seven:
                return False, "7z.exe not found"

            parts = self.info.get("parts", [])
            if not parts:
                return False, "No parts defined"

            downloaded = []

            # Download all parts
            for i, url in enumerate(parts):
                name = f"{self.dlc}.7z.{str(i+1).zfill(3)}"
                out = os.path.join(tempfile.gettempdir(), name)

                self.log(f"Downloading part {i+1}/{len(parts)}...")
                # Передаем название DLC для красивого логирования
                dlc_name = f"{self.dlc} - {self.info.get('name', 'Unknown DLC')} [Part {i+1}]"
                ok, reason = self.dl.download(url, out, dlc_name)
                if not ok:
                    return False, reason

                downloaded.append(out)

            # Extract via 7-Zip
            part1 = downloaded[0]
            self.log("Extracting multipart archive...")

            ok, reason = self.ex.extract_7z(self.seven, part1, self.game)
            if not ok:
                return False, reason

            # Cleanup
            for f in downloaded:
                try:
                    os.remove(f)
                except:
                    pass

            self.log("Installation completed successfully")
            return True, "OK"

        except Exception as e:
            return False, f"Multipart installation error: {str(e)}"


# ============================================================
#                 INSTALLATION THREADS
# ============================================================

class ZipInstallThread(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(str, bool, str)

    def __init__(self, dlc_id, info, game_path, downloader, extractor, logger):
        super().__init__()
        self.dlc = dlc_id
        self.info = info
        self.game = game_path
        self.downloader = downloader
        self.extractor = extractor
        self.logger = logger

    def run(self):
        inst = SingleDLCInstaller(
            self.dlc, self.info, self.game,
            self.downloader, self.extractor, self.logger
        )
        success, reason = inst.run()
        self.done.emit(self.dlc, success, reason)


class MultiPartInstallThread(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(str, bool, str)

    def __init__(self, dlc_id, info, game_path, downloader, extractor, logger):
        super().__init__()
        self.dlc = dlc_id
        self.info = info
        self.game = game_path
        self.downloader = downloader
        self.extractor = extractor
        self.logger = logger

    def run(self):
        # Find 7z when thread starts
        seven_finder = SevenZipFinder(self.logger)
        seven_path = seven_finder.find()
        
        if not seven_path:
            self.log.emit(f"[{self.dlc}] ERROR: 7-zip not found")
            self.done.emit(self.dlc, False, "7-zip not found")
            return

        inst = MultiPartInstaller(
            self.dlc, self.info, self.game,
            self.downloader, self.extractor,
            seven_path, self.logger
        )
        success, reason = inst.run()
        self.done.emit(self.dlc, success, reason)


# ============================================================
#                           REPAIR ENGINE
# ============================================================

class RepairEngine:
    """Система восстановления папки Sims 4"""

    def __init__(self, game_path, logger):
        self.game = Path(game_path)
        self.logger = logger

    def log(self, msg):
        if self.logger:
            self.logger.write(msg)

    def run(self):
        try:
            if not self.game.exists():
                self.log("Invalid game path")
                return False

            self.log("Starting deep repair...")

            self.check_structure()
            self.check_executables()
            self.clean_empty_dlc()
            self.clean_temp_files()

            self.log("Repair completed successfully")
            return True

        except Exception as e:
            self.log(f"Repair failed: {e}")
            return False

    def check_structure(self):
        self.log("Checking game structure...")
        required = ["Game", "Data", "Delta"]
        for f in required:
            if not (self.game / f).exists():
                self.log(f"Missing folder: {f}")

    def check_executables(self):
        self.log("Checking executables...")
        exe = self.game / "Game" / "Bin" / "TS4_x64.exe"
        if not exe.exists():
            self.log("TS4_x64.exe missing - game may not run")

    def clean_empty_dlc(self):
        self.log("Cleaning empty DLC folders...")
        for item in self.game.iterdir():
            name = item.name.upper()
            if name.startswith(("EP", "GP", "SP", "FP")) and item.is_dir():
                if not any(item.iterdir()):
                    self.log(f"Removing empty folder: {name}")
                    try:
                        shutil.rmtree(item, ignore_errors=True)
                    except:
                        pass

    def clean_temp_files(self):
        self.log("Cleaning temp files...")
        temp = Path(tempfile.gettempdir())
        patterns = [".7z.001", ".7z.002", ".zip", ".tmp"]
        
        for f in temp.iterdir():
            if any(f.name.endswith(pattern) for pattern in patterns):
                try:
                    f.unlink()
                except:
                    pass


# ============================================================
#                      REPAIR THREAD
# ============================================================

class RepairThread(QThread):
    done = pyqtSignal(bool)

    def __init__(self, game_path, logger):
        super().__init__()
        self.game_path = game_path
        self.logger = logger

    def run(self):
        engine = RepairEngine(self.game_path, self.logger)
        ok = engine.run()
        self.done.emit(ok)


# ============================================================
#                    AUTO UPDATE CHECKER
# ============================================================

class AutoUpdateChecker:
    RAW_URL = "https://raw.githubusercontent.com/l1ntol/Linua-Updater/main/version.txt"

    def __init__(self, logger, parent):
        self.logger = logger
        self.parent = parent

    def check(self):
        try:
            self.logger.write("Checking for updates...")
            r = requests.get(self.RAW_URL, timeout=5)
            if r.status_code == 200:
                latest = r.text.strip()
                current = "2.0"
                if latest != current:
                    self.notify(latest)
        except:
            pass

    def notify(self, latest):
        dlg = QMessageBox(self.parent)
        dlg.setWindowTitle("Update Available")
        dlg.setText(f"New version {latest} is available.")
        dlg.setInformativeText("Open GitHub?")
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if dlg.exec() == QMessageBox.StandardButton.Yes:
            webbrowser.open("https://github.com/l1ntol/Linua-Updater")


# ============================================================
#                APPLICATION CONTROLLER
# ============================================================

class AppController:
    def __init__(self, logger):
        self.logger = logger
        self.downloader = DownloadEngine(logger)
        self.extractor = Extractor(logger)

    def install_zip(self, dlc_id, dlc_info, game_path, finished_callback):
        worker = ZipInstallThread(
            dlc_id, dlc_info, game_path,
            self.downloader,
            self.extractor,
            self.logger
        )
        worker.log.connect(self.logger.write)
        worker.done.connect(finished_callback)
        worker.start()
        return worker

    def install_multipart(self, dlc_id, dlc_info, game_path, finished_callback):
        worker = MultiPartInstallThread(
            dlc_id, dlc_info, game_path,
            self.downloader,
            self.extractor,
            self.logger
        )
        worker.log.connect(self.logger.write)
        worker.done.connect(finished_callback)
        worker.start()
        return worker

    def run_repair(self, game_path, finished_callback):
        worker = RepairThread(game_path, self.logger)
        worker.done.connect(finished_callback)
        worker.start()
        return worker

# ============================================================
#                    MAIN APPLICATION WINDOW
# ============================================================

class LinuaUpdater(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Linua Updater v2.0") 
        self.setFixedSize(620, 520)

        self.logger = None
        self.dlc_db = self.load_dlc_database()

        self.progress_total = 0
        self.progress_done = 0
        self.active_threads = []

        # UI
        self.setup_ui()
        self.apply_dark_theme()

        # attach logger AFTER UI
        self.logger = LogWriter(self.log_text)

        # auto detect game
        QTimer.singleShot(200, self.auto_detect)

        # auto update check
        QTimer.singleShot(500, lambda: AutoUpdateChecker(self.logger, self).check())

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # title
        title = QLabel("Linua Updater v2.0")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px; color: white;")
        layout.addWidget(title)

        # path select
        path_label = QLabel("Select your The Sims 4 folder:")
        path_label.setStyleSheet("color: white;")
        layout.addWidget(path_label)

        row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("C:\\Program Files (x86)\\Steam\\steamapps\\common\\The Sims 4")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse_folder)

        row.addWidget(self.path_input)
        row.addWidget(browse)
        layout.addLayout(row)

        # update + repair + cancel
        row2 = QHBoxLayout()
        self.update_btn = QPushButton("Update")
        self.repair_btn = QPushButton("Repair")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_installation)
        self.cancel_btn.setVisible(False)

        row2.addWidget(self.update_btn)
        row2.addWidget(self.repair_btn)
        row2.addWidget(self.cancel_btn)
        layout.addLayout(row2)

        self.update_btn.clicked.connect(self.start_update)
        self.repair_btn.clicked.connect(self.start_repair)

        # progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # log window
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_text)

        # info
        info = QLabel(
            "The only legitimate sources of this program are listed in the readme.\n"
            "This program is free — if you paid for it, you were scammed.\n\n"
            "Select your Sims 4 folder, then press Update.\n"
            "Repair checks core game files."
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #2a2a2a; padding: 10px; border-radius: 6px; color: white;")
        layout.addWidget(info)

    def apply_dark_theme(self):
        css = """
            QMainWindow, QDialog {
                background-color: #1e1e1e;
                color: white;
            }
            QLineEdit, QTextEdit {
                background-color: #0a0a0a;
                color: #00ff00;
                border: 1px solid #444;
            }
            QPushButton {
                background-color: #333;
                border: 1px solid #555;
                padding: 7px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #222; }
            QLabel { color: white; }
            QProgressBar {
                background-color: #222;
                border: 1px solid #555;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #0078d7;
            }
        """
        self.setStyleSheet(css)

    def browse_folder(self):
        """Открыть диалог выбора папки"""
        self.log_message("Opening folder browser...")
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select The Sims 4 Folder",
            self.path_input.text() or "C:\\"
        )
        if folder:
            self.path_input.setText(folder)
            self.log_message("Folder selected")

    def log_message(self, message, level="INFO"):
        """Улучшенное логирование с уровнями"""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        level_color = {
            "INFO": "white",
            "WARNING": "yellow", 
            "ERROR": "red",
            "SUCCESS": "lightgreen"
        }
        color = level_color.get(level, "white")
        
        self.log_text.append(f'<font color="{color}">{timestamp} [{level}] {message}</font>')

    def auto_detect(self):
        """Автоматическое обнаружение игры"""
        self.log_message("Detecting The Sims 4...")

        drives = ["C", "D", "E", "F", "G", "H"]
        paths = [
            r"\Program Files (x86)\Steam\steamapps\common\The Sims 4",
            r"\Program Files\Steam\steamapps\common\The Sims 4", 
            r"\SteamLibrary\steamapps\common\The Sims 4",
            r"\Program Files\EA Games\The Sims 4",
            r"\Program Files (x86)\EA Games\The Sims 4",
            r"\Program Files (x86)\Origin Games\The Sims 4",
            r"\The Sims 4",
        ]

        for drive in drives:
            for path in paths:
                full_path = f"{drive}:{path}"
                if os.path.exists(full_path):
                    self.path_input.setText(full_path)
                    self.log_message(f"Found game: {full_path}")
                    return

        self.log_message("Game not found automatically")

    def validate_game_path(self, path):
        """Проверка что путь действительно ведет к The Sims 4"""
        if not path or not os.path.exists(path):
            return False, "Path does not exist"
        
        path_obj = Path(path)
        
        # Базовые проверки структуры папки The Sims 4
        required_folders = ["Game", "Data"]
        for folder in required_folders:
            if not (path_obj / folder).exists():
                return False, f"Missing required folder: {folder}"
        
        # Проверка ключевых исполняемых файлов
        possible_executables = [
            "Game/Bin/TS4_x64.exe",
            "Game/Bin/TS4.exe",
            "Game/Bin/TS4_x86.exe"
        ]
        
        exe_found = any((path_obj / exe).exists() for exe in possible_executables)
        if not exe_found:
            return False, "No Sims 4 executable found"
        
        return True, "Valid Sims 4 folder"

    def check_disk_space(self, path, required_gb=10):
        """Проверка свободного места на диске"""
        try:
            total, used, free = shutil.disk_usage(path)
            free_gb = free // (2**30)  # Конвертируем в GB
            return free_gb >= required_gb, free_gb
        except Exception as e:
            self.log_message(f"Could not check disk space: {e}")
            return True, 0  # Если проверка не удалась, продолжаем

    def load_dlc_database(self):
        """Загрузка базы данных DLC"""
        db = {
            # Expansion Packs
            "EP01": {"name": "Get to Work", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP01/Sims4_DLC_EP01_Get_to_Work.zip"},
            "EP02": {"name": "Get Together", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP02/Sims4_DLC_EP02_Get_Together.zip"},
            
            # MediaFire links for large DLC
            "EP03": {"name": "City Living", "url": "https://download1077.mediafire.com/gk01keeidixgG9nuc3hCq_nnyHf0IcjXr_33TxOq9eKMEmbIztWc2OhOEd1zumzk_lJjpWfaauZcFHXJn4gcJ3ra79T3p5o9mwo9ogZf5vdL6ln_PHNUQaF7SqNEJQawYwwoE-kaM1YgVpLTO0PFUViERIDdp9ltzzp4D75F4L7ijA/4lg732ou6oy1f4k/Sims4_DLC_EP03_City_Living.zip"},
            
            "EP04": {"name": "Cats and Dogs", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP04/Sims4_DLC_EP04_Cats_and_Dogs.zip"},
            "EP05": {"name": "Seasons", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP05/Sims4_DLC_EP05_Seasons.zip"},
            
            "EP06": {"name": "Get Famous", "url": "https://download1474.mediafire.com/amqx09qcwncgoiqRYqPMWw4igfV51JYYCnPuCH0CFxxSf2UCTU217D0iDywqdAgTfhb8eGWw2Z6VEVPTXXxrE3mapdcu4T6gFnQ4XFaqR72Yys0E8KgZ_2OLnBe0zxNImGZC_ubqY2hUNad-Z6aXU86GmRxmlSCi9_OjwfODmZP_Ww/x07rc8c1nqu0sy5/Sims4_DLC_EP06_Get_Famous.zip"},
            
            "EP07": {"name": "Island Living", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP07/Sims4_DLC_EP07_Island_Living.zip"},
            "EP08": {"name": "Discover University", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP08/Sims4_DLC_EP08_Discover_University.zip"},
            "EP09": {"name": "Eco Lifestyle", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP09/Sims4_DLC_EP09_Eco_Lifestyle.zip"},
            "EP10": {"name": "Snowy Escape", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP10/Sims4_DLC_EP10_Snowy_Escape.zip"},
            "EP11": {"name": "Cottage Living", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP11/Sims4_DLC_EP11_Cottage_Living.zip"},
            "EP12": {"name": "High School Years", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP12/Sims4_DLC_EP12_High_School_Years.zip"},
            "EP13": {"name": "Growing Together", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP13/Sims4_DLC_EP13_Growing_Together.zip"},
            "EP14": {"name": "Horse Ranch", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP14/Sims4_DLC_EP14_Horse_Ranch.zip"},
            "EP15": {"name": "For Rent", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP15/Sims4_DLC_EP15_For_Rent.zip"},
            "EP16": {"name": "Lovestruck", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP16/Sims4_DLC_EP16_Lovestruck.zip"},

            # Game Packs
            "GP01": {"name": "Outdoor Retreat", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP01/Sims4_DLC_GP01_Outdoor_Retreat.zip"},
            "GP02": {"name": "Spa Day", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP02/Sims4_DLC_GP02_Spa_Day.zip"},
            "GP03": {"name": "Dine Out", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP03/Sims4_DLC_GP03_Dine_Out.zip"},
            "GP04": {"name": "Vampires", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP04/Sims4_DLC_GP04_Vampires.zip"},
            "GP05": {"name": "Parenthood", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP05/Sims4_DLC_GP05_Parenthood.zip"},
            "GP06": {"name": "Jungle Adventure", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP06/Sims4_DLC_GP06_Jungle_Adventure.zip"},
            "GP07": {"name": "StrangerVille", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP07/Sims4_DLC_GP07_StrangerVille.zip"},
            "GP08": {"name": "Realm of Magic", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP08/Sims4_DLC_GP08_Realm_of_Magic.zip"},
            "GP09": {"name": "Star Wars: Journey to Batuu", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP09/Sims4_DLC_GP09_Star_Wars_Journey_to_Batuu.zip"},
            "GP10": {"name": "Dream Home Decorator", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP10/Sims4_DLC_GP10_Dream_Home_Decorator.zip"},
            "GP11": {"name": "My Wedding Stories", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP11/Sims4_DLC_GP11_My_Wedding_Stories.zip"},
            "GP12": {"name": "Werewolves", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/GP12/Sims4_DLC_GP12_Werewolves.zip"},

            # Stuff Packs
            "SP01": {"name": "Luxury Party Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP01/Sims4_DLC_SP01_Luxury_Party_Stuff.zip"},
            "SP02": {"name": "Perfect Patio Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP02/Sims4_DLC_SP02_Perfect_Patio_Stuff.zip"},
            "SP03": {"name": "Cool Kitchen Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP03/Sims4_DLC_SP03_Cool_Kitchen_Stuff.zip"},
            "SP04": {"name": "Spooky Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP04/Sims4_DLC_SP04_Spooky_Stuff.zip"},
            "SP05": {"name": "Movie Hangout Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP05/Sims4_DLC_SP05_Movie_Hangout_Stuff.zip"},
            "SP06": {"name": "Romantic Garden Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP06/Sims4_DLC_SP06_Romantic_Garden_Stuff.zip"},
            "SP07": {"name": "Kids Room Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP07/Sims4_DLC_SP07_Kids_Room_Stuff.zip"},
            "SP08": {"name": "Backyard Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP08/Sims4_DLC_SP08_Backyard_Stuff.zip"},
            "SP09": {"name": "Vintage Glamour Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP09/Sims4_DLC_SP09_Vintage_Glamour_Stuff.zip"},
            "SP10": {"name": "Bowling Night Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP10/Sims4_DLC_SP10_Bowling_Night_Stuff.zip"},
            "SP11": {"name": "Fitness Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP11/Sims4_DLC_SP11_Fitness_Stuff.zip"},
            "SP12": {"name": "Toddler Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP12/Sims4_DLC_SP12_Toddler_Stuff.zip"},
            "SP13": {"name": "Laundry Day Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP13/Sims4_DLC_SP13_Laundry_Day_Stuff.zip"},
            "SP14": {"name": "My First Pet Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP14/Sims4_DLC_SP14_My_First_Pet_Stuff.zip"},
            "SP15": {"name": "Moschino Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP15/Sims4_DLC_SP15_Moschino_Stuff.zip"},
            "SP16": {"name": "Tiny Living Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP16/Sims4_DLC_SP16_Tiny_Living_Stuff.zip"},
            "SP17": {"name": "Nifty Knitting", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP17/Sims4_DLC_SP17_Nifty_Knitting.zip"},
            "SP18": {"name": "Paranormal Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP18/Sims4_DLC_SP18_Paranormal_Stuff.zip"},

            # Free Packs
            "FP01": {"name": "Holiday Celebration Pack", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/FP01/Sims4_DLC_FP01_Holiday_Celebration_Pack.zip"},
        }
        return db

    def detect_installed(self, game_path):
        """Обнаружение установленных DLC"""
        installed = set()
        if not os.path.exists(game_path):
            return installed
        for item in os.listdir(game_path):
            u = item.upper()
            if u.startswith(("EP", "GP", "SP", "FP")):
                installed.add(u)
        return installed

    def start_update(self):
        """Обработчик кнопки Update"""
        try:
            path = self.path_input.text().strip()
            
            # Валидация пути
            if not path:
                self.log_message("Please select a game folder first.")
                return
            
            is_valid, message = self.validate_game_path(path)
            if not is_valid:
                self.log_message(f"Invalid game folder: {message}")
                reply = QMessageBox.question(
                    self, 
                    "Confirm Folder", 
                    f"The selected folder may not be a valid Sims 4 installation.\n\nReason: {message}\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            
            # Проверка свободного места
            has_space, free_gb = self.check_disk_space(path)
            if not has_space:
                self.log_message(f"ERROR: Not enough disk space. Only {free_gb}GB free, need at least 10GB")
                QMessageBox.critical(
                    self,
                    "Low Disk Space",
                    f"Only {free_gb}GB free space available.\nNeed at least 10GB for installation.\nPlease free up some space and try again."
                )
                return
            elif free_gb < 20:  # Предупреждение если мало места
                self.log_message(f"Warning: Only {free_gb}GB free space available")
            
            installed = self.detect_installed(path)
            
            dlg = DLCSelector(self)
            dlg.populate(self.dlc_db, installed)
            
            result = dlg.exec()
            if result != QDialog.DialogCode.Accepted:
                self.log_message("DLC selection cancelled.")
                return
                
            selected = dlg.get()
            if not selected:
                self.log_message("No DLC selected.")
                return
                
            self.start_install_process(selected, path)
            
        except Exception as e:
            self.log_message(f"Error in DLC selection: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to open DLC selector: {str(e)}")

    def start_install_process(self, selected, game_path):
        """Запуск процесса установки"""
        if not selected:
            self.log_message("No DLC selected for installation.")
            return
            
        # Проверяем наличие 7-zip для многодольных DLC
        multipart_dlc = [dlc for dlc in selected if "parts" in self.dlc_db[dlc]]
        if multipart_dlc:
            seven_finder = SevenZipFinder(self.logger)
            seven_path = seven_finder.find()
            if not seven_path:
                self.log_message("ERROR: 7-zip required for multipart DLC but not found!")
                msg = QMessageBox(self)
                msg.setWindowTitle("7-zip Required")
                msg.setText("Multipart DLC (EP03 City Living, EP06 Get Famous) require 7-zip.")
                msg.setInformativeText("Please install 7-zip from official website and try again.")
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg.exec()
                return

        self.controller = AppController(self.logger)

        self.progress_total = len(selected)
        self.progress_done = 0

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(self.progress_total)
        self.progress_bar.setValue(0)

        self.update_btn.setEnabled(False)
        self.repair_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

        self.log_message(f"Installing {len(selected)} DLC...")

        self.active_threads = []

        for dlc_id in selected:
            info = self.dlc_db[dlc_id]

            if "parts" in info and info["parts"]:
                t = self.controller.install_multipart(
                    dlc_id, info, game_path,
                    self.install_done
                )
            else:
                t = self.controller.install_zip(
                    dlc_id, info, game_path,
                    self.install_done
                )

            self.active_threads.append(t)

    def cancel_installation(self):
        """Отмена текущей установки"""
        if hasattr(self, 'active_threads'):
            for thread in self.active_threads:
                if thread.isRunning():
                    thread.terminate()
                    thread.wait(1000)
            self.active_threads.clear()
        
        self.progress_bar.setVisible(False)
        self.update_btn.setEnabled(True)
        self.repair_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.log_message("Installation cancelled")

    @pyqtSlot(str, bool, str)
    def install_done(self, dlc_id, success, reason):
        """Обработчик завершения установки DLC"""
        self.progress_done += 1
        self.progress_bar.setValue(self.progress_done)

        if success:
            self.log_message(f"{dlc_id} installed.", "SUCCESS")
        else:
            self.log_message(f"{dlc_id} failed — {reason}", "ERROR")

        if self.progress_done == self.progress_total:
            self.finish_install()

    def finish_install(self):
        """Завершение процесса установки"""
        self.log_message("Installation complete.", "SUCCESS")
        self.progress_bar.setVisible(False)

        self.update_btn.setEnabled(True)
        self.repair_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Done")
        dlg.setText("All selected DLC were installed.")
        dlg.exec()

    def start_repair(self):
        """Обработчик кнопки Repair"""
        path = self.path_input.text().strip()
        if not path or not os.path.isdir(path):
            self.log_message("Invalid game folder.")
            return

        self.log_message("Starting repair...")

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)

        self.controller = AppController(self.logger)
        self.repair_thread = self.controller.run_repair(
            path,
            self.repair_done
        )

    @pyqtSlot(bool)
    def repair_done(self, ok):
        """Обработчик завершения ремонта"""
        self.progress_bar.setVisible(False)

        if ok:
            self.log_message("Repair finished.", "SUCCESS")
        else:
            self.log_message("Repair failed.", "ERROR")

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Repair complete")
        dlg.setText("Repair process finished.")
        dlg.exec()


# ============================================================
#                        SELECT DLC DIALOG
# ============================================================

class DLCSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select DLC")
        self.setFixedSize(540, 640)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: white;
                padding: 5px;
            }
            QCheckBox {
                color: white;
                background-color: #2a2a2a;
                padding: 8px;
                border-radius: 3px;
                margin: 2px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #555;
                background-color: #333;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #0078d7;
                background-color: #0078d7;
            }
            QCheckBox:hover {
                background-color: #333;
            }
            QPushButton {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #444;
            }
            QPushButton:pressed {
                background-color: #222;
            }
            QScrollArea {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)

        self.info = QLabel("Select DLC you want to install.\nAlready installed DLC are hidden.")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: white; padding: 10px; background-color: #2a2a2a; border-radius: 4px;")
        layout.addWidget(self.info)

        self.check_all = QCheckBox("Select all")
        self.check_all.setStyleSheet("color: white; font-weight: bold; padding: 10px;")
        self.check_all.stateChanged.connect(self.toggle_all)
        layout.addWidget(self.check_all)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #2a2a2a; border: none;")
        layout.addWidget(scroll)

        self.container = QWidget()
        self.container.setStyleSheet("background-color: #2a2a2a;")
        self.layout_c = QVBoxLayout(self.container)
        self.layout_c.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.container)

        bottom = QHBoxLayout()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        bottom.addWidget(ok)
        bottom.addWidget(cancel)
        layout.addLayout(bottom)

        self.cbs = {}

    def toggle_all(self, state):
        val = (state == Qt.CheckState.Checked.value)
        for cb in self.cbs.values():
            cb.setChecked(val)

    def populate(self, db, installed):
        # clear
        for i in reversed(range(self.layout_c.count())):
            item = self.layout_c.itemAt(i)
            if item.widget():
                item.widget().deleteLater()

        self.cbs.clear()

        # Проверяем, есть ли доступные DLC для установки
        available_dlc = []
        for dlc_id, info in db.items():
            if dlc_id.upper() not in installed:
                available_dlc.append((dlc_id, info))

        # Если все DLC уже установлены
        if not available_dlc:
            no_dlc_label = QLabel("All DLC are already installed.")
            no_dlc_label.setStyleSheet("color: white; padding: 20px; text-align: center; font-size: 12px;")
            no_dlc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_c.addWidget(no_dlc_label)
            self.check_all.setVisible(False)
            return

        # Если есть доступные DLC, показываем их как обычно
        self.check_all.setVisible(True)
        
        categories = {
            "Expansion Packs": [],
            "Game Packs": [],
            "Stuff Packs": [],
            "Free Packs": []
        }

        for dlc_id, info in available_dlc:
            if dlc_id.startswith("EP"):
                categories["Expansion Packs"].append((dlc_id, info))
            elif dlc_id.startswith("GP"):
                categories["Game Packs"].append((dlc_id, info))
            elif dlc_id.startswith("FP"):
                categories["Free Packs"].append((dlc_id, info))
            else:
                categories["Stuff Packs"].append((dlc_id, info))

        # add items
        for cat, items in categories.items():
            if not items:
                continue

            header = QLabel(cat)
            header.setStyleSheet("font-weight: bold; margin-top: 10px; color: #0078d7; font-size: 12px;")
            self.layout_c.addWidget(header)

            for dlc_id, info in sorted(items):
                cb = QCheckBox(f"[{dlc_id}] {info['name']}")
                cb.setStyleSheet("color: white; font-size: 11px;")
                self.layout_c.addWidget(cb)
                self.cbs[dlc_id] = cb

    def get(self):
        return [dlc for dlc, cb in self.cbs.items() if cb.isChecked()]

# ============================================================
#                              MAIN
# ============================================================

def main():
    app = QApplication(sys.argv)
    win = LinuaUpdater()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()