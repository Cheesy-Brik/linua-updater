# ================================================================
#                       LINUA UPDATER v4.0
#         Final Release Build • By l1ntol / Linua Project
# ================================================================

import os
import sys
import time
import json
import shutil
import zipfile
import tempfile
import subprocess
import requests
import socket
import webbrowser
import traceback
import platform
from pathlib import Path
from datetime import datetime

# Для обработки Ctrl+C
if sys.platform != "win32":
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

# Отключаем предупреждения SSL (только для локального использования)
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QFileDialog,
    QLabel, QPushButton, QTextEdit, QVBoxLayout,
    QHBoxLayout, QWidget, QLineEdit, QCheckBox,
    QScrollArea, QMessageBox, QProgressBar
)
from PyQt6.QtGui import QFont

APP_VERSION = "4.0"

# ================================================================
#                     LOG WRITER (из старого кода)
# ================================================================
class LogWriter:
    def __init__(self, widget):
        self.widget = widget

    def write(self, text):
        if text.strip():  # Игнорируем пустые строки
            self.widget.append(text)
            self.widget.ensureCursorVisible()


# ================================================================
#                   7ZIP DETECTOR (HYBRID) - из старого кода
# ================================================================
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
        exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        local = os.path.join(exe_dir, "7z.exe")
        if os.path.exists(local):
            if self.logger:
                self.logger.log("Using local 7z.exe")
            return local

        # 2) check system locations
        for p in self.POSSIBLE_LOCATIONS:
            if os.path.exists(p):
                if self.logger:
                    self.logger.log(f"Found 7zip at: {p}")
                return p

        # 3) check via PATH
        try:
            if sys.platform == "win32":
                result = subprocess.run(["where", "7z"], capture_output=True, text=True, shell=True)
            else:
                result = subprocess.run(["which", "7z"], capture_output=True, text=True)
                
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if self.logger:
                    self.logger.log(f"Found 7zip via PATH: {path}")
                return path
        except:
            pass

        # 4) 7zip not found
        if self.logger:
            self.logger.log("7z.exe not found. Multipart DLC will not extract.")
        return None


# ================================================================
#                  ADVANCED DOWNLOAD ENGINE - из старого кода
# ================================================================
class DownloadEngine:
    """
    Stable downloader - direct downloads only
    """

    def __init__(self, logger):
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def log(self, text):
        if self.logger:
            self.logger.log(text)

    def download(self, url, out_path, dlc_name=None):
        """Основной метод скачивания"""
        try:
            # Показываем название DLC вместо ссылки
            display_text = dlc_name if dlc_name else url
            self.log(f"Downloading: {display_text}")

            # Для ВСЕХ ссылок используем прямой download
            return self.download_direct(url, out_path)

        except Exception as e:
            return False, f"Download error: {str(e)}"

    def download_direct(self, url, out_path):
        """Прямое скачивание с улучшенной проверкой безопасности"""
        try:
            # Создаем родительскую директорию если нужно
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            
            with self.session.get(url, stream=True, timeout=30, verify=False) as r:
                r.raise_for_status()
                
                if r.status_code != 200:
                    return False, f"HTTP {r.status_code}"
                
                # Проверка content-type для безопасности
                content_type = r.headers.get('content-type', '')
                valid_types = ['application/zip', 'application/octet-stream', 
                              'application/x-zip-compressed', 'application/x-7z-compressed']
                
                if not any(ct in content_type for ct in valid_types):
                    self.log(f"Warning: Unexpected content type: {content_type}")

                total = int(r.headers.get("content-length", 0))
                # УВЕЛИЧИЛИ ЛИМИТ ДО 10GB ДЛЯ КРУПНЫХ DLC
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

        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.ConnectionError:
            return False, "Connection error"
        except Exception as e:
            return False, f"Direct download error: {str(e)}"


