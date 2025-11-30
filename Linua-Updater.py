# ============================================================
#               Linua Updater v2.0 – Final Build
# ============================================================

import os
import sys
import shutil
import zipfile
import tempfile
import subprocess
import threading
import requests
import webbrowser
from pathlib import Path
from datetime import datetime
from datetime import datetime

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, pyqtSlot
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QFileDialog,
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QCheckBox, QScrollArea,
    QMessageBox, QProgressBar
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
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]

    def __init__(self, logger):
        self.logger = logger

    def find(self):
        # 1) check local directory (same folder as EXE)
        local = os.path.join(os.path.dirname(sys.argv[0]), "7z.exe")
        if os.path.exists(local):
            self.logger.write("Using local 7z.exe")
            return local

        # 2) check system locations
        for p in self.POSSIBLE_LOCATIONS:
            if os.path.exists(p):
                self.logger.write(f"Found 7zip at: {p}")
                return p

        # 3) 7zip not found
        self.logger.write("7z.exe not found. Multipart DLC will not extract.")

        msg = QMessageBox()
        msg.setWindowTitle("7zip not found")
        msg.setText("7z.exe was not found. Multipart DLC cannot be installed without it.")
        msg.setInformativeText("Open official download page?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if msg.exec() == QMessageBox.StandardButton.Yes:
            webbrowser.open("https://www.7-zip.org/")

        return None


# ============================================================
#                  ADVANCED DOWNLOAD ENGINE
# ============================================================

class DownloadEngine:
    """
    Stable downloader with mirrors:
    1. GitHub direct
    2. ghproxy.com
    3. raw.kkgithub.com
    4. moeyy.cn proxy
    5. api999 mirror
    """

    def __init__(self, logger):
        self.logger = logger

    def log(self, text):
        if self.logger:
            self.logger.write(text)

    # ------------------------------------------------------------
    #                     MIRROR BUILDER
    # ------------------------------------------------------------

    def build_mirrors(self, url):
        return [
            url,
            f"https://ghproxy.com/{url}",
            f"https://raw.kkgithub.com/{url.replace('https://github.com/', '')}",
            f"https://mirror.ghproxy.com/{url}",
            f"https://api999.github.io/gh-proxy/{url}",
        ]

    # ------------------------------------------------------------
    #                     MAIN DOWNLOAD
    # ------------------------------------------------------------

    def download(self, url, out_path):
        mirrors = self.build_mirrors(url)

        for m in mirrors:
            try:
                self.log(f"Downloading: {m}")

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


# ============================================================
#                     ZIP / 7Z SAFE EXTRACTOR
# ============================================================

class Extractor:
    def __init__(self, logger):
        self.logger = logger

    def log(self, text):
        if self.logger:
            self.logger.write(text)

    # ---------------- ZIP ----------------

    def extract_zip(self, file, out_dir):
        try:
            with zipfile.ZipFile(file, "r") as z:
                z.extractall(out_dir)
            return True, "OK"
        except Exception as e:
            return False, str(e)

    # ---------------- 7Z ----------------

    def extract_7z(self, seven, part1, out_dir):
        """
        Extract only first file. 7z auto-detects .002 / .003 etc.
        """
        try:
            cmd = [
                seven,
                "x",
                part1,
                f"-o{out_dir}",
                "-y"
            ]
            subprocess.run(cmd, check=True)
            return True, "OK"

        except Exception as e:
            return False, f"7z error: {str(e)}"


# ============================================================
#                    DLC INSTALL ENGINE
# ============================================================

class SingleDLCInstaller:
    """Install ZIP-based DLC (simple one-file DLC)."""

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

    # ---------------- MAIN ----------------

    def run(self):
        try:
            url = self.info.get("url")
            if not url:
                return False, "URL missing"

            temp = os.path.join(tempfile.gettempdir(), f"{self.dlc}.zip")

            self.log("Downloading…")
            ok, reason = self.dl.download(url, temp)
            if not ok:
                return False, reason

            self.log("Extracting ZIP…")
            ok, reason = self.ex.extract_zip(temp, self.game)
            if not ok:
                return False, reason

            try:
                os.remove(temp)
            except:
                pass

            self.log("Done.")
            return True, "OK"

        except Exception as e:
            return False, str(e)


# ============================================================
#               MULTIPART DLC INSTALLER (7Z SPLIT)
# ============================================================

class MultiPartInstaller:
    """Install multipart DLC (EP03 / EP06)."""

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

    # ---------------- MAIN ----------------

    def run(self):
        try:
            if not self.seven:
                return False, "7z.exe not found"

            parts = self.info.get("parts", [])
            if not parts:
                return False, "No parts defined"

            downloaded = []

            # ---------------- DOWNLOAD ALL PARTS ----------------
            for i, url in enumerate(parts):
                name = f"{self.dlc}.7z.{str(i+1).zfill(3)}"
                out = os.path.join(tempfile.gettempdir(), name)

                self.log(f"Downloading part {i+1}/{len(parts)}…")
                ok, reason = self.dl.download(url, out)
                if not ok:
                    return False, reason

                downloaded.append(out)

            # ---------------- EXTRACT VIA 7-ZIP ----------------
            part1 = downloaded[0]
            self.log("Extracting multipart 7z…")

            ok, reason = self.ex.extract_7z(self.seven, part1, self.game)
            if not ok:
                return False, reason

            # ---------------- CLEANUP ----------------
            for f in downloaded:
                try:
                    os.remove(f)
                except:
                    pass

            self.log("Done.")
            return True, "OK"

        except Exception as e:
            return False, str(e)


# ============================================================
#                 THREAD – ZIP INSTALLER
# ============================================================

class ZipInstallThread(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(str, bool, str)

    def __init__(self, dlc_id, info, game_path, downloader, extractor):
        super().__init__()
        self.dlc = dlc_id
        self.info = info
        self.game = game_path
        self.downloader = downloader
        self.extractor = extractor

    def run(self):
        inst = SingleDLCInstaller(
            self.dlc, self.info, self.game,
            self.downloader, self.extractor, None
        )
        success, reason = inst.run()
        self.done.emit(self.dlc, success, reason)


# ============================================================
#               THREAD – MULTIPART INSTALLER
# ============================================================

class MultiPartInstallThread(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(str, bool, str)

    def __init__(self, dlc_id, info, game_path, downloader, extractor):
        super().__init__()
        self.dlc = dlc_id
        self.info = info
        self.game = game_path
        self.downloader = downloader
        self.extractor = extractor
        self.seven = SevenZipFinder(None).find()

    def run(self):
        inst = MultiPartInstaller(
            self.dlc, self.info, self.game,
            self.downloader, self.extractor,
            self.seven, None
        )
        success, reason = inst.run()
        self.done.emit(self.dlc, success, reason)


# ============================================================
#                           REPAIR ENGINE
# ============================================================

class RepairEngine:
    """Deep repair system for Sims 4 folder."""

    def __init__(self, game_path, logger):
        self.game = Path(game_path)
        self.logger = logger

    def log(self, msg):
        if self.logger:
            self.logger.write(msg)

    # ---------------- MAIN ENTRY ----------------

    def run(self):
        try:
            if not self.game.exists():
                self.log("Invalid game path.")
                return False

            self.log("Starting deep repair…")

            self.check_structure()
            self.check_executables()
            self.clean_empty_dlc()
            self.clean_broken_ep()
            self.clean_temp_archives()

            self.log("Repair complete.")
            return True

        except Exception as e:
            self.log(f"Repair failed: {e}")
            return False

    # ============================================================
    #                   CHECK GAME STRUCTURE
    # ============================================================

    def check_structure(self):
        self.log("Checking core structure…")

        required = ["Game", "Data", "Delta"]
        for f in required:
            if not (self.game / f).exists():
                self.log(f"Missing folder: {f}")

    # ============================================================
    #                   CHECK EXECUTABLES
    # ============================================================

    def check_executables(self):
        self.log("Checking TS4 executables…")

        exe = self.game / "Game" / "Bin" / "TS4_x64.exe"
        exe_old = self.game / "Game" / "Bin" / "TS4.exe"

        if not exe.exists():
            self.log("TS4_x64.exe missing — game may not run.")
        else:
            size = exe.stat().st_size
            if size < 10_000_000:
                self.log("Warning: TS4_x64.exe looks corrupted (too small).")

        if not exe.exists() and exe_old.exists():
            self.log("Found only TS4.exe — 32-bit version. Install incomplete.")

    # ============================================================
    #                   REMOVE EMPTY DLC FOLDERS
    # ============================================================

    def clean_empty_dlc(self):
        self.log("Scanning for empty or broken DLC folders…")

        for item in self.game.iterdir():
            name = item.name.upper()

            if not name.startswith(("EP", "GP", "SP", "FP")):
                continue

            # empty folder
            if item.is_dir() and not any(item.iterdir()):
                self.log(f"Removing empty DLC folder: {name}")
                shutil.rmtree(item, ignore_errors=True)

    # ============================================================
    #              CLEAN BROKEN EP (EP16 / multipart errors)
    # ============================================================

    def clean_broken_ep(self):
        self.log("Checking for broken EP content…")

        # EP16 lovestruck
        ep16 = self.game / "EP16"
        if ep16.exists():
            files = [f.name.lower() for f in ep16.iterdir()]

            # broken variant: contains installer.exe or weird files
            if any("installer" in f for f in files):
                self.log("Broken EP16 detected — cleaning invalid files…")

                for f in ep16.iterdir():
                    try:
                        if "installer" in f.name.lower():
                            f.unlink()
                    except:
                        pass

        # EP03 / EP06
        for ep in ["EP03", "EP06"]:
            folder = self.game / ep
            if folder.exists():
                files = [f.name for f in folder.iterdir()]
                # If only 1 file exists — usually wrong content
                if len(files) <= 1:
                    self.log(f"{ep} incomplete — cleaning broken content…")
                    shutil.rmtree(folder, ignore_errors=True)

    # ============================================================
    #           CLEAN LEFTOVER TEMP FILES (7z.001, .002, .zip)
    # ============================================================

    def clean_temp_archives(self):
        self.log("Cleaning leftover temp archives…")

        temp = Path(tempfile.gettempdir())
        removed = 0

        for f in temp.iterdir():
            name = f.name

            if name.endswith(".7z.001") or name.endswith(".7z.002") or name.endswith(".zip"):
                try:
                    f.unlink()
                    removed += 1
                except:
                    pass

        if removed > 0:
            self.log(f"Removed {removed} leftover archived files.")


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
            self.logger.write("Checking for updates…")

            r = requests.get(self.RAW_URL, timeout=5)
            if r.status_code != 200:
                return

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
#                APPLICATION CONTROLLER (CORE)
# ============================================================

class AppController:
    def __init__(self, logger):
        self.logger = logger
        self.downloader = DownloadEngine(logger)
        self.extractor = Extractor(logger)

    # ============================================================
    #                 INSTALL ZIP DLC
    # ============================================================

    def install_zip(self, dlc_id, dlc_info, game_path, finished_callback):
        worker = ZipInstallThread(
            dlc_id, dlc_info, game_path,
            self.downloader,
            self.extractor
        )
        worker.log.connect(self.logger.write)
        worker.done.connect(finished_callback)
        worker.start()
        return worker

    # ============================================================
    #               INSTALL MULTIPART DLC (7Z SPLIT)
    # ============================================================

    def install_multipart(self, dlc_id, dlc_info, game_path, finished_callback):
        worker = MultiPartInstallThread(
            dlc_id, dlc_info, game_path,
            self.downloader,
            self.extractor
        )
        worker.log.connect(self.logger.write)
        worker.done.connect(finished_callback)
        worker.start()
        return worker

    # ============================================================
    #                    RUN FULL REPAIR
    # ============================================================

    def run_repair(self, game_path, finished_callback):
        repair = RepairThread(game_path, self.logger)
        repair.done.connect(finished_callback)
        repair.start()
        return repair


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
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse_folder)

        row.addWidget(self.path_input)
        row.addWidget(browse)
        layout.addLayout(row)

        # update + repair
        row2 = QHBoxLayout()
        self.update_btn = QPushButton("Update")
        self.repair_btn = QPushButton("Repair")

        row2.addWidget(self.update_btn)
        row2.addWidget(self.repair_btn)
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

    def log_message(self, message):
        """Добавляет сообщение в лог с текущим реальным временем"""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        self.log_text.append(f"{timestamp} {message}")

    def auto_detect(self):
        """Автодетект игры"""
        self.log_message("Detecting The Sims 4...")

        drives = ["C", "D", "E", "F"]
        paths = [
            r"\Program Files (x86)\Steam\steamapps\common\The Sims 4",
            r"\Program Files\EA Games\The Sims 4",
            r"\SteamLibrary\steamapps\common\The Sims 4",
            r"\Origin Games\The Sims 4",
            r"\The Sims 4",
        ]

        for d in drives:
            for p in paths:
                full = f"{d}:{p}"
                if os.path.exists(full):
                    self.path_input.setText(full)
                    self.log_message(f"Found game: {full}")
                    return

        self.log_message("Game not found automatically.")

    def load_dlc_database(self):
        """Загрузка базы данных DLC"""
        db = {
            # Expansion Packs
            "EP01": {"name": "Get to Work", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP01/Sims4_DLC_EP01_Get_to_Work.zip"},
            "EP02": {"name": "Get Together", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP02/Sims4_DLC_EP02_Get_Together.zip"},
            "EP03": {"name": "City Living", "parts": [
                "https://github.com/l1ntol/lunia-dlc/releases/download/EP03/Sims4_DLC_EP03_City_Living.7z.001",
                "https://github.com/l1ntol/lunia-dlc/releases/download/EP03/Sims4_DLC_EP03_City_Living.7z.002"
            ]},
            "EP04": {"name": "Cats and Dogs", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP04/Sims4_DLC_EP04_Cats_and_Dogs.zip"},
            "EP05": {"name": "Seasons", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP05/Sims4_DLC_EP05_Seasons.zip"},
            "EP06": {"name": "Get Famous", "parts": [
                "https://github.com/l1ntol/lunia-dlc/releases/download/EP06/Sims4_DLC_EP06_Get_Famous.7z.001",
                "https://github.com/l1ntol/lunia-dlc/releases/download/EP06/Sims4_DLC_EP06_Get_Famous.7z.002"
            ]},
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
            "EP17": {"name": "Life and Death", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP17/Sims4_DLC_EP17_Life_and_Death.zip"},
            "EP18": {"name": "Businesses and Hobbies", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP18/Sims4_DLC_EP18_Businesses_and_Hobbies.zip"},
            "EP19": {"name": "Enchanted by Nature", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP19/Sims4_DLC_EP19_Enchanted_by_Nature_Expansion_Pack.zip"},
            "EP20": {"name": "Adventure Awaits", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP20/Sims4_DLC_EP20_Adventure_Awaits_Expansion_Pack.zip"},

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

            # Kits (SP19-SP74)
            "SP19": {"name": "Fashion Street Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP19/Sims4_DLC_SP19_Fashion_Street_Kit.zip"},
            "SP20": {"name": "Throwback Fit Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP20/Sims4_DLC_SP20_Throwback_Fit_Kit.zip"},
            "SP21": {"name": "Country Kitchen Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP21/Sims4_DLC_SP21_Country_Kitchen_Kit.zip"},
            "SP22": {"name": "Bust the Dust Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP22/Sims4_DLC_SP22_Bust_the_Dust_Kit.zip"},
            "SP23": {"name": "Courtyard Oasis Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP23/Sims4_DLC_SP23_Courtyard_Oasis_Kit.zip"},
            "SP24": {"name": "Fashion Street Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP24/Sims4_DLC_SP24_Fashion_Street_Kit.zip"},
            "SP25": {"name": "Industrial Loft Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP25/Sims4_DLC_SP25_Industrial_Loft_Kit.zip"},
            "SP26": {"name": "Incheon Arrivals Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP26/Sims4_DLC_SP26_Incheon_Arrivals_Kit.zip"},
            "SP28": {"name": "Modern Menswear Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP28/Sims4_DLC_SP28_Modern_Menswear_Kit.zip"},
            "SP29": {"name": "Blooming Rooms Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP29/Sims4_DLC_SP29_Blooming_Rooms_Kit.zip"},
            "SP30": {"name": "Carnaval Streetwear Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP30/Sims4_DLC_SP30_Carnaval_Streetwear_Kit.zip"},
            "SP31": {"name": "Decor to the Max Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP31/Sims4_DLC_SP31_Decor_to_the_Max_Kit.zip"},
            "SP32": {"name": "Moonlight Chic Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP32/Sims4_DLC_SP32_Moonlight_Chic_Kit.zip"},
            "SP33": {"name": "Little Campers Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP33/Sims4_DLC_SP33_Little_Campers_Kit.zip"},
            "SP34": {"name": "First Fits Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP34/Sims4_DLC_SP34_First_Fits_Kit.zip"},
            "SP35": {"name": "Desert Luxe Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP35/Sims4_DLC_SP35_Desert_Luxe_Kit.zip"},
            "SP36": {"name": "Pastel Pop Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP36/Sims4_DLC_SP36_Pastel_Pop_Kit.zip"},
            "SP37": {"name": "Everyday Clutter Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP37/Sims4_DLC_SP37_Everyday_Clutter_Kit.zip"},
            "SP38": {"name": "Simtimates Collection Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP38/Sims4_DLC_SP38_Simtimates_Collection_Kit.zip"},
            "SP39": {"name": "Bathroom Clutter Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP39/Sims4_DLC_SP39_Bathroom_Clutter_Kit.zip"},
            "SP40": {"name": "Greenhouse Haven Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP40/Sims4_DLC_SP40_Greenhouse_Haven_Kit.zip"},
            "SP41": {"name": "Basement Treasures Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP41/Sims4_DLC_SP41_Basement_Treasures_Kit.zip"},
            "SP42": {"name": "Grunge Revival Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP42/Sims4_DLC_SP42_Grunge_Revival_Kit.zip"},
            "SP43": {"name": "Book Nook Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP43/Sims4_DLC_SP43_Book_Nook_Kit.zip"},
            "SP44": {"name": "Poolside Splash Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP44/Sims4_DLC_SP44_Poolside_Splash_Kit.zip"},
            "SP45": {"name": "Modern Luxe Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP45/Sims4_DLC_SP45_Modern_Luxe_Kit.zip"},
            "SP46": {"name": "Home Chef Hustle Stuff Pack", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP46/Sims4_DLC_SP46_Home_Chef_Hustle_Stuff_Pack.zip"},
            "SP47": {"name": "Castle Estate Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP47/Sims4_DLC_SP47_Castle_Estate_Kit.zip"},
            "SP48": {"name": "Goth Galore Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP48/Sims4_DLC_SP48_Goth_Galore_Kit.zip"},
            "SP49": {"name": "Crystal Creations Stuff Pack", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP49/Sims4_DLC_SP49_Crystal_Creations_Stuff_Pack.zip"},
            "SP50": {"name": "Urban Homage Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP50/Sims4_DLC_SP50_Urban_Homage_Kit.zip"},
            "SP51": {"name": "Party Essentials Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP51/Sims4_DLC_SP51_Party_Essentials_Kit.zip"},
            "SP52": {"name": "Riviera Retreat Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP52/Sims4_DLC_SP52_Riviera_Retreat_Kit.zip"},
            "SP53": {"name": "Cozy Bistro Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP53/Sims4_DLC_SP53_Cozy_Bistro_Kit.zip"},
            "SP54": {"name": "Artist Studio Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP54/Sims4_DLC_SP54_Artist_Studio_Kit.zip"},
            "SP55": {"name": "Storybook Nursery Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP55/Sims4_DLC_SP55_Storybook_Nursery_Kit.zip"},
            "SP56": {"name": "Sweet Slumber Party Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP56/Sims4_DLC_SP56_Sweet_Slumber_Party_Kit.zip"},
            "SP57": {"name": "Cozy Kitsch Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP57/Sims4_DLC_SP57_Cozy_Kitsch_Kit.zip"},
            "SP58": {"name": "Comfy Gamer Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP58/Sims4_DLC_SP58_Comfy_Gamer_Kit.zip"},
            "SP59": {"name": "Secret Sanctuary Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP59/Sims4_DLC_SP59_Secret_Sanctuary_Kit.zip"},
            "SP60": {"name": "Casanova Cave Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP60/Sims4_DLC_SP60_Casanova_Cave_Kit.zip"},
            "SP61": {"name": "Refined Living Room Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP61/Sims4_DLC_SP61_Refined_Living_Room_Kit.zip"},
            "SP62": {"name": "Business Chic Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP62/Sims4_DLC_SP62_Business_Chic_Kit.zip"},
            "SP63": {"name": "Sleek Bathroom Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP63/Sims4_DLC_SP63_Sleek_Bathroom_Kit.zip"},
            "SP64": {"name": "Sweet Allure Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP64/Sims4_DLC_SP64_Sweet_Allure_Kit.zip"},
            "SP65": {"name": "Restoration Workshop Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP65/Sims4_DLC_SP65_Restoration_Workshop_Kit.zip"},
            "SP66": {"name": "Golden Years Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP66/Sims4_DLC_SP66_Golden_Years_Kit.zip"},
            "SP67": {"name": "Kitchen Clutter Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP67/Sims4_DLC_SP67_Kitchen_Clutter_Kit.zip"},
            "SP69": {"name": "Autumn Apparel Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP69/Sims4_DLC_SP69_Autumn_Apparel_Kit.zip"},
            "SP71": {"name": "Grange Mudroom Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP71/Sims4_DLC_SP71_Grange_Mudroom_Kit.zip"},
            "SP72": {"name": "Essential Glam Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP72/Sims4_DLC_SP72_Essential_Glam_Kit.zip"},
            "SP73": {"name": "Modern Retreat Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP73/Sims4_DLC_SP73_Modern_Retreat_Kit.zip"},
            "SP74": {"name": "Garden to Table Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP74/Sims4_DLC_SP74_Garden_to_Table_Kit.zip"},

            # Free Packs
            "FP01": {"name": "Holiday Celebration Pack", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/FP01/Sims4_DLC_FP01_Holiday_Celebration_Pack.zip"},
        }
        return db

    def detect_installed(self, game_path):
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
        path = self.path_input.text().strip()
        if not path or not os.path.exists(path):
            self.log_message("Invalid game folder.")
            return
        
        installed = self.detect_installed(path)
        
        dlg = DLCSelector(self)
        dlg.populate(self.dlc_db, installed)
        
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
            
        selected = dlg.get()
        if not selected:
            self.log_message("No DLC selected.")
            return
            
        self.start_install_process(selected, path)

    def start_install_process(self, selected, game_path):
        """Запуск процесса установки"""
        self.controller = AppController(self.logger)

        self.progress_total = len(selected)
        self.progress_done = 0

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(self.progress_total)
        self.progress_bar.setValue(0)

        self.update_btn.setEnabled(False)
        self.repair_btn.setEnabled(False)

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

    @pyqtSlot(str, bool, str)
    def install_done(self, dlc_id, success, reason):
        """Обработчик завершения установки DLC"""
        self.progress_done += 1
        self.progress_bar.setValue(self.progress_done)

        if success:
            self.log_message(f"{dlc_id} installed.")
        else:
            self.log_message(f"{dlc_id} failed — {reason}")

        if self.progress_done == self.progress_total:
            self.finish_install()

    def finish_install(self):
        """Завершение процесса установки"""
        self.log_message("Installation complete.")
        self.progress_bar.setVisible(False)

        self.update_btn.setEnabled(True)
        self.repair_btn.setEnabled(True)

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
            self.log_message("Repair finished.")
        else:
            self.log_message("Repair failed.")

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
            }
            QCheckBox {
                color: white;
            }
            QPushButton {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #444;
            }
        """)

        layout = QVBoxLayout(self)

        self.info = QLabel("Select DLC you want to install.\nAlready installed DLC are hidden.")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: white; padding: 10px;")
        layout.addWidget(self.info)

        self.check_all = QCheckBox("Select all")
        self.check_all.setStyleSheet("color: white;")
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
        val = (state == Qt.CheckState.Checked)
        for cb in self.cbs.values():
            cb.setChecked(val)

    def populate(self, db, installed):
        # clear
        for i in reversed(range(self.layout_c.count())):
            w = self.layout_c.itemAt(i).widget()
            if w:
                w.deleteLater()

        # Проверяем, есть ли доступные DLC для установки
        available_dlc = []
        for dlc_id, info in db.items():
            if dlc_id.upper() not in installed:
                available_dlc.append((dlc_id, info))

        # Если все DLC уже установлены
        if not available_dlc:
            no_dlc_label = QLabel("All DLC are already installed.")
            no_dlc_label.setStyleSheet("color: white; padding: 20px; text-align: center;")
            no_dlc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_c.addWidget(no_dlc_label)
            self.check_all.setVisible(False)  # Скрываем чекбокс "Select all"
            return

        # Если есть доступные DLC, показываем их как обычно
        self.check_all.setVisible(True)  # Показываем чекбокс "Select all"
        
        categories = {
            "Expansion Packs": [],
            "Game Packs": [],
            "Stuff Packs": [],
        }

        for dlc_id, info in available_dlc:
            if dlc_id.startswith("EP"):
                categories["Expansion Packs"].append((dlc_id, info))
            elif dlc_id.startswith("GP"):
                categories["Game Packs"].append((dlc_id, info))
            else:
                categories["Stuff Packs"].append((dlc_id, info))

        # add items
        for cat, items in categories.items():
            if not items:
                continue

            header = QLabel(cat)
            header.setStyleSheet("font-weight: bold; margin-top: 10px; color: white;")
            self.layout_c.addWidget(header)

            for dlc_id, info in sorted(items):
                cb = QCheckBox(f"[{dlc_id}] {info['name']}")
                cb.setStyleSheet("color: white;")
                self.layout_c.addWidget(cb)
                self.cbs[dlc_id] = cb

    def get(self):
        # Если нет доступных чекбоксов (все DLC установлены), возвращаем пустой список
        if not self.cbs:
            return []
        return [dlc for dlc, cb in self.cbs.items() if cb.isChecked()]

# ============================================================
#                     UPDATE PROCESS (UI)
# ============================================================

def attach_update_process(cls):
    def start_update(self):
        path = self.path_input.text().strip()

        if not path or not os.path.exists(path):
            self.logger.write("Invalid game folder.")
            return

        installed = self.detect_installed(path)

        dlg = DLCSelector(self)
        dlg.populate(self.dlc_db, installed)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dlg.get()
        if not selected:
            self.logger.write("No DLC selected.")
            return

        self.start_install_process(selected, path)

    def start_install_process(self, selected, game_path):
        self.controller = AppController(self.logger)

        self.progress_total = len(selected)
        self.progress_done = 0

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(self.progress_total)
        self.progress_bar.setValue(0)

        self.update_btn.setEnabled(False)
        self.repair_btn.setEnabled(False)

        self.logger.write(f"Installing {len(selected)} DLC…")

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

    @pyqtSlot(str, bool, str)
    def install_done(self, dlc_id, success, reason):
        self.progress_done += 1
        self.progress_bar.setValue(self.progress_done)

        if success:
            self.logger.write(f"{dlc_id} installed.")
        else:
            self.logger.write(f"{dlc_id} failed — {reason}")

        if self.progress_done == self.progress_total:
            self.finish_install()

    def finish_install(self):
        self.logger.write("Installation complete.")
        self.progress_bar.setVisible(False)

        self.update_btn.setEnabled(True)
        self.repair_btn.setEnabled(True)

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Done")
        dlg.setText("All selected DLC were installed.")
        dlg.exec()

    cls.start_update = start_update
    cls.start_install_process = start_install_process
    cls.install_done = install_done
    cls.finish_install = finish_install

attach_update_process(LinuaUpdater)


# ============================================================
#                     REPAIR PROCESS (UI)
# ============================================================

def attach_repair_process(cls):
    def start_repair(self):
        path = self.path_input.text().strip()
        if not path or not os.path.isdir(path):
            self.logger.write("Invalid game folder.")
            return

        self.logger.write("Starting repair…")

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)

        self.controller = AppController(self.logger)
        self.repair_thread = self.controller.run_repair(
            path,
            self.repair_done
        )

    @pyqtSlot(bool)
    def repair_done(self, ok):
        self.progress_bar.setVisible(False)

        if ok:
            self.logger.write("Repair finished.")
        else:
            self.logger.write("Repair failed.")

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Repair complete")
        dlg.setText("Repair process finished.")
        dlg.exec()

    cls.start_repair = start_repair
    cls.repair_done = repair_done

attach_repair_process(LinuaUpdater)


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