# ================================================================
#                     ZIP / 7Z SAFE EXTRACTOR - из старого кода
# ================================================================
class Extractor:
    def __init__(self, logger):
        self.logger = logger

    def log(self, text):
        if self.logger:
            self.logger.log(text)

    def extract_zip(self, file, out_dir):
        """Распаковать ZIP архив"""
        try:
            # Создаем директорию для распаковки
            os.makedirs(out_dir, exist_ok=True)
            
            with zipfile.ZipFile(file, "r") as z:
                # Проверяем архив перед распаковкой
                bad_file = z.testzip()
                if bad_file:
                    return False, f"Corrupted ZIP file: {bad_file}"
                    
                total = len(z.infolist())
                extracted = 0
                for member in z.infolist():
                    z.extract(member, out_dir)
                    extracted += 1
                    
            self.log(f"Extracted {extracted} files from ZIP")
            return True, "OK"
        except zipfile.BadZipFile:
            return False, "Invalid or corrupted ZIP file"
        except Exception as e:
            return False, f"ZIP extraction error: {str(e)}"

    def extract_7z(self, seven, archive_path, out_dir):
        """Распаковать 7z архив"""
        try:
            # Проверяем существование 7z
            if not os.path.exists(seven):
                return False, "7z.exe not found"
                
            # Проверяем существование архива
            if not os.path.exists(archive_path):
                return False, "Archive file not found"
                
            # Создаем директорию для распаковки
            os.makedirs(out_dir, exist_ok=True)
            
            cmd = [
                seven,
                "x",
                archive_path,
                f"-o{out_dir}",
                "-y"
            ]
            
            self.log(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            self.log(f"7z output: {result.stdout[:200]}")
            
            return True, "OK"

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            return False, f"7z error: {error_msg}"
        except subprocess.TimeoutExpired:
            return False, "7z extraction timeout"
        except FileNotFoundError:
            return False, "7z.exe not found in PATH"
        except Exception as e:
            return False, f"7z error: {str(e)}"


# ================================================================
#                    DLC INSTALL ENGINE - из старого кода
# ================================================================
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
            self.logger.log(f"[{self.dlc}] {t}")

    def run(self):
        temp = None
        try:
            url = self.info.get("url")
            if not url:
                return False, "URL missing"

            # Создаем временный файл с уникальным именем
            temp_dir = tempfile.gettempdir()
            temp = os.path.join(temp_dir, f"{self.dlc}_{int(time.time())}.zip")

            self.log("Downloading...")
            # Передаем название DLC для красивого логирования
            dlc_name = f"{self.dlc} - {self.info.get('name', 'Unknown DLC')}"
            ok, reason = self.dl.download(url, temp, dlc_name)
            if not ok:
                return False, reason

            # Проверяем размер файла
            if os.path.getsize(temp) == 0:
                return False, "Downloaded file is empty"

            self.log("Extracting...")
            ok, reason = self.ex.extract_zip(temp, self.game)
            if not ok:
                return False, reason

            self.log("Installation completed successfully")
            return True, "OK"

        except Exception as e:
            return False, f"Installation error: {str(e)}"
        finally:
            # Cleanup временного файла
            if temp and os.path.exists(temp):
                try:
                    os.remove(temp)
                except:
                    pass


# ================================================================
#               MULTIPART DLC INSTALLER - из старого кода
# ================================================================
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
            self.logger.log(f"[{self.dlc}] {t}")

    def run(self):
        downloaded_files = []
        try:
            if not self.seven or not os.path.exists(self.seven):
                return False, "7z.exe not found"

            parts = self.info.get("parts", [])
            if not parts:
                return False, "No parts defined"

            # Скачиваем все части
            for i, url in enumerate(parts):
                name = f"{self.dlc}.7z.{str(i+1).zfill(3)}"
                out = os.path.join(tempfile.gettempdir(), name)

                self.log(f"Downloading part {i+1}/{len(parts)}...")
                # Передаем название DLC для красивого логирования
                dlc_name = f"{self.dlc} - {self.info.get('name', 'Unknown DLC')} [Part {i+1}]"
                ok, reason = self.dl.download(url, out, dlc_name)
                if not ok:
                    # Очищаем уже скачанные части
                    for f in downloaded_files:
                        try:
                            os.remove(f)
                        except:
                            pass
                    return False, reason

                downloaded_files.append(out)

            # Проверяем что первая часть существует
            if not downloaded_files or not os.path.exists(downloaded_files[0]):
                return False, "First part not found"

            # Извлекаем через 7-Zip
            part1 = downloaded_files[0]
            self.log("Extracting multipart archive...")

            ok, reason = self.ex.extract_7z(self.seven, part1, self.game)
            if not ok:
                return False, reason

            self.log("Installation completed successfully")
            return True, "OK"

        except Exception as e:
            return False, f"Multipart installation error: {str(e)}"
        finally:
            # Очищаем временные файлы
            for f in downloaded_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except:
                    pass


# ================================================================
#                 INSTALLATION THREADS - из старого кода
# ================================================================
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
        self._stop_requested = False
        
    def stop(self):
        """Запросить остановку потока"""
        self._stop_requested = True
        
    def run(self):
        inst = SingleDLCInstaller(
            self.dlc, self.info, self.game,
            self.downloader, self.extractor, self.logger
        )
        
        # Проверяем флаг остановки во время установки
        if not self._stop_requested:
            success, reason = inst.run()
            self.done.emit(self.dlc, success, reason)
        else:
            self.log.emit(f"[{self.dlc}] Installation cancelled")
            self.done.emit(self.dlc, False, "Cancelled by user")


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
        self._stop_requested = False
        
    def stop(self):
        """Запросить остановку потока"""
        self._stop_requested = True
        
    def run(self):
        # Проверяем флаг остановки
        if self._stop_requested:
            self.log.emit(f"[{self.dlc}] Installation cancelled")
            self.done.emit(self.dlc, False, "Cancelled by user")
            return
            
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
        
        # Проверяем флаг остановки снова
        if not self._stop_requested:
            success, reason = inst.run()
            self.done.emit(self.dlc, success, reason)
        else:
            self.log.emit(f"[{self.dlc}] Installation cancelled")
            self.done.emit(self.dlc, False, "Cancelled by user")


# ================================================================
#                           REPAIR ENGINE - из старого кода
# ================================================================
class RepairEngine:
    """Система восстановления папки Sims 4"""

    def __init__(self, game_path, logger):
        self.game = Path(game_path)
        self.logger = logger

    def log(self, msg):
        if self.logger:
            self.logger.log(msg)

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
        required = ["Game", "Data"]
        for f in required:
            if not (self.game / f).exists():
                self.log(f"Missing folder: {f}")

    def check_executables(self):
        self.log("Checking executables...")
        exe = self.game / "Game" / "Bin" / "TS4_x64.exe"
        if not exe.exists():
            self.log("TS4_x64.exe missing - game may not run")
        else:
            size_mb = exe.stat().st_size / (1024 * 1024)
            self.log(f"TS4_x64.exe size: {size_mb:.1f} MB")

    def clean_empty_dlc(self):
        self.log("Cleaning empty DLC folders...")
        cleaned = 0
        for item in self.game.iterdir():
            if item.is_dir():
                name = item.name.upper()
                if name.startswith(("EP", "GP", "SP", "FP")):
                    if not any(item.iterdir()):
                        self.log(f"Removing empty folder: {name}")
                        try:
                            shutil.rmtree(item, ignore_errors=True)
                            cleaned += 1
                        except:
                            pass
        self.log(f"Cleaned {cleaned} empty DLC folders")

    def clean_temp_files(self):
        self.log("Cleaning temp files...")
        temp = Path(tempfile.gettempdir())
        patterns = [".7z.001", ".7z.002", ".zip", ".tmp", ".part"]
        
        cleaned = 0
        for pattern in patterns:
            for f in temp.glob(f"*{pattern}"):
                try:
                    if f.is_file():
                        f.unlink()
                        cleaned += 1
                except:
                    pass
        self.log(f"Cleaned {cleaned} temp files")


# ================================================================
#                      REPAIR THREAD - из старого кода
# ================================================================
class RepairThread(QThread):
    done = pyqtSignal(bool)
    log = pyqtSignal(str)
    
    def __init__(self, game_path, logger):
        super().__init__()
        self.game_path = game_path
        self.logger = logger
        self._stop_requested = False
        
    def stop(self):
        """Запросить остановку потока"""
        self._stop_requested = True
        
    def run(self):
        if not self._stop_requested:
            engine = RepairEngine(self.game_path, self.logger)
            ok = engine.run()
            self.done.emit(ok)


# ================================================================
#                    AUTO UPDATE CHECKER - УДАЛЕН
# ================================================================
# Убрали класс AutoUpdateChecker чтобы избежать ошибок


# ================================================================
#                APPLICATION CONTROLLER - ИСПРАВЛЕННЫЙ
# ================================================================
class AppController:
    def __init__(self, logger, thread_manager):
        self.logger = logger
        self.downloader = DownloadEngine(logger)
        self.extractor = Extractor(logger)
        self.thread_manager = thread_manager
        
    def install_zip(self, dlc_id, dlc_info, game_path, finished_callback):
        worker = ZipInstallThread(
            dlc_id, dlc_info, game_path,
            self.downloader,
            self.extractor,
            self.logger
        )
        worker.log.connect(self.logger.log)
        worker.done.connect(finished_callback)
        self.thread_manager.add_thread(worker)
        worker.start()
        return worker

    def install_multipart(self, dlc_id, dlc_info, game_path, finished_callback):
        worker = MultiPartInstallThread(
            dlc_id, dlc_info, game_path,
            self.downloader,
            self.extractor,
            self.logger
        )
        worker.log.connect(self.logger.log)
        worker.done.connect(finished_callback)
        self.thread_manager.add_thread(worker)
        worker.start()
        return worker

    def run_repair(self, game_path, finished_callback):
        repair = RepairThread(game_path, self.logger)
        repair.done.connect(finished_callback)
        repair.log.connect(self.logger.log)
        self.thread_manager.add_thread(repair)
        repair.start()
        return repair


# ================================================================
#                       NETWORK CHECKER
# ================================================================
class NetworkChecker:
    @staticmethod
    def is_online():
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return True
        except:
            return False


# ================================================================
#                      DISK SPACE CHECKER - из старого кода
# ================================================================
class DiskChecker:
    @staticmethod
    def get_free_gb(path):
        try:
            usage = shutil.disk_usage(path)
            return usage.free / (1024**3)  # Convert to GB
        except:
            return 0

    @staticmethod
    def check_disk_space(path, required_gb=10):
        """Проверка свободного места на диске"""
        try:
            total, used, free = shutil.disk_usage(path)
            free_gb = free // (2**30)  # Конвертируем в GB
            return free_gb >= required_gb, free_gb
        except Exception as e:
            return True, 0  # Если проверка не удалась, продолжаем


# ================================================================
#                           LOGGER
# ================================================================
class Logger:
    def __init__(self, widget=None):
        self.widget = widget
        self.log_dir = Path.home() / "AppData" / "Local" / "LinuaUpdater" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"log_{time.strftime('%Y-%m-%d')}.txt"

    def log(self, text):
        t = time.strftime("[%H:%M:%S]")
        line = f"{t} {text}"

        if self.widget:
            # Используем HTML для цветного текста
            if "ERROR" in text.upper():
                line = f'<font color="red">{line}</font>'
            elif "WARNING" in text.upper():
                line = f'<font color="yellow">{line}</font>'
            elif "SUCCESS" in text.upper() or "OK" in text.upper():
                line = f'<font color="lightgreen">{line}</font>'
            elif "DEBUG" in text.upper():
                line = f'<font color="gray">{line}</font>'
            else:
                line = f'<font color="white">{line}</font>'
            
            self.widget.append(line)
            self.widget.ensureCursorVisible()

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{t} {text}\n")
        except Exception as e:
            print(f"Failed to write log: {e}")

    def write(self, text):
        """Совместимость с LogWriter из старого кода"""
        self.log(text)


# ================================================================
#                        CONFIG MANAGER
# ================================================================
class ConfigManager:
    def __init__(self):
        self.path = Path.home() / "AppData" / "Local" / "LinuaUpdater" / "config.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            self.data = {"game_path": ""}
            self.save()
        else:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except:
                self.data = {"game_path": ""}
                self.save()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")


# ================================================================
#               НОВЫЕ КЛАССЫ ДЛЯ УЛУЧШЕНИЙ v4.0
# ================================================================

class ThreadManager:
    def __init__(self):
        self.active_threads = []
        self.is_cancelling = False
        
    def add_thread(self, thread):
        """Добавить поток в управление"""
        self.active_threads.append(thread)
        # Автоматически удалить поток из списка при завершении
        thread.finished.connect(lambda t=thread: self.remove_thread(t))
        
    def remove_thread(self, thread):
        """Удалить завершённый поток из списка"""
        try:
            if thread in self.active_threads:
                self.active_threads.remove(thread)
        except ValueError:
            pass
            
    def cancel_all(self):
        """Безопасно отменить все потоки"""
        self.is_cancelling = True
        
        # Сначала мягко останавливаем
        for thread in self.active_threads[:]:
            if hasattr(thread, 'stop'):
                try:
                    thread.stop()
                except:
                    pass
            elif thread.isRunning():
                thread.quit()
                
        # Ждем 2 секунды для мягкого завершения
        QTimer.singleShot(2000, self.force_terminate)
        
    def force_terminate(self):
        """Принудительное завершение оставшихся потоков"""
        for thread in self.active_threads[:]:
            if thread.isRunning():
                thread.terminate()
                thread.wait(1000)
        self.active_threads.clear()
        self.cleanup_temporary_files()
        self.is_cancelling = False
        
    def cleanup_temporary_files(self):
        """Очистка временных файлов после отмены"""
        temp_dir = Path(tempfile.gettempdir())
        patterns = ["*.tmp", "*.zip", "*.7z.*", "_linua_*", "*.part"]
        
        for pattern in patterns:
            for file in temp_dir.glob(pattern):
                try:
                    if file.is_file():
                        file.unlink()
                    elif file.is_dir():
                        shutil.rmtree(file, ignore_errors=True)
                except:
                    pass
                    
    def wait_for_all(self, timeout=5000):
        """Дождаться завершения всех потоков"""
        start_time = time.time()
        while self.active_threads and (time.time() - start_time) < (timeout / 1000):
            QApplication.processEvents()
            time.sleep(0.1)


# 2. Умное скачивание с очередью
class DownloadThread(QThread):
    progress = pyqtSignal(int, int)  # current, total in MB
    finished = pyqtSignal(str, bool, str)  # dlc_id, success, message
    
    def __init__(self, dlc_id, url, path, logger):
        super().__init__()
        self.dlc_id = dlc_id
        self.url = url
        self.path = path
        self.logger = logger
        self._stop_flag = False
        
    def stop(self):
        self._stop_flag = True
        
    def run(self):
        try:
            # Создаем сессию для этого потока
            session = requests.Session()
            session.headers.update({'User-Agent': 'Linua-Updater/4.0'})
            
            with session.get(self.url, stream=True, timeout=30, verify=False) as r:
                r.raise_for_status()
                
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                # Создаем директорию если нужно
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                
                with open(self.path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._stop_flag:
                            self.finished.emit(self.dlc_id, False, "Cancelled")
                            try:
                                os.remove(self.path)
                            except:
                                pass
                            return
                            
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            mb_downloaded = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024) if total_size else 0
                            self.progress.emit(int(mb_downloaded), int(mb_total))
                
                # Проверка целостности
                if total_size > 0 and downloaded < total_size * 0.95:
                    try:
                        os.remove(self.path)
                    except:
                        pass
                    self.finished.emit(self.dlc_id, False, "File incomplete")
                else:
                    self.finished.emit(self.dlc_id, True, "Downloaded successfully")
                    
        except Exception as e:
            self.finished.emit(self.dlc_id, False, str(e))


class DownloadManager:
    def __init__(self, max_workers=2, logger=None):
        self.max_workers = max_workers
        self.logger = logger
        self.download_queue = []
        self.active_downloads = []
        self.paused = False
        
    def add_to_queue(self, dlc_id, url, path, callback):
        self.download_queue.append({
            'id': dlc_id,
            'url': url,
            'path': path,
            'callback': callback
        })
        self.process_queue()
        
    def process_queue(self):
        while (len(self.active_downloads) < self.max_workers and 
               self.download_queue and not self.paused):
            item = self.download_queue.pop(0)
            self.start_download(item)
            
    def start_download(self, item):
        thread = DownloadThread(
            item['id'], item['url'], item['path'], self.logger
        )
        thread.finished.connect(lambda success, msg, dlc=item['id']: 
                               self.download_finished(item, success, msg))
        thread.start()
        self.active_downloads.append(thread)
        
    def download_finished(self, item, success, message):
        # Удаляем завершенный поток
        for thread in self.active_downloads:
            if not thread.isRunning():
                self.active_downloads.remove(thread)
                break
                
        item['callback'](item['id'], success, message)
        self.process_queue()
        
    def pause_all(self):
        self.paused = True
        for thread in self.active_downloads:
            if hasattr(thread, 'stop'):
                thread.stop()
        
    def resume_all(self):
        self.paused = False
        self.process_queue()
        
    def cancel_all(self):
        self.pause_all()
        for thread in self.active_downloads:
            if thread.isRunning():
                thread.terminate()
        self.active_downloads.clear()
        self.download_queue.clear()


# 3. Rollback система
class RollbackManager:
    def __init__(self, game_path, logger):
        self.game_path = Path(game_path)
        self.logger = logger
        self.backup_dir = self.game_path / "_linua_backup"
        self.rollback_log = []
        
    def create_backup(self, dlc_id):
        """Создать бэкап перед установкой"""
        dlc_path = self.game_path / dlc_id
        if dlc_path.exists() and dlc_path.is_dir():
            backup_path = self.backup_dir / dlc_id
            self.backup_dir.mkdir(exist_ok=True)
            
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
                
            try:
                shutil.copytree(dlc_path, backup_path)
                self.rollback_log.append({
                    'action': 'backup',
                    'dlc': dlc_id,
                    'path': str(backup_path)
                })
                self.logger.log(f"[BACKUP] Created backup for {dlc_id}")
            except Exception as e:
                self.logger.log(f"[BACKUP] Failed to backup {dlc_id}: {e}")
            
    def rollback(self, dlc_id):
        """Откатить установку DLC"""
        dlc_path = self.game_path / dlc_id
        backup_path = self.backup_dir / dlc_id
        
        # Удаляем текущий DLC
        if dlc_path.exists():
            try:
                shutil.rmtree(dlc_path, ignore_errors=True)
            except Exception as e:
                self.logger.log(f"[ROLLBACK] Failed to remove {dlc_id}: {e}")
            
        # Восстанавливаем из бэкапа
        if backup_path.exists() and backup_path.is_dir():
            try:
                shutil.move(str(backup_path), str(dlc_path))
                self.logger.log(f"[ROLLBACK] {dlc_id} restored from backup")
            except Exception as e:
                self.logger.log(f"[ROLLBACK] Failed to restore {dlc_id}: {e}")
            
    def cleanup(self):
        """Очистить бэкапы после успешной установки"""
        if self.backup_dir.exists():
            try:
                shutil.rmtree(self.backup_dir, ignore_errors=True)
                self.logger.log("[BACKUP] Cleaned up backup files")
            except Exception as e:
                self.logger.log(f"[BACKUP] Failed to cleanup: {e}")


# 4. Улучшенная проверка DLC (ПРАВИЛЬНАЯ ДЛЯ SIMS 4)
class DLCValidator:
    @staticmethod
    def is_dlc_valid(dlc_path):
        """Проверка DLC The Sims 4 - правильная структура"""
        path = Path(dlc_path)
        
        # 1. Папка существует
        if not path.exists():
            return False, "Path doesn't exist"
            
        # 2. Не пустая
        if not any(path.iterdir()):
            return False, "Empty DLC folder"
            
        # 3. Sims 4 DLC имеет специфическую структуру:
        #    - Папки: _locdata_, _installer, Geometry, etc.
        #    - Файлы: *.package, *.bnk, *.trayitem и т.д.
        
        # Ищем характерные для Sims 4 DLC файлы и папки
        sims4_dlc_markers = {
            "folders": [
                "_locdata_", "_installer", "Geometry", 
                "Thumbnails", "UI", "Audio", "Movies"
            ],
            "files": [
                "*.package", "*.bnk", "*.trayitem",
                "*.sgi", "*.dll", "*.ts4script"
            ]
        }
        
        # Проверяем папки
        found_folders = []
        for folder in sims4_dlc_markers["folders"]:
            if (path / folder).exists():
                found_folders.append(folder)
                
        # Проверяем файлы
        found_files = []
        for pattern in sims4_dlc_markers["files"]:
            if list(path.rglob(pattern)):
                found_files.append(pattern.replace("*", ""))
                
        # Для DLC Sims 4 достаточно найти либо характерные папки, либо файлы
        if found_folders or found_files:
            # Это похоже на валидный DLC Sims 4
            markers = []
            if found_folders:
                markers.append(f"folders: {', '.join(found_folders[:3])}")
            if found_files:
                markers.append(f"files: {', '.join(found_files[:3])}")
                
            return True, f"Valid Sims 4 DLC ({'; '.join(markers)})"
            
        # Если нет характерных маркеров, проверим есть ли package файлы
        package_files = list(path.rglob("*.package"))
        if package_files:
            return True, f"Valid DLC ({len(package_files)} package files)"
            
        # Если ничего не найдено - возможно не DLC
        return False, "No Sims 4 DLC markers found"
        
    @staticmethod
    def get_dlc_size(dlc_path):
        """Получить размер DLC"""
        total = 0
        for file in Path(dlc_path).rglob('*'):
            if file.is_file():
                try:
                    total += file.stat().st_size
                except:
                    pass
        return total / (1024*1024*1024)  # в GB


# 5. Улучшенная проверка игры (ОБНОВЛЕННЫЙ)
class GameValidator:
    # ТОЛЬКО ОБЯЗАТЕЛЬНЫЕ ФАЙЛЫ
    ESSENTIAL_FILES = [
        "Game/Bin/TS4_x64.exe",  # Основной исполняемый файл
        "Data/Client/ClientDeltaBuild0.package",  # Обязательный файл данных
        "Data/Client/ClientFullBuild0.package"   # Обязательный файл данных
    ]
    
    # ОПЦИОНАЛЬНЫЕ ФАЙЛЫ (32-битные версии не обязательны)
    OPTIONAL_FILES = [
        "Game/Bin/TS4.exe",      # 32-битная версия (не обязательна)
        "Game/Bin/TS4_x86.exe",  # Старая версия (не обязательна)
    ]
    
    ESSENTIAL_FOLDERS = [
        "Game",
        "Data", 
        "Delta",           # Delta может отсутствовать в некоторых установках
        "Game/Bin",
        "Data/Client"
    ]
    
    @staticmethod
    def validate_game_path(path, logger=None):
        """Проверка игры - без ложных предупреждений о размере"""
        game_path = Path(path)
        issues = []
        
        if not game_path.exists():
            return False, ["Game folder doesn't exist"]
            
        # 1. ОБЯЗАТЕЛЬНО: TS4_x64.exe
        ts4_exe = game_path / "Game/Bin/TS4_x64.exe"
        if not ts4_exe.exists():
            issues.append("TS4_x64.exe missing - game cannot run")
        else:
            # ТОЛЬКО логируем размер, не проверяем
            try:
                size_mb = ts4_exe.stat().st_size / (1024 * 1024)
                if logger:
                    logger.log(f"[VALIDATE] TS4_x64.exe: {size_mb:.1f} MB")
            except:
                pass
                
        # 2. ОБЯЗАТЕЛЬНО: Основные папки
        required_folders = ["Game", "Data", "Game/Bin"]
        for folder in required_folders:
            if not (game_path / folder).exists():
                issues.append(f"Missing folder: {folder}")
                
        # 3. Проверка на Sims 4
        sims4_markers = [
            "Data/Client/ClientDeltaBuild0.package",
            "Data/Client/ClientFullBuild0.package",
            "Data/Simulation/FullBuild0.package"
        ]
        
        found_markers = sum(1 for marker in sims4_markers if (game_path / marker).exists())
        if found_markers < 1:
            issues.append("Doesn't appear to be a Sims 4 folder")
                
        return len(issues) == 0, issues


# 6. Внешняя DLC Database
class ExternalDatabase:
    DB_URL = "https://raw.githubusercontent.com/l1ntol/Linua-Updater/main/dlc_database.json"
    CACHE_TIME = 3600  # 1 час
    
    def __init__(self, logger):
        self.logger = logger
        self.cache_file = Path.home() / "AppData" / "Local" / "LinuaUpdater" / "dlc_cache.json"
        self.local_db = DLCDatabase().all()  # Используем локальную базу как fallback
        
    def fetch_remote_database(self, force=False):
        """Пытаться загрузить с GitHub, но использовать локальную если нет"""
        try:
            # Проверить кэш (опционально)
            if not force and self.cache_file.exists():
                try:
                    cache_age = time.time() - self.cache_file.stat().st_mtime
                    if cache_age < self.CACHE_TIME:
                        with open(self.cache_file, 'r', encoding='utf-8') as f:
                            cached_db = json.load(f)
                            self.logger.log("[DB] Using cached database")
                            return cached_db
                except:
                    pass
                        
            # Пытаться загрузить с GitHub
            self.logger.log("[DB] Trying to fetch database from GitHub...")
            response = requests.get(self.DB_URL, timeout=5, verify=False)
            if response.status_code == 200:
                db_data = response.json()
                
                # Сохранить в кэш
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(db_data, f, indent=2)
                    
                self.logger.log("[DB] Database updated from GitHub successfully")
                return db_data
                
        except Exception as e:
            self.logger.log(f"[DB] GitHub fetch failed: {e}. Using local database.")
            
        # Всегда возвращаем локальную базу как fallback
        return self.local_db
        
    def get_database(self, force_refresh=False):
        """Получить актуальную базу данных"""
        try:
            return self.fetch_remote_database(force_refresh)
        except:
            return self.local_db


# 7. Расширенный Repair-режим
class AdvancedRepair:
    def __init__(self, game_path, logger):
        self.game_path = Path(game_path)
        self.logger = logger
        
    def run_full_repair(self):
        """Полный ремонт игры - правильная проверка DLC"""
        results = {
            "checks": [],
            "fixed": [],
            "errors": [],
            "warnings": []
        }
        
        # 1. Проверка структуры игры
        results["checks"].append("Checking game structure...")
        structure_ok, issues = GameValidator.validate_game_path(self.game_path)
        if not structure_ok:
            results["errors"].extend(issues)
            
        # 2. Проверка DLC Sims 4 (ПРАВИЛЬНАЯ)
        results["checks"].append("Checking DLC folders...")
        dlc_folders = [f for f in self.game_path.iterdir() 
                      if f.is_dir() and f.name.upper().startswith(("EP", "GP", "SP", "FP"))]
        
        valid_dlc_count = 0
        total_dlc_size = 0
        
        for dlc in dlc_folders:
            valid, reason = DLCValidator.is_dlc_valid(dlc)
            if valid:
                valid_dlc_count += 1
                size_gb = DLCValidator.get_dlc_size(dlc)
                total_dlc_size += size_gb
                self.logger.log(f"[OK] {dlc.name} - {reason}")
            else:
                # Проверим если это может быть другим типом контента
                content_files = list(dlc.rglob("*"))
                if content_files:
                    # Есть файлы, но не похоже на стандартный DLC
                    results["warnings"].append(f"{dlc.name}: Non-standard content ({len(content_files)} files)")
                else:
                    # Пустая папка - удалить?
                    results["warnings"].append(f"{dlc.name}: Empty folder")
                
        results["checks"].append(f"Found {valid_dlc_count}/{len(dlc_folders)} valid DLC ({total_dlc_size:.1f} GB total)")
        
        # 3. Проверка TS4_x64.exe
        exe_path = self.game_path / "Game/Bin/TS4_x64.exe"
        if exe_path.exists():
            try:
                size_mb = exe_path.stat().st_size / (1024 * 1024)
                results["checks"].append(f"TS4_x64.exe: {size_mb:.1f} MB")
                
                # Диапазон размеров для разных версий Sims 4
                if size_mb > 30 and size_mb < 200:
                    results["fixed"].append(f"Game executable OK ({size_mb:.1f} MB)")
                elif size_mb < 30:
                    results["warnings"].append(f"TS4_x64.exe small ({size_mb:.1f} MB)")
                else:
                    results["warnings"].append(f"TS4_x64.exe large ({size_mb:.1f} MB)")
            except:
                results["checks"].append("TS4_x64.exe: Unable to get size")
        else:
            results["errors"].append("TS4_x64.exe missing")
                
        # 4. Очистка временных файлов
        results["checks"].append("Cleaning temp files...")
        cleaned = self.clean_temp_files()
        if cleaned:
            results["fixed"].append(f"Cleaned {cleaned} temp files")
            
        # 5. Проверка прав
        results["checks"].append("Checking permissions...")
        if not self.check_permissions():
            results["warnings"].append("Insufficient write permissions")
            
        # 6. Сводка
        if not results["errors"]:
            results["fixed"].append("No critical errors found")
            
        report = self.generate_report(results)
        return results, report
        
        
    def clean_temp_files(self):
        """Очистка временных файлов"""
        patterns = [
            "*.tmp", "*.temp", "Thumbs.db", "desktop.ini",
            "_linua_*", "*.part", "*.crdownload"
        ]
        
        cleaned = 0
        for pattern in patterns:
            for file in self.game_path.rglob(pattern):
                try:
                    if file.is_file():
                        file.unlink()
                        cleaned += 1
                except:
                    pass
        return cleaned
                    
    def check_permissions(self):
        """Проверка прав на запись"""
        test_file = self.game_path / ".permission_test"
        try:
            test_file.touch()
            test_file.unlink()
            return True
        except:
            return False
            
    def generate_report(self, results):
        """Создать отчет о ремонте"""
        report_lines = [
            "=== Linua Updater Repair Report ===",
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Game path: {self.game_path}",
            ""
        ]
        
        if results["checks"]:
            report_lines.append("Checks performed:")
            for check in results["checks"]:
                report_lines.append(f"  • {check}")
                
        if results["fixed"]:
            report_lines.append("\nIssues fixed:")
            for fix in results["fixed"]:
                report_lines.append(f"  ✓ {fix}")
                
        if results["warnings"]:
            report_lines.append("\nWarnings:")
            for warning in results["warnings"]:
                report_lines.append(f"  ⚠ {warning}")
                
        if results["errors"]:
            report_lines.append("\nCritical errors:")
            for error in results["errors"]:
                report_lines.append(f"  ✗ {error}")
                
        return "\n".join(report_lines)


# 8. Offline-режим
class OfflineMode:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.is_offline = False
        
    def check_connection(self):
        """Проверить подключение"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            socket.create_connection(("github.com", 443), timeout=2)
            self.is_offline = False
            return True
        except:
            self.is_offline = True
            self.enable_offline_mode()
            return False
            
    def enable_offline_mode(self):
        """Включить оффлайн-режим"""
        self.logger.log("[OFFLINE] Running in offline mode")
        
    def get_available_features(self):
        """Получить доступные функции в оффлайн-режиме"""
        if self.is_offline:
            return {
                "repair": True,
                "validate": True,
                "check_installed": True,
                "cleanup": True,
                "update": False,
                "download": False,
                "auto_update": False
            }
        return {
            "repair": True,
            "validate": True,
            "check_installed": True,
            "cleanup": True,
            "update": True,
            "download": True,
            "auto_update": True
        }


# ================================================================
#                         DLC DATABASE
# ================================================================
class DLCDatabase:
    def __init__(self):
        # База данных из старого кода (103 DLC)
        self.dlc = {
            "EP01": {"name": "Get to Work", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP01/Sims4_DLC_EP01_Get_to_Work.zip"},
            "EP02": {"name": "Get Together", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP02/Sims4_DLC_EP02_Get_Together.zip"},
            "EP04": {"name": "Cats and Dogs", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP04/Sims4_DLC_EP04_Cats_and_Dogs.zip"},
            "EP05": {"name": "Seasons", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/EP05/Sims4_DLC_EP05_Seasons.zip"},
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
            "SP16": {"name": "Tiny Living Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP16/Sims4_DLC_SP16_Tiny_Living_Stuff_Pack.zip"},
            "SP17": {"name": "Nifty Knitting", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP17/Sims4_DLC_SP17_Nifty_Knitting.zip"},
            "SP18": {"name": "Paranormal Stuff", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP18/Sims4_DLC_SP18_Paranormal_Stuff_Pack.zip"},
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
            "SP70": {"name": "Spongebob Kid's Room Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP70/SP70.zip"},
            "SP68": {"name": "Spongebob's House Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP68/SP68.zip"},
            "SP81": {"name": "Prairie Dreams Kit", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/SP81/SP81.zip"},
            "FP01": {"name": "Holiday Celebration Pack", "url": "https://github.com/l1ntol/lunia-dlc/releases/download/FP01/Sims4_DLC_FP01_Holiday_Celebration_Pack.zip"},
        }

    def all(self):
        return self.dlc


# ================================================================
#                     SELECT DLC DIALOG - из старого кода
# ================================================================
class DLCSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select DLC")
        self.setFixedSize(540, 640)
        self.apply_dark_theme()

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

    def apply_dark_theme(self):
        css = """
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
        """
        self.setStyleSheet(css)

    def toggle_all(self, state):
        val = (state == Qt.CheckState.Checked)
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


# ================================================================
#                           MAIN UI
# ================================================================
class LinuaUI(QMainWindow):
    def __init__(self, config, db):
        super().__init__()

        self.config = config
        self.db = db

        self.setWindowTitle(f"Linua Updater v{APP_VERSION}")
        self.setFixedSize(620, 520)

        # UI
        self.setup_ui()
        self.apply_dark_theme()

        self.logger = Logger(self.log_text)
        
        # ===== ИНИЦИАЛИЗАЦИЯ СИСТЕМ =====
        self.thread_manager = ThreadManager()
        self.controller = AppController(self.logger, self.thread_manager)
        self.download_manager = DownloadManager(max_workers=2, logger=self.logger)
        self.rollback_manager = None
        self.offline_mode = OfflineMode(config, self.logger)
        self.external_db = ExternalDatabase(self.logger)
        # Убрали AutoUpdater - больше не проверяем обновления
        # ====================================

        self.active_threads = []
        self.progress_total = 0
        self.progress_done = 0
        
        # Load saved path
        saved = self.config.get("game_path", "")
        if saved:
            self.path_input.setText(saved)
            self.logger.log(f"[GAME] Path loaded from config: {saved}")

        # Проверка соединения
        if not self.offline_mode.check_connection():
            self.logger.log("[OFFLINE] Internet not detected. Some features disabled.")
        else:
            self.logger.log("[ONLINE] Internet connection OK.")
            # Убрали автоматическую проверку обновлений

        # Auto detect game
        QTimer.singleShot(200, self.auto_detect)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # title
        title = QLabel(f"Linua Updater v{APP_VERSION}")
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

        # update + repair + cancel (убрали кнопку Check Updates)
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

        self.update_btn.clicked.connect(self.on_update)
        self.repair_btn.clicked.connect(self.on_repair)
        # Убрали кнопку проверки обновлений

        # progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Лейбл для прогресса
        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet("color: #00ff00; font-size: 11px; padding: 2px;")
        layout.addWidget(self.progress_label)

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
        self.logger.log("Opening folder browser...")
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select The Sims 4 Folder",
            self.path_input.text() or "C:\\"
        )
        if folder:
            self.path_input.setText(folder)
            self.config.set("game_path", folder)
            self.logger.log("Folder selected")

    def auto_detect(self):
        """Автоматическое обнаружение игры - из старого кода"""
        self.logger.log("Detecting The Sims 4...")

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
                    self.config.set("game_path", full_path)
                    self.logger.log(f"[GAME] Found game: {full_path}")
                    return

        self.logger.log("Game not found automatically")

    def detect_installed(self, game_path):
        """Обнаружение установленных DLC - из старого кода"""
        installed = set()
        if not os.path.exists(game_path):
            return installed
        for item in os.listdir(game_path):
            u = item.upper()
            if u.startswith(("EP", "GP", "SP", "FP")):
                installed.add(u)
        return installed

    def log_message(self, message, level="INFO"):
        """Улучшенное логирование с уровнями - из старого кода"""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        level_color = {
            "INFO": "white",
            "WARNING": "yellow", 
            "ERROR": "red",
            "SUCCESS": "lightgreen"
        }
        color = level_color.get(level, "white")
        
        self.log_text.append(f'<font color="{color}">{timestamp} [{level}] {message}</font>')

    
    def on_update(self):
        """Обработчик кнопки Update - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            path = self.path_input.text().strip()
            
            # Валидация пути
            if not path:
                self.logger.log("Please select a game folder first.")
                return
            
            # Упрощенная проверка
            if not os.path.exists(path):
                self.logger.log("Game folder doesn't exist.")
                return
                
            # Проверяем только TS4_x64.exe
            ts4_exe = os.path.join(path, "Game", "Bin", "TS4_x64.exe")
            if not os.path.exists(ts4_exe):
                self.logger.log("TS4_x64.exe not found.")
                reply = QMessageBox.question(
                    self, 
                    "Confirm", 
                    "TS4_x64.exe not found. This may not be a valid Sims 4 folder.\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            else:
                # Просто логируем размер
                try:
                    size_mb = os.path.getsize(ts4_exe) / (1024 * 1024)
                    self.logger.log(f"TS4_x64.exe found: {size_mb:.1f} MB")
                except:
                    self.logger.log("TS4_x64.exe found (size unknown)")
            
            # Проверка свободного места
            has_space, free_gb = DiskChecker.check_disk_space(path, required_gb=15)
            if not has_space:
                self.logger.log(f"ERROR: Not enough disk space. Only {free_gb:.1f}GB free, need at least 15GB")
                QMessageBox.critical(
                    self,
                    "Low Disk Space",
                    f"Only {free_gb:.1f}GB free space available.\nNeed at least 15GB for installation.\nPlease free up some space and try again."
                )
                return
            elif free_gb < 25:  # Предупреждение если мало места
                self.logger.log(f"Warning: Only {free_gb:.1f}GB free space available")
                QMessageBox.warning(
                    self,
                    "Low Disk Space",
                    f"Warning: Only {free_gb:.1f}GB free space available.\nConsider freeing up more space for optimal performance."
                )
            
            # Проверка DLC которые уже установлены
            installed = self.detect_installed(path)
            
            # Использовать улучшенный диалог выбора DLC
            dlg = DLCSelector(self)
            dlg.populate(self.db.all(), installed)
            
            result = dlg.exec()
            if result != QDialog.DialogCode.Accepted:
                self.logger.log("DLC selection cancelled.")
                return
                
            selected = dlg.get()
            if not selected:
                self.logger.log("No DLC selected.")
                return
                
            # Подтверждение установки
            confirm_msg = (
                f"You are about to install {len(selected)} DLC.\n"
                f"Free space: {free_gb:.1f} GB\n\n"
                f"Continue with installation?"
            )
            
            reply = QMessageBox.question(
                self,
                "Confirm Installation",
                confirm_msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.start_install_process(selected, path)
        
        except Exception as e:
            self.logger.log(f"Error in DLC selection: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to start installation: {str(e)}")

    def start_install_process(self, selected, game_path):
        """Запуск процесса установки"""
        self.logger.log(f"Starting installation with {len(selected)} DLC")
        
        if not selected:
            self.logger.log("No DLC selected for installation.")
            return

        try:
            # Проверяем наличие 7-zip для многодольных DLC
            multipart_dlc = []
            for dlc in selected:
                if dlc in self.db.all() and "parts" in self.db.all()[dlc]:
                    multipart_dlc.append(dlc)
                    
            if multipart_dlc:
                self.logger.log(f"Multipart DLC found: {multipart_dlc}")
                seven_finder = SevenZipFinder(self.logger)
                seven_path = seven_finder.find()
                if not seven_path:
                    self.logger.log("ERROR: 7-zip required for multipart DLC but not found!")
                    msg = QMessageBox(self)
                    msg.setWindowTitle("7-zip Required")
                    msg.setText("Multipart DLC require 7-zip.")
                    msg.setInformativeText("Please install 7-zip from official website and try again.")
                    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                    msg.exec()
                    return

            self.progress_total = len(selected)
            self.progress_done = 0

            self.progress_bar.setVisible(True)
            self.progress_bar.setMaximum(self.progress_total)
            self.progress_bar.setValue(0)

            self.update_btn.setEnabled(False)
            self.repair_btn.setEnabled(False)
            # Убрали check_update_btn
            self.cancel_btn.setVisible(True)

            self.logger.log(f"Installing {len(selected)} DLC...")

            self.active_threads = []

            for dlc_id in selected:
                if dlc_id not in self.db.all():
                    self.logger.log(f"ERROR: DLC {dlc_id} not found in database")
                    continue
                    
                info = self.db.all()[dlc_id]

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
                
        except Exception as e:
            self.logger.log(f"ERROR in start_install_process: {str(e)}")
            self.logger.log(f"ERROR traceback: {traceback.format_exc()}")
            self.progress_bar.setVisible(False)
            self.update_btn.setEnabled(True)
            self.repair_btn.setEnabled(True)
            # Убрали check_update_btn
            self.cancel_btn.setVisible(False)
            QMessageBox.critical(self, "Error", f"Failed to start installation: {str(e)}")

    @pyqtSlot(str, bool, str)
    def install_done(self, dlc_id, success, reason):
        """Обработчик завершения установки DLC - из старого кода"""
        self.progress_done += 1
        self.progress_bar.setValue(self.progress_done)

        if success:
            self.logger.log(f"✓ {dlc_id} installed successfully.")
        else:
            self.logger.log(f"✗ {dlc_id} failed — {reason}")

        if self.progress_done == self.progress_total:
            self.finish_install()

    def finish_install(self):
        """Завершение процесса установки - из старого кода"""
        self.logger.log("✓ Installation complete.")
        self.progress_bar.setVisible(False)

        self.update_btn.setEnabled(True)
        self.repair_btn.setEnabled(True)
        # Убрали check_update_btn
        self.cancel_btn.setVisible(False)

        QMessageBox.information(self, "Done", "All selected DLC were installed.")

    def cancel_installation(self):
        """Отмена текущей установки"""
        self.logger.log("Cancelling installation...")
        
        # Отмена через thread_manager
        if hasattr(self, 'thread_manager') and self.thread_manager:
            self.thread_manager.cancel_all()
        
        # Отмена через download_manager
        if hasattr(self, 'download_manager'):
            self.download_manager.cancel_all()
        
        # Остановить активные потоки
        for thread in self.active_threads:
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
        self.active_threads.clear()
        
        # Вернуть UI в исходное состояние
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.update_btn.setEnabled(True)
        self.repair_btn.setEnabled(True)
        # Убрали check_update_btn
        self.cancel_btn.setVisible(False)
        self.logger.log("Installation cancelled")

    def on_repair(self):
        """Обработчик кнопки Repair - улучшенная версия"""
        path = self.path_input.text().strip()
        if not path or not os.path.isdir(path):
            self.logger.log("Invalid game folder.")
            return

        # Спросить какой тип ремонта
        dialog = QDialog(self)
        dialog.setWindowTitle("Repair Options")
        dialog.setFixedSize(300, 200)
        dialog.setStyleSheet(self.styleSheet())
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("Select repair type:"))
        
        btn_quick = QPushButton("Quick Repair (Basic)")
        btn_quick.clicked.connect(lambda: self.run_quick_repair(path, dialog))
        
        btn_full = QPushButton("Full Repair (Advanced)")
        btn_full.clicked.connect(lambda: self.enhanced_repair(path, dialog))
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dialog.reject)
        
        layout.addWidget(btn_quick)
        layout.addWidget(btn_full)
        layout.addWidget(btn_cancel)
        
        dialog.exec()
        
    def run_quick_repair(self, path, dialog):
        dialog.accept()
        self.logger.log("Starting quick repair...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)
    
        if self.controller:
            self.repair_thread = self.controller.run_repair(path, self.repair_done)
        else:
            self.logger.log("Error: Controller not initialized")

    def enhanced_repair(self, path, dialog):
        dialog.accept()
        self.logger.log("[REPAIR] Starting advanced repair...")
        
        repair = AdvancedRepair(path, self.logger)
        results, report = repair.run_full_repair()
        
        # Показать отчет
        result_dialog = QDialog(self)
        result_dialog.setWindowTitle("Repair Report")
        result_dialog.setFixedSize(500, 400)
        result_dialog.setStyleSheet(self.styleSheet())
        
        layout = QVBoxLayout(result_dialog)
        
        text = QTextEdit()
        text.setPlainText(report)
        text.setReadOnly(True)
        text.setStyleSheet("background-color: #0a0a0a; color: #00ff00; font-family: Consolas;")
        
        layout.addWidget(text)
        
        button_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save Report")
        save_btn.clicked.connect(lambda: self.save_report(report))
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(result_dialog.accept)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        result_dialog.exec()

    @pyqtSlot(bool)
    def repair_done(self, ok):
        """Обработчик завершения ремонта - из старого кода"""
        self.progress_bar.setVisible(False)

        if ok:
            self.logger.log("✓ Repair finished successfully.")
        else:
            self.logger.log("✗ Repair failed.")

        QMessageBox.information(self, "Repair complete", "Repair process finished.")

    def closeEvent(self, event):
        """Обработчик закрытия окна - безопасное завершение потоков"""
        try:
            self.logger.log("Shutting down application...")
            
            # Отключить все кнопки чтобы предотвратить новые действия
            self.update_btn.setEnabled(False)
            self.repair_btn.setEnabled(False)
            
            # Остановить все операции
            if hasattr(self, 'thread_manager') and self.thread_manager:
                self.thread_manager.cancel_all()
                
            if hasattr(self, 'download_manager'):
                self.download_manager.cancel_all()
                
            # Очистить временные файлы
            self.cleanup_temporary_files()
            
            # Подождать немного чтобы потоки успели завершиться
            QApplication.processEvents()
            time.sleep(0.5)
            
            event.accept()
        except Exception as e:
            self.logger.log(f"Error during shutdown: {e}")
            event.accept()
            
    def cleanup_temporary_files(self):
        """Очистка временных файлов"""
        try:
            temp_dir = tempfile.gettempdir()
            patterns = ["*.tmp", "*.zip", "*.7z.*", "_linua_*", "*.part"]
            
            for pattern in patterns:
                import glob
                for file in glob.glob(os.path.join(temp_dir, pattern)):
                    try:
                        if os.path.isfile(file):
                            os.remove(file)
                        elif os.path.isdir(file):
                            shutil.rmtree(file, ignore_errors=True)
                    except:
                        pass
        except:
            pass
                
    def save_report(self, report):
        """Сохранить отчет в файл"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", 
            f"linua_repair_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(report)
                self.logger.log(f"[REPORT] Saved to {file_path}")
            except Exception as e:
                self.logger.log(f"[ERROR] Failed to save report: {e}")


# ================================================================
#                         ENTRY POINT
# ================================================================
if __name__ == "__main__":

    # Windows Admin Check
    if platform.system() == "Windows":
        import ctypes
        
        # Helper function
        def is_admin():
            try:
                return ctypes.windll.shell32.IsUserAnAdmin()
            except:
                return False
        
        if not is_admin():
            # Rerun script asking for admin priveleges
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                " ".join(sys.argv),
                None,
                1
            )
            # Exit original non-admin process
            sys.exit()

    # Включить поддержку High DPI
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Установить имя приложения для Windows
    app.setApplicationName("Linua Updater")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("l1ntol")
    
    config = ConfigManager()
    db = DLCDatabase()

    window = LinuaUI(config, db)
    window.show()

    sys.exit(app.exec())