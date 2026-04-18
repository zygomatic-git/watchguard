"""
╔══════════════════════════════════════════════════════════════╗
║              Watchguard Bot v3.0                             ║
║          Tek dosya · Taşınabilir · Güvenilir                 ║
╠══════════════════════════════════════════════════════════════╣
║  Değişiklikler v3.0:                                         ║
║                                                              ║
║  🔐 PersistentStore                                          ║
║     · BOT_TOKEN, OWNER_ID, SHELL_PIN artık watchguard.dat    ║
║     · zlib+base64 obfüskasyonu                               ║
║     · Tüm kalıcı veriler tek dosyada (config+identity+       ║
║       settings+security)                                     ║
║                                                              ║
║  💻 Multi-Computer Seçimi                                    ║
║     · /computers — tüm bilgisayarları listele / seç          ║
║     · /ping — tüm bilgisayarları pinle                       ║
║     · is_selected ayarı (varsayılan: True)                   ║
║                                                              ║
║  ⌨️ ReplyKeyboard + BotMenu                                  ║
║     · Kalıcı hızlı erişim klavyesi                           ║
║     · set_my_commands() ile menü                             ║
║                                                              ║
║  📸 JPEG Screenshot                                          ║
║     · PNG yerine %85 kalite JPEG                             ║
║                                                              ║
║  🎥 Video Çözünürlük Ölçekleme                               ║
║     · VIDEO_RESOLUTION_SCALE ayarı                           ║
║                                                              ║
║  💬 /msg Komutu                                              ║
║     · GUI kaldırıldı, basit tkinter messagebox               ║
║                                                              ║
║  🐚 /shell (eski /run)                                       ║
║     · Komut yeniden adlandırıldı                             ║
║                                                              ║
║  🐛 disk_usage Windows düzeltmesi                            ║
╚══════════════════════════════════════════════════════════════╝

KURULUM:
  install.ps1 dosyasını çalıştırın — otomatik kurulum yapar.
  Task Scheduler'da otomatik başlatma ayarlanır.
"""

import os
import sys
import io
import time
import threading
import tempfile
import subprocess
import platform
import logging
import logging.handlers
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import json
import hashlib
import socket
import zlib
import base64

# ──────────────────────────────────────────────────────────────────────────────
# Script dizini — Task Scheduler'da CWD farklı olabilir,
# bu yüzden tüm dosyalar SCRIPT_DIR'e göre açılır/yazılır.
# ──────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════════════════════
# PAKET KURULUM
# ══════════════════════════════════════════════════════════════════════════════

REQUIRED_PACKAGES = {
    'telebot':      'pyTelegramBotAPI',
    'pyautogui':    'pyautogui',
    'PIL':          'pillow',
    'psutil':       'psutil',
    'cv2':          'opencv-python',
    'numpy':        'numpy',
    'pynput':       'pynput',
    'screeninfo':   'screeninfo',
    'mss':          'mss',
    'sounddevice':  'sounddevice',
    'soundfile':    'soundfile',
    'dxcam':        'dxcam',
}

def ensure_packages():
    """Eksik paketleri kur; gerekirse script'i yeniden başlat."""
    import importlib
    import importlib.util
    missing = [pkg for mod, pkg in REQUIRED_PACKAGES.items()
               if not importlib.util.find_spec(mod)]

    if not missing:
        return

    print(f"[Kurulum] Eksik paketler yukleniyor: {', '.join(missing)}")
    for pkg in missing:
        try:
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', pkg, '--quiet'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print(f"[Kurulum] OK: {pkg}")
        except Exception as e:
            print(f"[Kurulum] HATA: {pkg}: {e}")

    print("[Kurulum] Script yeniden baslatiliyor...")
    subprocess.Popen([sys.executable, os.path.abspath(__file__)])
    sys.exit(0)

ensure_packages()

# ── Paket importları (kurulum tamamlandıktan sonra) ───────────────────────────
import tkinter as tk
import telebot
from telebot.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                            ReplyKeyboardMarkup, KeyboardButton, BotCommand)
from PIL import Image, ImageGrab
import pyautogui
import psutil
import getpass


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENT STORE  (watchguard.dat'tan yüklenir — tüm kalıcı veriler)
# ══════════════════════════════════════════════════════════════════════════════

class PersistentStore:
    """
    Tek dosyada tüm kalıcı veriler.
    watchguard.dat = zlib+base64 obfüske edilmiş JSON

    Yapı:
    {
      "config":   {bot_token, owner_id, shell_pin},
      "identity": {id, name, emoji, created, platform},
      "settings": {quiet_hours_enabled, is_selected},
      "security": {enabled, updated}
    }
    """

    DAT_PATH = os.path.join(
        os.environ.get('APPDATA', ''),
        'Microsoft', 'Windows', 'Themes', 'Watchguard', 'watchguard.dat'
    )

    _SETTINGS_DEFAULTS = {
        'quiet_hours_enabled': False,
        'is_selected': True,
    }
    _SECURITY_DEFAULTS = {
        'enabled': False,
    }

    def __init__(self):
        self._data: dict = {}
        self._load()

    # ── Encode / Decode ───────────────────────────────────────────────────────

    @staticmethod
    def _encode(data: dict) -> str:
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        return base64.b64encode(zlib.compress(raw)).decode('utf-8')

    @staticmethod
    def _decode(text: str) -> dict:
        return json.loads(zlib.decompress(base64.b64decode(text.strip())))

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load(self):
        if not os.path.exists(self.DAT_PATH):
            print(f"[HATA] watchguard.dat bulunamadı: {self.DAT_PATH}")
            print("[HATA] Lütfen install.ps1 dosyasını çalıştırın.")
            sys.exit(1)
        try:
            with open(self.DAT_PATH, 'r', encoding='utf-8') as f:
                raw = self._decode(f.read())
        except Exception as e:
            print(f"[HATA] watchguard.dat okunamadı: {e}")
            sys.exit(1)

        # Eski format geçiş: düz {bot_token, owner_id, shell_pin}
        if 'config' not in raw and 'bot_token' in raw:
            self._data = {
                'config':   raw,
                'identity': {},
                'settings': dict(self._SETTINGS_DEFAULTS),
                'security': dict(self._SECURITY_DEFAULTS),
            }
            self._save()
        else:
            self._data = raw
            # Eksik anahtarları varsayılanla doldur
            self._data.setdefault('identity', {})
            self._data.setdefault('settings', dict(self._SETTINGS_DEFAULTS))
            self._data.setdefault('security', dict(self._SECURITY_DEFAULTS))

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.DAT_PATH), exist_ok=True)
            with open(self.DAT_PATH, 'w', encoding='utf-8') as f:
                f.write(self._encode(self._data))
        except Exception as e:
            logging.getLogger('Watchguard').error(f"watchguard.dat kayıt hatası: {e}")

    # ── Config (sadece okunur) ────────────────────────────────────────────────

    @property
    def bot_token(self) -> str:
        return self._data.get('config', {}).get('bot_token', '')

    @property
    def owner_id(self) -> int:
        return int(self._data.get('config', {}).get('owner_id', 0))

    @property
    def shell_pin(self):
        return self._data.get('config', {}).get('shell_pin')

    # ── Identity ──────────────────────────────────────────────────────────────

    def get_identity(self) -> dict:
        return dict(self._data.get('identity', {}))

    def set_identity(self, data: dict):
        self._data['identity'] = data
        self._save()

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_setting(self, key: str):
        return self._data.get('settings', {}).get(key, self._SETTINGS_DEFAULTS.get(key))

    def set_setting(self, key: str, value):
        self._data.setdefault('settings', {})[key] = value
        self._save()

    def toggle_setting(self, key: str) -> bool:
        new_val = not self.get_setting(key)
        self.set_setting(key, new_val)
        return new_val

    # ── Security state ────────────────────────────────────────────────────────

    def get_security(self) -> dict:
        return dict(self._data.get('security', {}))

    def set_security(self, enabled: bool):
        self._data.setdefault('security', {})['enabled'] = enabled
        self._data['security']['updated'] = datetime.now().isoformat()
        self._save()


# Modül seviyesinde tek örnek — ensure_packages() tamamlandıktan sonra
store = PersistentStore()


# ══════════════════════════════════════════════════════════════════════════════
# YAPILANDIRMA (geri kalan sabit ayarlar)
# ══════════════════════════════════════════════════════════════════════════════

class Config:
    """
    ┌─────────────────────────────────────────────┐
    │  Statik ayarlar — BOT_TOKEN/OWNER_ID/PIN     │
    │  artık PersistentStore'da (watchguard.dat)   │
    └─────────────────────────────────────────────┘
    """

    # ── Bilgisayar kimliği (None = otomatik) ──────────────────────────────────
    COMPUTER_NAME  = None    # Örn: "Ev Bilgisayarı" | None → user@hostname
    COMPUTER_EMOJI = '✈️'  # Örn: "🏠" | None → rastgele

    # ── Güncelleme ────────────────────────────────────────────────────────────
    GITHUB_RAW_URL = (
        "https://raw.githubusercontent.com/zygomatic-git/watchguard/main/watchguard_v3.pyw"
    )

    # ── Bellek içi log buffer ─────────────────────────────────────────────────
    LOG_BUFFER_SIZE     = 200   # Bellekte tutulacak maksimum satır sayısı

    # ── Video ─────────────────────────────────────────────────────────────────
    VIDEO_DURATION          = 10    # Normal kayıt süresi (saniye)
    VIDEO_FPS               = 10
    MAX_VIDEO_SIZE_MB       = 50
    VIDEO_RESOLUTION_SCALE  = 0.5   # 0.5 → %50 çözünürlük (~960×540), 1.0 → tam
    # Codec deneme sırası: (fourcc, uzantı, açıklama)
    VIDEO_CODECS = [
        ('avc1', '.mp4',  'H.264'),   # en küçük — FFMPEG gerekir
        ('VP80', '.webm', 'WebM/VP8'),# H.264 yoksa WebM — FFMPEG gerekir
        ('mp4v', '.mp4',  'MPEG-4'),  # her zaman çalışır, büyük dosya
    ]

    # ── Güvenlik modu ─────────────────────────────────────────────────────────
    SECURITY_VIDEO_DURATION  = 30    # saniye
    SECURITY_COOLDOWN        = 60    # Bir sonraki tetiklenme için bekleme (saniye)
    SECURITY_MOUSE_THRESHOLD = 80    # Toplam piksel hareketi eşiği

    # ── Sessiz saatler (24s format) ───────────────────────────────────────────
    QUIET_HOURS_START = 0    # 00:00
    QUIET_HOURS_END   = 7    # 07:00

    # ── Periyodik rapor ───────────────────────────────────────────────────────
    DAILY_REPORT_HOUR = 9    # Her sabah 09:00'da sistem raporu gönder

    # ── Mikrofon ──────────────────────────────────────────────────────────────
    MIC_DURATION     = 10    # Varsayılan kayıt süresi (saniye)
    MIC_MAX_DURATION = 300   # Maksimum kayıt süresi (saniye) — 5 dakika

    # ── Sistem izleme ─────────────────────────────────────────────────────────
    LOW_BATTERY_THRESHOLD = 20
    CHECK_INTERVAL        = 60    # saniye

    # ── Log rotation ──────────────────────────────────────────────────────────

    # ── Network ───────────────────────────────────────────────────────────────
    MAX_RETRIES  = 5
    RETRY_DELAY  = 5

    COMPUTER_EMOJIS = ['💻', '🖥️', '⚡', '🔥', '💎', '🌟', '🚀', '🎯', '⭐', '🌈']


# ══════════════════════════════════════════════════════════════════════════════
# BİLGİSAYAR KİMLİĞİ
# ══════════════════════════════════════════════════════════════════════════════

class ComputerIdentity:
    """Her bilgisayar için kalıcı, benzersiz kimlik."""

    def __init__(self, store: PersistentStore):
        self._store = store
        self.computer_id    = None
        self.computer_name  = None
        self.computer_emoji = None
        self._load_or_create()

    def _generate_id(self) -> str:
        try:
            import uuid
            mac = ':'.join([f'{(uuid.getnode() >> i) & 0xff:02x}' for i in range(0, 48, 8)][::-1])
        except Exception:
            mac = 'unknown'
        raw = f"{socket.gethostname()}_{getpass.getuser()}_{mac}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _load_or_create(self):
        data = self._store.get_identity()
        if data.get('id'):
            self.computer_id    = data['id']
            self.computer_name  = data['name']
            self.computer_emoji = data['emoji']
            return
        # Create new identity
        self.computer_id    = self._generate_id()
        self.computer_name  = Config.COMPUTER_NAME or f"{getpass.getuser()}@{platform.node()}"
        if Config.COMPUTER_EMOJI:
            self.computer_emoji = Config.COMPUTER_EMOJI
        else:
            import random
            self.computer_emoji = random.choice(Config.COMPUTER_EMOJIS)
        self._save()

    def _save(self):
        self._store.set_identity({
            'id':       self.computer_id,
            'name':     self.computer_name,
            'emoji':    self.computer_emoji,
            'created':  datetime.now().isoformat(),
            'platform': platform.platform(),
        })

    def display_name(self) -> str:
        return f"{self.computer_emoji} {self.computer_name}"

    def short_id(self) -> str:
        return self.computer_id[:6]


# ══════════════════════════════════════════════════════════════════════════════
# LOGLAMA (Sadece bellek içi — disk'e yazılmaz)
# ══════════════════════════════════════════════════════════════════════════════

class _DequeHandler(logging.Handler):
    """Son N log satırını bellekte tutan handler."""
    def __init__(self, maxlen: int):
        super().__init__()
        from collections import deque
        self._buf: deque = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord):
        self._buf.append(self.format(record))

    def get_lines(self, n: int = None) -> List[str]:
        lines = list(self._buf)
        return lines[-n:] if n else lines

    def clear(self):
        self._buf.clear()


class LogManager:
    def __init__(self, identity: ComputerIdentity):
        self.identity = identity
        self._setup()

    def _setup(self):
        fmt = f'%(asctime)s [{self.identity.short_id()}] %(levelname)s - %(message)s'
        formatter = logging.Formatter(fmt)

        self._deque_handler = _DequeHandler(maxlen=Config.LOG_BUFFER_SIZE)
        self._deque_handler.setFormatter(formatter)

        # stdout handler — sadece geliştirme sırasında görünür, .pyw'de pencere yok
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        self._log = logging.getLogger('Watchguard')
        self._log.setLevel(logging.INFO)
        if not self._log.handlers:
            self._log.addHandler(self._deque_handler)
            self._log.addHandler(stream_handler)

    def info(self, msg: str):    self._log.info(msg)
    def warning(self, msg: str): self._log.warning(msg)
    def error(self, msg: str, exc_info=False): self._log.error(msg, exc_info=exc_info)
    def debug(self, msg: str):   self._log.debug(msg)

    def get_lines(self, n: int = None) -> List[str]:
        return self._deque_handler.get_lines(n)

    def clear(self):
        self._deque_handler.clear()


# ══════════════════════════════════════════════════════════════════════════════
# AYARLAR YÖNETİCİSİ (Kalıcı toggle'lar)
# ══════════════════════════════════════════════════════════════════════════════

class SettingsManager:
    """Quiet hours, is_selected gibi kullanıcının toggle ettiği ayarları store'a yazar."""

    _DEFAULTS = {
        'quiet_hours_enabled': False,
        'is_selected': True,
    }

    def __init__(self, store: PersistentStore):
        self._store = store
        self._quiet_log: List[str] = []

    def get(self, key):
        return self._store.get_setting(key) if self._store.get_setting(key) is not None \
               else self._DEFAULTS.get(key)

    def set(self, key, value):
        self._store.set_setting(key, value)

    def toggle(self, key) -> bool:
        return self._store.toggle_setting(key)

    @property
    def quiet_hours_enabled(self) -> bool:
        return self.get('quiet_hours_enabled')

    def is_quiet_time(self) -> bool:
        """Şu an sessiz saatlerin içinde miyiz?"""
        if not self.quiet_hours_enabled:
            return False
        h     = datetime.now().hour
        start = Config.QUIET_HOURS_START
        end   = Config.QUIET_HOURS_END
        if start <= end:
            return start <= h < end
        # Gece yarısını geçen aralık (örn. 22–06)
        return h >= start or h < end

    def log_quiet_event(self, event: str):
        """Sessiz saatlerde bastırılan olayı kuyruğa ekle."""
        ts = datetime.now().strftime('%H:%M')
        self._quiet_log.append(f"[{ts}] {event}")

    def pop_quiet_log(self) -> List[str]:
        """Kuyruğu döndür ve temizle."""
        log = list(self._quiet_log)
        self._quiet_log.clear()
        return log


# ══════════════════════════════════════════════════════════════════════════════
# ÇOKLU MONİTÖR
# ══════════════════════════════════════════════════════════════════════════════

class MultiMonitorManager:
    def __init__(self, logger: LogManager):
        self.logger   = logger
        self.monitors = self._detect()

    def _detect(self) -> List[Dict]:
        try:
            from screeninfo import get_monitors
            return [
                {
                    'id':         i,
                    'name':       m.name,
                    'width':      m.width,
                    'height':     m.height,
                    'x':          m.x,
                    'y':          m.y,
                    'is_primary': getattr(m, 'is_primary', i == 0),
                }
                for i, m in enumerate(get_monitors())
            ]
        except Exception as e:
            self.logger.warning(f"Monitör tespiti başarısız: {e}")
            size = pyautogui.size()
            return [{'id': 0, 'name': 'Primary', 'width': size.width,
                     'height': size.height, 'x': 0, 'y': 0, 'is_primary': True}]

    def capture_all(self) -> Image.Image:
        try:
            return ImageGrab.grab(all_screens=True)
        except Exception:
            return pyautogui.screenshot()

    def capture_one(self, monitor_id: int) -> Optional[Image.Image]:
        if monitor_id >= len(self.monitors):
            return None
        m = self.monitors[monitor_id]
        try:
            return ImageGrab.grab(bbox=(m['x'], m['y'],
                                        m['x'] + m['width'],
                                        m['y'] + m['height']))
        except Exception as e:
            self.logger.error(f"Monitör {monitor_id} yakalama hatası: {e}")
            return None

    def info_text(self) -> str:
        lines = [f"📺 <b>{len(self.monitors)} Monitör</b>\n"]
        for m in self.monitors:
            star = ' 🌟' if m['is_primary'] else ''
            lines.append(f"  {m['id']+1}. {m['name']}{star} — {m['width']}×{m['height']}")
        return '\n'.join(lines)

    def selection_keyboard(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton("📺 Tüm Ekranlar", callback_data="ss_all"))
        btns = [
            InlineKeyboardButton(
                f"{'🌟' if m['is_primary'] else '📺'} Ekran {m['id']+1}",
                callback_data=f"ss_monitor_{m['id']}"
            )
            for m in self.monitors
        ]
        for i in range(0, len(btns), 2):
            kb.add(*btns[i:i+2])
        return kb


# ══════════════════════════════════════════════════════════════════════════════
# GÜVENLİK MODU  (Bug fix: _listeners_active flag)
# ══════════════════════════════════════════════════════════════════════════════

class SecurityMode:
    """
    Hareket algılama ve otomatik kayıt.

    Kritik düzeltme: Önceki sürümde load_state() self.enabled=True atayıp
    start() çağırıyordu, start() ise if self.enabled: return ile hemen
    dönüyordu → listener'lar hiç başlamıyordu.

    Çözüm: Listener yaşam döngüsü _listeners_active bayrağıyla takip edilir,
    _load_state() doğrudan _start_listeners() çağırır.
    """

    def __init__(self, bot_manager):
        self.bot_manager = bot_manager
        self.logger      = bot_manager.logger
        self.settings    = bot_manager.settings

        self.enabled           = False
        self._listeners_active = False
        self.recording         = False
        self._recording_lock   = threading.Lock()
        self.last_recording_time = 0.0

        self._mouse_listener    = None
        self._keyboard_listener = None

        self._last_mouse_pos: Optional[Tuple[int, int]] = None
        self._accumulated_dist = 0.0

        self.mouse_movements = 0
        self.key_presses     = 0

        self._load_state()

    def _load_state(self):
        try:
            data = self.bot_manager.store.get_security()
            if data.get('enabled', False):
                self.enabled = True
                self._start_listeners()
        except Exception as e:
            self.logger.error(f"Güvenlik durumu yüklenemedi: {e}")

    def _save_state(self):
        try:
            self.bot_manager.store.set_security(self.enabled)
        except Exception as e:
            self.logger.error(f"Güvenlik durumu kaydedilemedi: {e}")

    def start(self) -> bool:
        if self.enabled:
            return False
        self.enabled = True
        self._save_state()
        self._start_listeners()
        self.logger.info("🔐 Güvenlik modu AÇIK")
        self.bot_manager.send_notification(
            f"🔐 <b>Güvenlik Modu Aktif</b>\n"
            f"{self.bot_manager.identity.display_name()}\n\n"
            f"Hareket algılandığında:\n"
            f"📸 Anlık fotoğraf → 🎥 {Config.SECURITY_VIDEO_DURATION}s video"
        )
        return True

    def stop(self) -> bool:
        if not self.enabled:
            return False
        self.enabled = False
        self._save_state()
        self._stop_listeners()
        self.logger.info("🔓 Güvenlik modu KAPALI")
        self.bot_manager.send_notification(
            f"🔓 <b>Güvenlik Modu Kapatıldı</b>\n"
            f"{self.bot_manager.identity.display_name()}"
        )
        return True

    def toggle(self) -> bool:
        self.stop() if self.enabled else self.start()
        return self.enabled

    def _start_listeners(self):
        if self._listeners_active:
            return
        self._listeners_active = True
        self._accumulated_dist = 0.0
        self._last_mouse_pos   = None

        from pynput import mouse, keyboard
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press
        )
        self._mouse_listener.start()
        self._keyboard_listener.start()
        self.logger.info("Güvenlik listener'ları başlatıldı")

    def _stop_listeners(self):
        if not self._listeners_active:
            return
        self._listeners_active = False
        if self._mouse_listener:
            try: self._mouse_listener.stop()
            except Exception: pass
        if self._keyboard_listener:
            try: self._keyboard_listener.stop()
            except Exception: pass
        self._mouse_listener    = None
        self._keyboard_listener = None
        self.logger.info("Güvenlik listener'ları durduruldu")

    def listeners_alive(self) -> bool:
        if not self.enabled:
            return True
        ml = self._mouse_listener    and getattr(self._mouse_listener,    'running', False)
        kl = self._keyboard_listener and getattr(self._keyboard_listener, 'running', False)
        return bool(ml and kl)

    def restart_listeners(self):
        self.logger.warning("Güvenlik listener'ları yeniden başlatılıyor...")
        self._listeners_active = False
        self._start_listeners()

    def _on_mouse_move(self, x, y):
        if not self.enabled:
            return
        if self._last_mouse_pos:
            dx = x - self._last_mouse_pos[0]
            dy = y - self._last_mouse_pos[1]
            self._accumulated_dist += (dx*dx + dy*dy) ** 0.5
        self._last_mouse_pos = (x, y)
        self.mouse_movements += 1

        if self._accumulated_dist >= Config.SECURITY_MOUSE_THRESHOLD:
            self._accumulated_dist = 0.0
            self._trigger("mouse hareketi")

    def _on_mouse_click(self, x, y, button, pressed):
        if not self.enabled or not pressed:
            return
        self._trigger("mouse tıklaması")

    def _on_key_press(self, key):
        if not self.enabled:
            return
        self.key_presses += 1
        self._trigger("klavye basımı")

    def _trigger(self, trigger_type: str):
        with self._recording_lock:
            if self.recording:
                return
            if time.time() - self.last_recording_time < Config.SECURITY_COOLDOWN:
                return
            if self.settings.is_quiet_time():
                self.settings.log_quiet_event(f"Güvenlik tetiklendi: {trigger_type}")
                return
            self.recording = True
            self.last_recording_time = time.time()
        self.logger.warning(f"⚠️ Güvenlik tetiklendi: {trigger_type}")

        self.bot_manager.send_notification(
            f"⚠️ <b>Hareket Algılandı!</b>\n"
            f"{self.bot_manager.identity.display_name()}\n\n"
            f"🔍 {trigger_type}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"📸 Anlık fotoğraf gönderiliyor..."
        )
        threading.Thread(target=self._record_sequence,
                         args=(trigger_type,), daemon=True).start()

    def _record_sequence(self, trigger_type: str):
        """1) Anlık screenshot gönder  2) Video kaydet ve gönder"""
        try:
            try:
                ss = self.bot_manager.monitor_manager.capture_all()
                self.bot_manager._send_photo(
                    self.bot_manager.store.owner_id, ss,
                    f"📸 <b>Anlık Fotoğraf</b>\n"
                    f"{self.bot_manager.identity.display_name()}\n"
                    f"🔍 {trigger_type} — {datetime.now().strftime('%H:%M:%S')}"
                )
            except Exception as e:
                self.logger.error(f"Güvenlik screenshot hatası: {e}")

            video_path = self.bot_manager.video_recorder.record_screen(
                duration=Config.SECURITY_VIDEO_DURATION
            )
            if video_path:
                with open(video_path, 'rb') as f:
                    self.bot_manager.bot.send_video(
                        self.bot_manager.store.owner_id, f,
                        caption=(
                            f"🔐 <b>Güvenlik Kaydı</b>\n"
                            f"{self.bot_manager.identity.display_name()}\n"
                            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        ),
                        parse_mode='HTML',
                        timeout=120
                    )
                try: os.remove(video_path)
                except Exception: pass
                self.logger.info("Güvenlik kaydı gönderildi")
            else:
                self.bot_manager.send_notification("❌ Güvenlik videosu kaydedilemedi")

        except Exception as e:
            self.logger.error(f"Güvenlik kayıt hatası: {e}")
        finally:
            self.recording = False

    def status_text(self) -> str:
        if not self.enabled:
            return "🔓 Güvenlik Modu: <b>KAPALI</b>"

        s = "🔐 Güvenlik Modu: <b>AÇIK</b>\n"
        if self.recording:
            s += "🎥 Kayıt yapılıyor...\n"
        else:
            remaining = max(0, Config.SECURITY_COOLDOWN -
                            (time.time() - self.last_recording_time))
            s += f"⏳ Bekleme: {int(remaining)}s\n" if remaining else "✅ Hazır\n"

        s += f"🖱️ Mouse: {self.mouse_movements} hareket\n"
        s += f"⌨️ Klavye: {self.key_presses} tuş"

        if self.settings.is_quiet_time():
            s += (f"\n\n🌙 Sessiz Saatler aktif "
                  f"({Config.QUIET_HOURS_START:02d}:00–{Config.QUIET_HOURS_END:02d}:00)")
        return s


# ══════════════════════════════════════════════════════════════════════════════
# WATCHDOG
# ══════════════════════════════════════════════════════════════════════════════

class WatchdogManager:
    """Kritik thread'leri izler; ölürse restart fonksiyonunu çağırır."""

    def __init__(self, logger: LogManager):
        self.logger   = logger
        self._watches: Dict[str, Dict] = {}

    def register(self, name: str, thread: threading.Thread, restart_fn):
        self._watches[name] = {'thread': thread, 'restart': restart_fn}

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True, name='watchdog')
        t.start()
        self.logger.info("Watchdog başlatıldı")

    def _loop(self):
        while True:
            time.sleep(30)
            for name, entry in list(self._watches.items()):
                if not entry['thread'].is_alive():
                    self.logger.warning(f"⚠️ Watchdog: '{name}' thread'i öldü, restart...")
                    try:
                        new_thread = entry['restart']()
                        entry['thread'] = new_thread
                    except Exception as e:
                        self.logger.error(f"Watchdog restart hatası ({name}): {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SİSTEM İZLEYİCİ (Pil, USB, Kullanıcı, Günlük Rapor, Aktif Pencere)
# ══════════════════════════════════════════════════════════════════════════════

class SystemMonitor:
    def __init__(self, bot_manager):
        self.bot_manager = bot_manager
        self.logger      = bot_manager.logger
        self.settings    = bot_manager.settings
        self.monitoring  = True

        self._last_battery_warning = 0.0
        self._last_user            = getpass.getuser()
        self._known_partitions: set = set()
        self._last_report_date     = None
        self._was_quiet            = self.settings.is_quiet_time()

        self._init_partitions()

    def _init_partitions(self):
        try:
            self._known_partitions = {p.device for p in psutil.disk_partitions()}
        except Exception:
            self._known_partitions = set()

    def start_monitoring(self) -> threading.Thread:
        t = threading.Thread(target=self._loop, daemon=True, name='monitor')
        t.start()
        self.logger.info("Sistem izleme başlatıldı")
        return t

    def _loop(self):
        while self.monitoring:
            try:
                self._check_battery()
                self._check_user_change()
                self._check_usb()
                self._check_daily_report()
                self._check_quiet_hours_end()
            except Exception as e:
                self.logger.error(f"İzleme döngüsü hatası: {e}")
            time.sleep(Config.CHECK_INTERVAL)

    def _check_battery(self):
        try:
            if not hasattr(psutil, 'sensors_battery'):
                return
            bat = psutil.sensors_battery()
            if not bat or bat.power_plugged:
                return
            if bat.percent <= Config.LOW_BATTERY_THRESHOLD:
                if self.settings.is_quiet_time():
                    self.settings.log_quiet_event(f"Düşük pil: %{bat.percent:.0f}")
                    return
                now = time.time()
                if now - self._last_battery_warning > 1800:
                    self.bot_manager.send_notification(
                        f"⚠️ <b>Düşük Pil</b>\n"
                        f"{self.bot_manager.identity.display_name()}\n\n"
                        f"🔋 {bat.percent}% — {self._fmt_time(bat.secsleft)}"
                    )
                    self._last_battery_warning = now
        except Exception:
            pass

    def _check_user_change(self):
        try:
            current = getpass.getuser()
            if current != self._last_user:
                self.bot_manager.send_notification(
                    f"👤 <b>Kullanıcı Değişti</b>\n"
                    f"{self.bot_manager.identity.display_name()}\n\n"
                    f"Önceki: {self._last_user}\n"
                    f"Şu an:  {current}"
                )
                self._last_user = current
        except Exception:
            pass

    def _check_usb(self):
        try:
            current      = {p.device for p in psutil.disk_partitions()}
            new_devs     = current - self._known_partitions
            removed_devs = self._known_partitions - current
            if self.settings.is_quiet_time():
                for dev in new_devs:
                    self.settings.log_quiet_event(f"USB takıldı: {dev}")
                for dev in removed_devs:
                    self.settings.log_quiet_event(f"USB çıkarıldı: {dev}")
                self._known_partitions = current
                return

            for dev in new_devs:
                self.logger.info(f"Yeni disk/USB: {dev}")
                self.bot_manager.send_notification(
                    f"🔌 <b>USB / Disk Takıldı</b>\n"
                    f"{self.bot_manager.identity.display_name()}\n\n"
                    f"📀 <code>{dev}</code>\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )

            for dev in removed_devs:
                self.logger.info(f"Disk/USB çıkarıldı: {dev}")
                self.bot_manager.send_notification(
                    f"⏏️ <b>USB / Disk Çıkarıldı</b>\n"
                    f"{self.bot_manager.identity.display_name()}\n\n"
                    f"📀 <code>{dev}</code>"
                )

            self._known_partitions = current
        except Exception:
            pass

    def _check_daily_report(self):
        now = datetime.now()
        if now.hour == Config.DAILY_REPORT_HOUR and now.date() != self._last_report_date:
            self._send_daily_report()
            self._last_report_date = now.date()

    def _send_daily_report(self):
        try:
            cpu  = psutil.cpu_percent(interval=1)
            ram  = psutil.virtual_memory()
            # Windows disk düzeltmesi
            drive = os.path.splitdrive(SCRIPT_DIR)[0] + '\\'
            try:
                disk = psutil.disk_usage(drive)
            except Exception:
                disk = psutil.disk_usage('/')
            uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())

            bat_line = ""
            if hasattr(psutil, 'sensors_battery'):
                bat = psutil.sensors_battery()
                if bat:
                    bat_line = f"🔋 Pil: {bat.percent}% {'🔌' if bat.power_plugged else ''}\n"

            sec = self.bot_manager.security_mode
            sec_line = "🔐 Güvenlik: AÇIK" if sec and sec.enabled else "🔓 Güvenlik: KAPALI"

            self.bot_manager.send_notification(
                f"📊 <b>Günlük Rapor — {datetime.now().strftime('%d.%m.%Y')}</b>\n"
                f"{self.bot_manager.identity.display_name()}\n\n"
                f"🖥 CPU: {cpu}%\n"
                f"🧠 RAM: {ram.used/(1024**3):.1f}/{ram.total/(1024**3):.1f}GB ({ram.percent}%)\n"
                f"💾 Disk: {disk.used/(1024**3):.1f}/{disk.total/(1024**3):.1f}GB ({disk.percent}%)\n"
                f"{bat_line}"
                f"⏱ Uptime: {str(uptime).split('.')[0]}\n"
                f"{sec_line}"
            )
            self.logger.info("Günlük rapor gönderildi")
        except Exception as e:
            self.logger.error(f"Günlük rapor hatası: {e}")

    def get_active_window(self) -> str:
        try:
            sys_name = platform.system()

            if sys_name == 'Windows':
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()

                buf = ctypes.create_unicode_buffer(512)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
                title = buf.value or "(Başlıksız)"

                pid_val = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
                try:
                    proc = psutil.Process(pid_val.value)
                    proc_name = proc.name()
                    proc_path = proc.exe()
                except Exception:
                    proc_name, proc_path = "Bilinmiyor", ""

                return (
                    f"🖥️ <b>Aktif Pencere</b>\n\n"
                    f"📝 Başlık: <code>{title}</code>\n"
                    f"⚙️ Uygulama: {proc_name}\n"
                    f"📂 <code>{proc_path}</code>"
                )

            elif sys_name == 'Linux':
                result = subprocess.run(
                    ['xdotool', 'getactivewindow', 'getwindowname'],
                    capture_output=True, text=True, timeout=3
                )
                title = result.stdout.strip() or "Alınamadı"
                return f"🖥️ <b>Aktif Pencere</b>\n\n📝 <code>{title}</code>"

            elif sys_name == 'Darwin':
                script = ('tell application "System Events" to get name '
                          'of first application process whose frontmost is true')
                result = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True, text=True, timeout=3
                )
                app = result.stdout.strip() or "Alınamadı"
                return f"🖥️ <b>Aktif Pencere</b>\n\n⚙️ {app}"

            return "⚠️ Desteklenmeyen platform"

        except Exception as e:
            return f"❌ Aktif pencere alınamadı: {e}"

    def _check_quiet_hours_end(self):
        is_quiet = self.settings.is_quiet_time()
        if self._was_quiet and not is_quiet:
            log = self.settings.pop_quiet_log()
            if log:
                self.bot_manager.send_notification(
                    f"🌅 <b>Sessiz Saatler Bitti — Özet</b>\n"
                    f"{self.bot_manager.identity.display_name()}\n\n"
                    f"{len(log)} olay bastırıldı:\n"
                    + "\n".join(f"• {e}" for e in log)
                )
        self._was_quiet = is_quiet

    def stop(self):
        self.monitoring = False

    @staticmethod
    def _fmt_time(seconds: int) -> str:
        if seconds < 0:
            return "Hesaplanamıyor"
        h, rem = divmod(seconds, 3600)
        m = rem // 60
        return f"{int(h)}s {int(m)}dk"


# ══════════════════════════════════════════════════════════════════════════════
# VIDEO KAYIT
# ══════════════════════════════════════════════════════════════════════════════

class VideoRecorder:
    def __init__(self, logger: LogManager):
        self.logger    = logger
        self.recording = False

    def record_screen(self, duration: int = None, fps: int = None) -> Optional[str]:
        if self.recording:
            self.logger.warning("Zaten bir kayıt devam ediyor")
            return None

        duration = duration or Config.VIDEO_DURATION
        fps      = fps      or Config.VIDEO_FPS

        try:
            self.recording = True
            import cv2
            import numpy as np

            # ── Ekran yakalayıcı seç: dxcam (GPU) → mss (CPU fallback) ────────
            _dxcam_cam  = None
            _sct_ctx    = None
            screen_size = None

            try:
                import dxcam as _dxcam
                _dxcam_cam = _dxcam.create(output_color="BGR")
                test_frame = _dxcam_cam.grab()
                if test_frame is None:
                    raise RuntimeError("test frame boş")
                h, w        = test_frame.shape[:2]
                screen_size = (w, h)
                self.logger.info("Ekran yakalama: dxcam (GPU)")
            except Exception as dx_err:
                self.logger.info(f"dxcam kullanılamıyor ({dx_err}), mss'e geçiliyor")
                if _dxcam_cam is not None:
                    try: del _dxcam_cam
                    except Exception: pass
                    _dxcam_cam = None

            if _dxcam_cam is None:
                import mss as mss_lib
                _sct_ctx    = mss_lib.mss()
                sct         = _sct_ctx.__enter__()
                monitor     = sct.monitors[0]
                screen_size = (monitor['width'], monitor['height'])
                self.logger.info("Ekran yakalama: mss (CPU)")

            # ── Çözünürlük ölçekleme ───────────────────────────────────────────
            scale = Config.VIDEO_RESOLUTION_SCALE
            if scale != 1.0:
                out_w = int(screen_size[0] * scale)
                out_h = int(screen_size[1] * scale)
                out_w = out_w if out_w % 2 == 0 else out_w - 1
                out_h = out_h if out_h % 2 == 0 else out_h - 1
                write_size = (out_w, out_h)
            else:
                write_size = screen_size

            # ── VideoWriter — codec dene, uzantıya göre temp dosya aç ─────────
            out    = None
            output = None
            for fourcc_str, ext, name in Config.VIDEO_CODECS:
                fd, candidate = tempfile.mkstemp(suffix=ext)
                os.close(fd)
                try:
                    fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
                    test   = cv2.VideoWriter(candidate, fourcc, fps, write_size, True)
                    if test.isOpened():
                        test.release()
                        out    = cv2.VideoWriter(candidate, fourcc, fps, write_size, True)
                        output = candidate
                        self.logger.info(f"Video codec: {name} ({ext})")
                        break
                    test.release()
                except Exception:
                    pass
                try: os.remove(candidate)
                except Exception: pass

            if not out or not out.isOpened():
                raise RuntimeError("Uygun video codec bulunamadı")

            # ── Kayıt döngüsü ──────────────────────────────────────────────────
            interval    = 1.0 / fps
            frame_count = int(duration * fps)

            if _dxcam_cam is not None:
                _dxcam_cam.start(target_fps=fps, video_mode=True)
                try:
                    for _ in range(frame_count):
                        t0    = time.time()
                        frame = _dxcam_cam.get_latest_frame()
                        if frame is None:
                            continue
                        if scale != 1.0:
                            frame = cv2.resize(frame, write_size)
                        out.write(frame)
                        time.sleep(max(0, interval - (time.time() - t0)))
                finally:
                    _dxcam_cam.stop()
                    del _dxcam_cam
            else:
                try:
                    for _ in range(frame_count):
                        t0    = time.time()
                        frame = cv2.cvtColor(
                            np.array(sct.grab(monitor)), cv2.COLOR_BGRA2BGR
                        )
                        if scale != 1.0:
                            frame = cv2.resize(frame, write_size)
                        out.write(frame)
                        time.sleep(max(0, interval - (time.time() - t0)))
                finally:
                    _sct_ctx.__exit__(None, None, None)

            out.release()
            size_mb = os.path.getsize(output) / (1024 * 1024)
            self.logger.info(f"Video kaydedildi: {size_mb:.2f} MB")
            return output

        except Exception as e:
            self.logger.error(f"Video kayıt hatası: {e}")
            if output:
                try: os.remove(output)
                except Exception: pass
            return None
        finally:
            self.recording = False


# ══════════════════════════════════════════════════════════════════════════════
# MİKROFON KAYIT
# ══════════════════════════════════════════════════════════════════════════════

class MicRecorder:
    """
    In-memory microphone recorder with energy-based VAD.
    - Captures via sounddevice (16 kHz mono int16)
    - Encodes to WAV in RAM using stdlib wave — no disk writes, no extra deps
    - VAD: skips chunks that are below RMS noise floor
    """

    SAMPLE_RATE   = 16000
    BLOCK_SIZE    = 1600     # callback block = 0.1 s  (low latency for stop)
    CHUNK_SECONDS = 30       # continuous-mode chunk length
    VAD_THRESHOLD = 0.16     # spectral speech-band energy ratio per frame
    VAD_MIN_RATIO = 0.28     # min fraction of frames detected as speech

    def __init__(self, logger: LogManager):
        self.logger     = logger
        self.last_error: Optional[str] = None
        self._lock      = threading.Lock()
        self._recording = False

    # ── public API ────────────────────────────────────────────────────────────

    def has_microphone(self) -> bool:
        try:
            import sounddevice as sd
            return any(d['max_input_channels'] > 0 for d in sd.query_devices())
        except Exception:
            return False

    def record(self, duration: int,
               stop_event: Optional[threading.Event] = None
               ) -> Optional[Tuple[io.BytesIO, bool]]:
        """
        Record up to *duration* seconds using a non-blocking InputStream.

        If *stop_event* is set mid-recording the capture stops early and
        whatever was collected so far is encoded + returned.

        Returns (wav_buf: BytesIO, is_silent: bool) on success, None on error.
        """
        with self._lock:
            if self._recording:
                self.last_error = "Already recording"
                return None
            self._recording = True

        try:
            import sounddevice as sd
            import numpy as np
            import wave
            import queue as _queue

            sr           = self.SAMPLE_RATE
            target       = int(duration * sr)
            audio_q: _queue.Queue = _queue.Queue()

            def _cb(indata, frames, time_info, status):
                audio_q.put(indata.copy())

            chunks: list = []
            collected    = 0

            self.logger.info(f"Mic recording: {duration}s")
            with sd.InputStream(samplerate=sr, channels=1, dtype='int16',
                                callback=_cb, blocksize=self.BLOCK_SIZE):
                while collected < target:
                    if stop_event and stop_event.is_set():
                        break
                    try:
                        data = audio_q.get(timeout=0.2)
                        chunks.append(data)
                        collected += len(data)
                    except _queue.Empty:
                        pass

            if not chunks:
                self.last_error = "No audio captured"
                return None

            audio = np.concatenate(chunks)

            # ── VAD: speech detection ────────────────────────────────────────
            is_silent = self._vad_check(audio.flatten(), sr)

            # ── Encode: Opus → FLAC → WAV ────────────────────────────────────
            buf = self._encode_opus(audio, sr)
            if buf:
                fmt = "OGG/Opus"
                buf.name = "mic.ogg"
            else:
                buf = self._encode_flac(audio, sr)
                if buf:
                    fmt = "FLAC"
                    buf.name = "mic.flac"
                else:
                    buf = self._encode_wav(audio, sr)
                    fmt = "WAV"
                    buf.name = "mic.wav"

            size_kb = buf.getbuffer().nbytes / 1024
            self.logger.info(f"Mic done: {size_kb:.1f} KB [{fmt}]  silent={is_silent}")
            self.last_error = None
            return buf, is_silent

        except Exception as e:
            self.last_error = str(e) or repr(e) or type(e).__name__
            self.logger.error(f"Mic error: {self.last_error}")
            return None
        finally:
            with self._lock:
                self._recording = False

    # ── VAD ───────────────────────────────────────────────────────────────────

    def _vad_check(self, audio_flat: 'np.ndarray', sr: int) -> bool:
        """
        Returns True (silent / no speech) or False (speech detected).

        Priority:
          1. webrtcvad  — most accurate, needs C extension (Python ≤ 3.11)
          2. Spectral   — FFT speech-band analysis via numpy (always available)
        """
        # ── 1. webrtcvad ─────────────────────────────────────────────────────
        try:
            import webrtcvad
            import numpy as np

            vad        = webrtcvad.Vad(2)
            frame_size = int(sr * 20 / 1000)     # 20 ms → 320 samples @ 16 kHz
            frame_bytes = frame_size * 2

            raw = audio_flat.astype(np.int16).tobytes()
            speech = total = 0
            for i in range(0, len(raw) - frame_bytes + 1, frame_bytes):
                total += 1
                try:
                    if vad.is_speech(raw[i:i + frame_bytes], sr):
                        speech += 1
                except Exception:
                    pass

            if total == 0:
                return True
            ratio = speech / total
            self.logger.info(f"VAD (webrtc): {speech}/{total} frames  ({ratio:.1%})")
            return ratio < 0.08

        except ImportError:
            pass
        except Exception as e:
            self.logger.warning(f"webrtcvad error: {e}")

        # ── 2. Spectral VAD (numpy — no extra deps) ───────────────────────────
        # Speech energy is concentrated in 300–3400 Hz.
        # Keyboard clicks / sniffing are broadband or low-freq — won't dominate
        # the speech band across many consecutive frames.
        try:
            import numpy as np

            frame_size = int(sr * 20 / 1000)     # 320 samples per frame
            freqs      = np.fft.rfftfreq(frame_size, 1.0 / sr)
            sp_mask    = (freqs >= 300) & (freqs <= 3400)

            speech = total = 0
            samples = audio_flat.astype(np.float32)

            for i in range(0, len(samples) - frame_size + 1, frame_size):
                frame = samples[i:i + frame_size]

                # skip truly silent frames (below noise floor)
                rms = np.sqrt(np.mean(frame ** 2)) / 32768.0
                if rms < 0.004:
                    total += 1
                    continue

                fft          = np.abs(np.fft.rfft(frame)) ** 2
                total_e      = fft.sum() + 1e-10
                speech_ratio = fft[sp_mask].sum() / total_e

                total += 1
                if speech_ratio > 0.30:      # speech band dominant
                    speech += 1

            if total == 0:
                return True
            ratio = speech / total
            self.logger.info(f"VAD (spectral): {speech}/{total} frames ({ratio:.1%})")
            return ratio < 0.08

        except Exception as e:
            self.logger.warning(f"Spectral VAD error: {e}")

        # ── 3. Energy fallback (last resort) ─────────────────────────────────
        import numpy as np
        flat    = audio_flat.astype(np.float32) / 32768.0
        n_above = int(np.sum(np.abs(flat) > self.VAD_THRESHOLD))
        ratio   = n_above / max(len(flat), 1)
        self.logger.info(f"VAD (energy): {ratio:.1%} above threshold")
        return ratio < self.VAD_MIN_RATIO

    # ── encoders ──────────────────────────────────────────────────────────────

    def _encode_flac(self, audio: 'np.ndarray', sr: int) -> Optional[io.BytesIO]:
        """Encode to FLAC via soundfile. ~55% smaller than WAV, lossless, no extra deps."""
        try:
            import soundfile as sf
            import numpy as np
            buf = io.BytesIO()
            sf.write(buf, audio.flatten().astype(np.float32) / 32768.0,
                     sr, format='FLAC')
            buf.seek(0)
            return buf
        except Exception as e:
            self.logger.warning(f"FLAC encoding failed, falling back to WAV: {e}")
            return None

    def _encode_opus(self, audio: 'np.ndarray', sr: int) -> Optional[io.BytesIO]:
        """Encode int16 numpy array to OGG/Opus via pyogg. Returns None if unavailable."""
        try:
            # Pre-load pyogg's bundled DLLs before pyogg does its own ctypes search.
            # On Python 3.14 the DLL search path changed; loading them explicitly
            # puts them in the process cache so pyogg's LoadLibrary("opus") succeeds.
            import importlib.util as _ilu, ctypes as _ct, sys as _sys
            if 'pyogg' not in _sys.modules:
                _spec = _ilu.find_spec('pyogg')
                if _spec:
                    import os as _os
                    _pkg = _os.path.dirname(_spec.origin)
                    _os.add_dll_directory(_pkg)
                    for _dll in ('libogg.dll', 'opus.dll', 'opusenc.dll', 'opusfile.dll'):
                        _p = _os.path.join(_pkg, _dll)
                        if _os.path.exists(_p):
                            try: _ct.CDLL(_p)
                            except Exception: pass

            import pyogg                                    # pip install pyogg
            import numpy as np

            buf = io.BytesIO()
            encoder = pyogg.OpusBufferedEncoder()
            encoder.set_application("audio")
            encoder.set_sampling_frequency(sr)
            encoder.set_channels(1)
            encoder.set_bitrate(24000)                      # 24 kbps

            writer = pyogg.OggOpusWriter(buf, encoder)

            # Feed in 20 ms frames (320 samples @ 16 kHz)
            frame_bytes = 320 * 2                           # int16 = 2 bytes
            raw = audio.flatten().tobytes()
            for i in range(0, len(raw), frame_bytes):
                chunk = raw[i:i + frame_bytes]
                if len(chunk) < frame_bytes:               # pad last frame
                    chunk = chunk + b'\x00' * (frame_bytes - len(chunk))
                writer.write(memoryview(bytearray(chunk)))

            writer.close()
            buf.seek(0)
            return buf
        except ImportError:
            return None
        except Exception as e:
            self.logger.warning(f"Opus encoding failed, falling back to WAV: {e}")
            return None

    @staticmethod
    def _encode_wav(audio: 'np.ndarray', sr: int) -> io.BytesIO:
        """Encode int16 numpy array to in-memory WAV (stdlib, always available)."""
        import wave as _wave
        buf = io.BytesIO()
        with _wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(audio.tobytes())
        buf.seek(0)
        return buf


# ══════════════════════════════════════════════════════════════════════════════
# BİLGİSAYAR BİLGİ YÖNETİCİSİ
# ══════════════════════════════════════════════════════════════════════════════

class ComputerInfoManager:
    def __init__(self, identity: ComputerIdentity):
        self.identity = identity

    def get_info_text(self) -> str:
        cpu  = psutil.cpu_percent(interval=0.1)
        ram  = psutil.virtual_memory()
        # Windows disk düzeltmesi
        drive = os.path.splitdrive(SCRIPT_DIR)[0] + '\\'
        try:
            disk = psutil.disk_usage(drive)
        except Exception:
            disk = psutil.disk_usage('/')
        uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())

        bat_line = ""
        if hasattr(psutil, 'sensors_battery'):
            bat = psutil.sensors_battery()
            if bat:
                bat_line = f"🔋 Pil: {bat.percent}% {'🔌' if bat.power_plugged else ''}\n"

        return (
            f"{self.identity.display_name()}\n"
            f"🆔 <code>{self.identity.computer_id}</code>\n\n"
            f"🖥 CPU: {cpu}% ({psutil.cpu_count()} çekirdek)\n"
            f"🧠 RAM: {ram.used/(1024**3):.1f}/{ram.total/(1024**3):.1f} GB ({ram.percent}%)\n"
            f"💾 Disk: {disk.used/(1024**3):.1f}/{disk.total/(1024**3):.1f} GB ({disk.percent}%)\n"
            f"{bat_line}"
            f"⏱ Uptime: {str(uptime).split('.')[0]}\n"
            f"💻 {platform.platform()}\n"
            f"👤 {getpass.getuser()}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT YÖNETİCİSİ
# ══════════════════════════════════════════════════════════════════════════════

class TelegramBotManager:
    def __init__(self, store: PersistentStore):
        self.store      = store
        self.identity   = ComputerIdentity(store)
        self.logger     = LogManager(self.identity)
        self.settings   = SettingsManager(store)
        self.bot        = None
        self.connected  = False

        self.video_recorder  = VideoRecorder(self.logger)
        self.mic_recorder    = MicRecorder(self.logger)
        self.monitor_manager = MultiMonitorManager(self.logger)
        self.computer_info   = ComputerInfoManager(self.identity)

        self.security_mode:  Optional[SecurityMode]    = None
        self.system_monitor: Optional[SystemMonitor]   = None
        self.watchdog:       Optional[WatchdogManager] = None

        # /mic on/off sürekli kayıt durumu
        self._mic_stop_event = threading.Event()
        self._mic_continuous_active = False

        self._init_bot()

        if self.bot:
            self.security_mode = SecurityMode(self)

    # ── Bot bağlantısı ────────────────────────────────────────────────────────

    def _init_bot(self):
        for attempt in range(Config.MAX_RETRIES):
            try:
                self.bot = telebot.TeleBot(self.store.bot_token, parse_mode='HTML')
                self.bot.get_me()
                self.connected = True
                self.logger.info(f"Bot bağlandı — {self.identity.display_name()}")
                return
            except Exception as e:
                wait = Config.RETRY_DELAY * (attempt + 1)
                self.logger.error(f"Bot bağlantı hatası ({attempt+1}/{Config.MAX_RETRIES}): {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(wait)
        self.logger.error("Bot başlatılamadı — token ve internet bağlantısını kontrol edin")

    # ── Bildirim yardımcıları ─────────────────────────────────────────────────

    def send_notification(self, message: str) -> bool:
        for attempt in range(Config.MAX_RETRIES):
            try:
                self.bot.send_message(self.store.owner_id, message, parse_mode='HTML')
                return True
            except Exception as e:
                self.logger.error(f"Bildirim hatası ({attempt+1}): {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)
        return False

    def _send_photo(self, chat_id: int, image: Image.Image, caption: str):
        """PIL Image'ı JPEG olarak geçici dosya üzerinden Telegram'a gönder."""
        fd, temp = tempfile.mkstemp(suffix='.jpg')
        os.close(fd)
        try:
            image.save(temp, 'JPEG', quality=85, optimize=True)
            with open(temp, 'rb') as f:
                self.bot.send_photo(chat_id, f.read(), caption=caption, parse_mode='HTML')
        finally:
            try: os.remove(temp)
            except Exception: pass

    def send_startup_notification(self):
        self.send_notification(
            f"🟢 <b>Watchguard Bot v3.0 Aktif</b>\n\n"
            f"{self.computer_info.get_info_text()}\n\n"
            f"{self.monitor_manager.info_text()}\n\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"💡 /help — Tüm komutlar"
        )

    # ── Klavyeler ─────────────────────────────────────────────────────────────

    def _main_keyboard(self) -> InlineKeyboardMarkup:
        """Mevcut inline klavye (detaylı etkileşim için)."""
        sec_txt   = ("🔐 Güvenlik: AÇIK"  if self.security_mode and self.security_mode.enabled
                     else "🔓 Güvenlik: KAPALI")
        quiet_txt = ("🌙 Sessiz: AÇIK"   if self.settings.quiet_hours_enabled
                     else "🔔 Sessiz: KAPALI")

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("📸 Ekran Görüntüsü", callback_data="screenshot_menu"),
            InlineKeyboardButton("🎥 Video Kaydet",    callback_data="record"),
        )
        kb.add(
            InlineKeyboardButton("📊 Sistem Bilgisi",  callback_data="sysinfo"),
            InlineKeyboardButton("📋 İşlemler",        callback_data="processes"),
        )
        kb.add(
            InlineKeyboardButton("🖥️ Aktif Pencere",  callback_data="active_window"),
            InlineKeyboardButton("📺 Monitörler",      callback_data="monitors"),
        )
        kb.add(
            InlineKeyboardButton("📷 Kamera",          callback_data="camera"),
            InlineKeyboardButton("🎙️ Mikrofon",        callback_data="mic"),
        )
        kb.add(
            InlineKeyboardButton("🔒 Kilitle",         callback_data="lock"),
        )
        kb.add(
            InlineKeyboardButton(sec_txt,              callback_data="security_toggle"),
            InlineKeyboardButton(quiet_txt,            callback_data="quiet_toggle"),
        )
        kb.add(
            InlineKeyboardButton("🔄 Yeniden Başlat",  callback_data="restart"),
            InlineKeyboardButton("⚠️ Kapat",           callback_data="shutdown"),
        )
        return kb

    def _reply_keyboard(self) -> ReplyKeyboardMarkup:
        """Kalıcı hızlı erişim klavyesi."""
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        kb.add(
            KeyboardButton('/ss 📸'),
            KeyboardButton('/rec 🎥'),
            KeyboardButton('/myinfo 📊'),
        )
        kb.add(
            KeyboardButton('/processes 📋'),
            KeyboardButton('/window 🖥️'),
            KeyboardButton('/monitors 📺'),
        )
        kb.add(
            KeyboardButton('/mic 🎙️'),
            KeyboardButton('/security 🔐'),
            KeyboardButton('/quiethours 🌙'),
        )
        kb.add(
            KeyboardButton('/lock 🔒'),
            KeyboardButton('/restart 🔄'),
            KeyboardButton('/ping 🏓'),
        )
        kb.add(
            KeyboardButton('/computers 💻'),
            KeyboardButton('/update ⬆️'),
            KeyboardButton('/help ❓'),
        )
        return kb

    def _setup_bot_commands(self):
        """BotFather menüsünü ayarla."""
        try:
            self.bot.set_my_commands([
                BotCommand('computers',  'Bilgisayarları listele / seç'),
                BotCommand('ping',       'Tüm bilgisayarları pinle'),
                BotCommand('ss',         'Ekran görüntüsü'),
                BotCommand('rec',        'Video kaydet'),
                BotCommand('myinfo',     'Sistem bilgileri'),
                BotCommand('processes',  'İşlem listesi'),
                BotCommand('security',   'Güvenlik modunu aç/kapa'),
                BotCommand('quiethours', 'Sessiz saatleri aç/kapa'),
                BotCommand('shell',      'Komut çalıştır'),
                BotCommand('mic',        'Mikrofon: /mic 30 | /mic 2m | /mic on | /mic off'),
                BotCommand('msg',        'Mesaj gönder ve yanıt al'),
                BotCommand('window',     'Aktif pencere'),
                BotCommand('monitors',   'Monitör listesi'),
                BotCommand('killps',     'İşlem sonlandır'),
                BotCommand('lock',       'Ekranı kilitle'),
                BotCommand('logs',       'Son logları göster: /logs veya /logs 50'),
                BotCommand('clearlog',   'Log geçmişini temizle'),
                BotCommand('update',     'GitHub\'tan en son sürümü indir ve uygula'),
                BotCommand('restart',    'Yeniden başlat'),
                BotCommand('shutdown',   'Kapat'),
                BotCommand('help',       'Yardım'),
            ])
        except Exception as e:
            self.logger.warning(f"Bot komutları ayarlanamadı: {e}")

    # ── Handler kurulumu ──────────────────────────────────────────────────────

    def setup_handlers(self):
        bot = self.bot
        cfg = self.store
        identity = self.identity

        def owner(fn):
            """
            Sadece OWNER_ID'den gelen mesajları işle.
            is_selected False ise komutları sessizce yoksay.
            """
            def wrapper(msg):
                if msg.from_user.id != cfg.owner_id:
                    return
                if not self.settings.get('is_selected'):
                    return
                fn(msg)
            return wrapper

        # ── /computers ────────────────────────────────────────────────────────
        # is_selected kontrolü YOK — tüm bilgisayarlar yanıt verir
        @bot.message_handler(commands=['computers'])
        def cmd_computers(msg):
            if msg.from_user.id != cfg.owner_id:
                return
            try:
                selected = self.settings.get('is_selected')
                sel_icon = "✅" if selected else "⬜"
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(
                    f"{sel_icon} Seç — {identity.computer_name}",
                    callback_data=f"select_{identity.computer_id}"
                ))
                bot.send_message(
                    msg.chat.id,
                    f"{identity.display_name()}\n"
                    f"<code>{identity.computer_id}</code>\n"
                    f"Durum: {sel_icon} {'Seçili' if selected else 'Seçili değil'}",
                    reply_markup=kb
                )
            except Exception as e:
                self.logger.error(f"/computers hatası: {e}", exc_info=True)
                bot.send_message(msg.chat.id, f"❌ Hata: {e}")

        # ── /ping ─────────────────────────────────────────────────────────────
        # is_selected kontrolü YOK — tüm bilgisayarlar yanıt verir
        @bot.message_handler(commands=['ping'])
        def cmd_ping(msg):
            if msg.from_user.id != cfg.owner_id:
                return
            # Mesajın Telegram'dan bu bota ulaşma gecikmesi
            latency_ms = int((time.time() - msg.date) * 1000)
            selected = self.settings.get('is_selected')
            sel_icon = "✅" if selected else "⬜"
            try:
                bot.send_message(
                    msg.chat.id,
                    f"🏓 {identity.display_name()} {sel_icon} — {latency_ms}ms"
                )
            except Exception as e:
                self.logger.error(f"Ping hatası: {e}")

        # ── /start /help ──────────────────────────────────────────────────────
        @bot.message_handler(commands=['start', 'help'])
        @owner
        def cmd_help(msg):
            pin_status = "✅ PIN korumalı" if cfg.shell_pin else "⚠️ PIN yok"
            shell_ex   = (
                "<code>/shell SIFRE komut</code>" if cfg.shell_pin
                else "<code>/shell komut</code>"
            )
            bot.send_message(msg.chat.id, (
                f"🤖 <b>Watchguard v3.0</b>\n"
                f"📍 {identity.display_name()}\n"
                "\n"
                "─────────────────────────\n"
                "💻 <b>BİLGİSAYAR YÖNETİMİ</b>\n"
                "/computers — Tüm bilgisayarları listele ve seç\n"
                "/ping      — Tüm bilgisayarları pinle (gecikme + seçim durumu)\n"
                "\n"
                "📷 <b>GÖRÜNTÜ</b>\n"
                "/ss             — Tüm monitörlerin ekran görüntüsü\n"
                f"/rec            — {Config.VIDEO_DURATION}s ekran videosu kaydı\n"
                "/monitors       — Bağlı monitörleri listele\n"
                "\n"
                "🖥️ <b>SİSTEM</b>\n"
                "/myinfo         — CPU, RAM, disk, pil, uptime\n"
                "/window         — Şu an aktif pencere başlığı\n"
                "/processes      — CPU+RAM'e göre top 20 işlem\n"
                "/killps &lt;PID&gt;  — İşlemi PID ile sonlandır\n"
                "\n"
                "🎙️ <b>MİKROFON</b>\n"
                f"/mic            — Tek kayıt ({Config.MIC_DURATION}s varsayılan)\n"
                "/mic &lt;süre&gt;    — Özel süre: <code>/mic 30</code> veya <code>/mic 2m</code>\n"
                "/mic on         — Sürekli kayıt (30s döngü, VAD aktif — sessizlik atlanır)\n"
                "/mic off        — Sürekli kaydı durdur\n"
                "\n"
                "⚙️ <b>UZAKTAN KONTROL</b>\n"
                f"/shell          — Kabuk komutu çalıştır [{pin_status}]\n"
                f"  Kullanım: {shell_ex}\n"
                "  Örnek: <code>dir</code> · <code>ipconfig</code> · <code>tasklist</code>\n"
                "/msg &lt;metin&gt;   — Ekranda mesaj kutusu göster (yanıt alınabilir)\n"
                "/lock           — Ekranı kilitle\n"
                "/restart        — Bilgisayarı yeniden başlat (10s)\n"
                "/shutdown       — Bilgisayarı kapat (10s)\n"
                "\n"
                "🔐 <b>GÜVENLİK</b>\n"
                "/security       — Hareket algılama modunu aç/kapa\n"
                f"/quiethours     — Sessiz saatleri aç/kapa\n"
                f"  ({Config.QUIET_HOURS_START:02d}:00–{Config.QUIET_HOURS_END:02d}:00 arası bildirim gönderilmez)\n"
                "\n"
                "📋 <b>LOG</b>\n"
                "/logs           — Son 30 log satırı\n"
                "/logs &lt;n&gt;       — Son n satır (maks 200)\n"
                "/clearlog       — Log geçmişini temizle\n"
                "\n"
                "🔄 <b>GÜNCELLEME</b>\n"
                "/update         — GitHub'tan en son sürümü indir ve uygula\n"
                "─────────────────────────"
            ), reply_markup=self._reply_keyboard())

        # ── /security ─────────────────────────────────────────────────────────
        @bot.message_handler(commands=['security'])
        @owner
        def cmd_security(msg):
            state  = self.security_mode.toggle()
            status = "AÇIK 🔐" if state else "KAPALI 🔓"
            bot.send_message(msg.chat.id,
                f"<b>Güvenlik Modu: {status}</b>\n\n{self.security_mode.status_text()}")

        # ── /quiethours ───────────────────────────────────────────────────────
        @bot.message_handler(commands=['quiethours'])
        @owner
        def cmd_quiet(msg):
            enabled = self.settings.toggle('quiet_hours_enabled')
            state   = "AÇIK 🌙" if enabled else "KAPALI 🔔"
            bot.send_message(msg.chat.id,
                f"🌙 <b>Sessiz Saatler: {state}</b>\n\n"
                f"Aralık: {Config.QUIET_HOURS_START:02d}:00 – "
                f"{Config.QUIET_HOURS_END:02d}:00\n"
                f"Şu an: {datetime.now().strftime('%H:%M')}\n\n"
                + ("⚠️ Bu saatler arasında güvenlik bildirimleri gönderilmez." if enabled
                   else "✅ Tüm bildirimler aktif."))

        # ── /window ───────────────────────────────────────────────────────────
        @bot.message_handler(commands=['window'])
        @owner
        def cmd_window(msg):
            bot.send_message(msg.chat.id, self.system_monitor.get_active_window())

        # ── /monitors ─────────────────────────────────────────────────────────
        @bot.message_handler(commands=['monitors'])
        @owner
        def cmd_monitors(msg):
            bot.send_message(msg.chat.id, self.monitor_manager.info_text())

        # ── /myinfo ───────────────────────────────────────────────────────────
        @bot.message_handler(commands=['myinfo'])
        @owner
        def cmd_myinfo(msg):
            bot.send_message(msg.chat.id,
                f"💻 <b>Sistem Bilgileri</b>\n\n"
                f"{self.computer_info.get_info_text()}\n\n"
                f"{self.monitor_manager.info_text()}\n\n"
                f"{self.security_mode.status_text()}")

        # ── /ss ───────────────────────────────────────────────────────────────
        @bot.message_handler(commands=['ss'])
        @owner
        def cmd_ss(msg):
            self._handle_screenshot_all(msg.chat.id)

        # ── /rec ──────────────────────────────────────────────────────────────
        @bot.message_handler(commands=['rec'])
        @owner
        def cmd_rec(msg):
            self._handle_record(msg.chat.id)

        # ── /processes ────────────────────────────────────────────────────────
        @bot.message_handler(commands=['processes'])
        @owner
        def cmd_processes(msg):
            self._handle_processes(msg.chat.id)

        # ── /killps ───────────────────────────────────────────────────────────
        @bot.message_handler(commands=['killps'])
        @owner
        def cmd_killps(msg):
            self._handle_kill_process(msg)

        # ── /shell (eski /run) ────────────────────────────────────────────────
        @bot.message_handler(commands=['shell'])
        @owner
        def cmd_shell(msg):
            parts = msg.text.split(maxsplit=1)
            if len(parts) < 2:
                hint = ("/shell PASSWORD &lt;komut&gt;"
                        if cfg.shell_pin else "/shell &lt;komut&gt;")
                bot.send_message(msg.chat.id, f"❓ Kullanım: {hint}")
                return

            arg = parts[1].strip()

            if cfg.shell_pin:
                pin_parts = arg.split(maxsplit=1)
                if len(pin_parts) < 2 or pin_parts[0] != str(cfg.shell_pin):
                    bot.send_message(msg.chat.id, "❌ Geçersiz PIN")
                    return
                arg = pin_parts[1]

            try:
                result = subprocess.run(
                    arg, shell=True, capture_output=True, text=True,
                    timeout=30, encoding='utf-8', errors='replace'
                )
                import html as _html
                raw = ((result.stdout or '') + (result.stderr or '')).strip()[:3000] or "(Çıktı yok)"
                output = _html.escape(raw)
                bot.send_message(msg.chat.id,
                    f"💻 <b>Komut</b>: <code>{_html.escape(arg)}</code>\n\n<pre>{output}</pre>")
            except subprocess.TimeoutExpired:
                bot.send_message(msg.chat.id, "⏱ Komut 30s'de tamamlanamadı")
            except Exception as e:
                bot.send_message(msg.chat.id, f"❌ {e}")

        # ── /mic ──────────────────────────────────────────────────────────────
        @bot.message_handler(commands=['mic'])
        @owner
        def cmd_mic(msg):
            parts = msg.text.split(maxsplit=1)
            dur = None
            if len(parts) > 1:
                arg = parts[1].strip().lower()

                # on/off sürekli mod
                if arg == 'on':
                    if self._mic_continuous_active:
                        bot.send_message(msg.chat.id,
                            "⚠️ Sürekli kayıt zaten aktif. Durdurmak için /mic off")
                        return
                    if not self.mic_recorder.has_microphone():
                        bot.send_message(msg.chat.id, "❌ Mikrofon bulunamadı")
                        return
                    self._mic_stop_event.clear()
                    self._mic_continuous_active = True
                    bot.send_message(msg.chat.id,
                        f"🎙️ Sürekli kayıt başlatıldı (30s döngü, VAD aktif)\n"
                        f"{identity.display_name()}\n"
                        f"Durdurmak için: /mic off")
                    threading.Thread(
                        target=self._handle_mic_continuous,
                        args=(msg.chat.id,), daemon=True
                    ).start()
                    return

                if arg == 'off':
                    if not self._mic_continuous_active:
                        bot.send_message(msg.chat.id, "⚠️ Sürekli kayıt aktif değil.")
                        return
                    self._mic_stop_event.set()
                    bot.send_message(msg.chat.id,
                        f"🛑 Sürekli kayıt durduruluyor...\n{identity.display_name()}")
                    return

                try:
                    if arg.endswith('m') or arg.endswith('dk'):
                        minutes = int(''.join(filter(str.isdigit, arg)))
                        dur = minutes * 60
                    else:
                        dur = int(arg)
                except ValueError:
                    bot.send_message(
                        msg.chat.id,
                        "❓ Kullanım: /mic [süre | on | off]\n"
                        "  <code>/mic</code>      — varsayılan (10s)\n"
                        "  <code>/mic 30</code>   — 30 saniye\n"
                        "  <code>/mic 2m</code>   — 2 dakika\n"
                        "  <code>/mic on</code>   — sürekli 1 dk'lık döngü\n"
                        "  <code>/mic off</code>  — sürekli kaydı durdur\n"
                        f"  Maksimum tek kayıt: {Config.MIC_MAX_DURATION // 60} dakika"
                    )
                    return
            self._handle_mic(msg.chat.id, dur)

        # ── /msg ──────────────────────────────────────────────────────────────
        @bot.message_handler(commands=['msg'])
        @owner
        def cmd_msg(msg):
            parts = msg.text.split(maxsplit=1)
            if len(parts) < 2:
                bot.send_message(msg.chat.id, "❓ Kullanım: /msg <metin>")
                return
            text = parts[1].strip()
            chat_id = msg.chat.id

            def show_dialog():
                import tkinter as tk
                root = tk.Tk()
                root.title(f"Watchguard — {identity.display_name()}")
                root.geometry("460x210")
                root.resizable(False, False)
                root.attributes('-topmost', True)
                root.after(500, lambda: root.attributes('-topmost', False))

                # Gelen mesaj
                tk.Label(root, text="📱 Telegram'dan mesaj:",
                         font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x', padx=12, pady=(12, 2))
                tk.Label(root, text=text, wraplength=436, justify='left',
                         font=('Segoe UI', 10), bg='#f0f0f0', relief='flat',
                         padx=8, pady=6).pack(fill='x', padx=12)

                # Yanıt alanı
                tk.Label(root, text="✏️ Yanıtınız (Enter = gönder, Esc = kapat):",
                         font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x', padx=12, pady=(10, 2))
                entry = tk.Entry(root, font=('Segoe UI', 10))
                entry.pack(fill='x', padx=12)
                entry.focus()

                reply_sent = [False]

                def send_reply(event=None):
                    reply = entry.get().strip()
                    if reply:
                        try:
                            bot.send_message(chat_id,
                                f"💬 <b>{identity.display_name()}</b>\n\n{reply}",
                                parse_mode='HTML')
                            reply_sent[0] = True
                        except Exception as e:
                            self.logger.error(f"/msg yanıt hatası: {e}")
                    root.destroy()

                def close(event=None):
                    root.destroy()

                btn_frame = tk.Frame(root)
                btn_frame.pack(pady=10)
                tk.Button(btn_frame, text="Gönder 📤", command=send_reply,
                          bg='#0078d4', fg='white', font=('Segoe UI', 9),
                          relief='flat', padx=12, pady=4).pack(side='left', padx=6)
                tk.Button(btn_frame, text="Kapat", command=close,
                          font=('Segoe UI', 9), relief='flat',
                          padx=12, pady=4).pack(side='left', padx=6)

                entry.bind('<Return>', send_reply)
                entry.bind('<Escape>', close)
                root.mainloop()

            threading.Thread(target=show_dialog, daemon=True).start()
            bot.send_message(msg.chat.id,
                f"💬 Mesaj iletildi — yanıt bekleniyor\n{identity.display_name()}")

        # ── /lock ─────────────────────────────────────────────────────────────
        @bot.message_handler(commands=['lock'])
        @owner
        def cmd_lock(msg):
            self._handle_lock(msg.chat.id)

        # ── /restart ──────────────────────────────────────────────────────────
        @bot.message_handler(commands=['restart'])
        @owner
        def cmd_restart(msg):
            self._handle_restart(msg.chat.id)

        # ── /shutdown ─────────────────────────────────────────────────────────
        @bot.message_handler(commands=['shutdown'])
        @owner
        def cmd_shutdown(msg):
            self._handle_shutdown(msg.chat.id)

        # ── /logs ─────────────────────────────────────────────────────────────
        @bot.message_handler(commands=['logs'])
        @owner
        def cmd_logs(msg):
            if not self.settings.get('is_selected'):
                return
            parts = msg.text.split(maxsplit=1)
            try:
                n = int(parts[1]) if len(parts) > 1 else 30
                n = max(1, min(n, Config.LOG_BUFFER_SIZE))
            except ValueError:
                n = 30
            lines = self.logger.get_lines(n)
            if not lines:
                bot.send_message(msg.chat.id, "📋 Log buffer boş.")
                return
            text = '\n'.join(lines)
            # Telegram mesaj limiti 4096 karakter
            for i in range(0, len(text), 4000):
                bot.send_message(msg.chat.id,
                    f"<pre>{text[i:i+4000]}</pre>")

        # ── /clearlog ─────────────────────────────────────────────────────────
        @bot.message_handler(commands=['clearlog'])
        @owner
        def cmd_clearlog(msg):
            if not self.settings.get('is_selected'):
                return
            self.logger.clear()
            bot.send_message(msg.chat.id,
                f"🗑️ Log geçmişi temizlendi — {identity.display_name()}")

        # ── /update ───────────────────────────────────────────────────────────
        @bot.message_handler(commands=['update'])
        @owner
        def cmd_update(msg):
            if not self.settings.get('is_selected'):
                return
            kb = InlineKeyboardMarkup()
            kb.row(
                InlineKeyboardButton("✅ Güncelle", callback_data="update_confirm"),
                InlineKeyboardButton("❌ İptal",    callback_data="update_cancel"),
            )
            bot.send_message(msg.chat.id,
                f"🔄 <b>Güncelleme</b> — {identity.display_name()}\n\n"
                f"GitHub'tan en son sürüm indirilip bot yeniden başlatılacak.\n"
                f"<code>{Config.GITHUB_RAW_URL}</code>",
                reply_markup=kb)

        # ── Callback handler ──────────────────────────────────────────────────
        @bot.callback_query_handler(func=lambda call: True)
        def callback_handler(call):
            if call.from_user.id != cfg.owner_id:
                return
            bot.answer_callback_query(call.id)
            cid  = call.message.chat.id
            mid  = call.message.message_id
            data = call.data

            # ── select_<computer_id> — tüm bilgisayarlar bu callback'i alır ──
            if data.startswith("select_"):
                target_id = data[len("select_"):]
                if identity.computer_id == target_id:
                    self.settings.set('is_selected', True)
                    bot.send_message(cid,
                        f"✅ {identity.display_name()} seçildi")
                else:
                    # Başka bir bilgisayar seçildi — bu bilgisayarı deseçe
                    self.settings.set('is_selected', False)
                return

            # Seçili olmayan bilgisayar inline butonları işlemez
            if not self.settings.get('is_selected'):
                return

            if data == "update_confirm":
                bot.edit_message_text(
                    f"🔄 Güncelleme başlatıldı — {identity.display_name()}\n"
                    "İndiriliyor...", cid, mid)
                threading.Thread(
                    target=self._handle_update,
                    args=(cid, mid), daemon=True
                ).start()
                return
            elif data == "update_cancel":
                bot.edit_message_text("❌ Güncelleme iptal edildi.", cid, mid)
                return

            if data == "screenshot_menu":
                bot.edit_message_text("📸 Hangi ekranı görüntülemek istersiniz?",
                                      cid, mid,
                                      reply_markup=self.monitor_manager.selection_keyboard())
            elif data == "ss_all":
                self._handle_screenshot_all(cid)
            elif data.startswith("ss_monitor_"):
                self._handle_screenshot_monitor(cid, int(data.split("_")[-1]))
            elif data == "security_toggle":
                self.security_mode.toggle()
                bot.edit_message_reply_markup(cid, mid, reply_markup=self._main_keyboard())
            elif data == "quiet_toggle":
                self.settings.toggle('quiet_hours_enabled')
                bot.edit_message_reply_markup(cid, mid, reply_markup=self._main_keyboard())
            elif data == "active_window":
                bot.send_message(cid, self.system_monitor.get_active_window())
            else:
                dispatch = {
                    'record':    self._handle_record,
                    'sysinfo':   self._handle_sysinfo,
                    'processes': self._handle_processes,
                    'monitors':  lambda cid: self.bot.send_message(cid, self.monitor_manager.info_text()),
                    'mic':       self._handle_mic,
                    'camera':    self._handle_camera,
                    'lock':      self._handle_lock,
                    'restart':   self._handle_restart,
                    'shutdown':  self._handle_shutdown,
                }
                handler = dispatch.get(data)
                if handler:
                    try:
                        handler(cid)
                    except Exception as e:
                        self.logger.error(f"Callback hatası ({data}): {e}")
                        bot.send_message(cid, f"❌ {e}")

        # ── Genel metin mesajı ────────────────────────────────────────────────
        @bot.message_handler(func=lambda m: True, content_types=['text'])
        @owner
        def handle_text(msg):
            text = msg.text.strip()
            if text.startswith('/'):
                bot.send_message(msg.chat.id, "❓ Bilinmeyen komut. /help ile yardım alın.")

    # ── İşlem handler'ları ────────────────────────────────────────────────────

    def _handle_screenshot_all(self, chat_id: int):
        try:
            ss = self.monitor_manager.capture_all()
            self._send_photo(chat_id, ss,
                f"📺 Tüm Ekranlar — {self.identity.display_name()}")
        except Exception as e:
            self.logger.error(f"Screenshot hatası: {e}")
            self.bot.send_message(chat_id, f"❌ {e}")

    def _handle_screenshot_monitor(self, chat_id: int, monitor_id: int):
        try:
            ss = self.monitor_manager.capture_one(monitor_id)
            if not ss:
                raise RuntimeError(f"Ekran {monitor_id+1} yakalanamadı")
            m = self.monitor_manager.monitors[monitor_id]
            self._send_photo(chat_id, ss,
                f"📺 {m['name']}\n{self.identity.display_name()}")
        except Exception as e:
            self.bot.send_message(chat_id, f"❌ {e}")

    def _handle_record(self, chat_id: int):
        self.bot.send_message(chat_id,
            f"🎥 Kayıt başlıyor ({Config.VIDEO_DURATION}s)...\n{self.identity.display_name()}")

        def do():
            path = self.video_recorder.record_screen()
            if path:
                try:
                    with open(path, 'rb') as f:
                        self.bot.send_video(
                            chat_id, f,
                            caption=self.identity.display_name(),
                            timeout=120   # büyük dosyalar için yeterli süre
                        )
                    os.remove(path)
                except Exception as e:
                    self.bot.send_message(chat_id, f"❌ Video gönderilemedi: {e}")
            else:
                self.bot.send_message(chat_id, "❌ Kayıt başarısız")

        threading.Thread(target=do, daemon=True).start()

    def _handle_sysinfo(self, chat_id: int):
        self.bot.send_message(chat_id,
            f"📊 <b>Sistem Bilgileri</b>\n\n"
            f"{self.computer_info.get_info_text()}\n\n"
            f"{self.security_mode.status_text()}")

    def _handle_processes(self, chat_id: int):
        try:
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    i = p.info
                    if i['cpu_percent'] > 0 or i['memory_percent'] > 0:
                        procs.append((i['cpu_percent'], i['pid'],
                                      i['name'], i['memory_percent']))
                except Exception:
                    continue

            procs.sort(reverse=True)
            lines = [
                f"<code>{pid}</code>: {name} (CPU:{cpu:.1f}% RAM:{ram:.1f}%)"
                for cpu, pid, name, ram in procs[:20]
            ]
            self.bot.send_message(chat_id,
                f"📋 <b>Top 20 İşlem</b> — {self.identity.display_name()}\n\n"
                + '\n'.join(lines)
                + "\n\n<code>/killps PID</code>")
        except Exception as e:
            self.bot.send_message(chat_id, f"❌ {e}")

    def _handle_camera(self, chat_id: int):
        try:
            import cv2
            self.bot.send_message(chat_id, "📷 Kamera açılıyor...")
            cam = cv2.VideoCapture(0)
            if not cam.isOpened():
                raise RuntimeError("Kamera açılamadı")
            ret, frame = False, None
            for _ in range(5):
                ret, frame = cam.read()
                if ret:
                    break
                time.sleep(0.3)
            cam.release()
            if not ret:
                raise RuntimeError("Görüntü alınamadı")

            fd, temp = tempfile.mkstemp(suffix='.jpg')
            os.close(fd)
            cv2.imwrite(temp, frame)
            with open(temp, 'rb') as f:
                self.bot.send_photo(chat_id, f.read(),
                                    caption=self.identity.display_name())
            try: os.remove(temp)
            except Exception: pass
        except Exception as e:
            self.bot.send_message(chat_id, f"❌ Kamera: {e}")

    def _handle_lock(self, chat_id: int):
        cmds = {
            'Windows': ['rundll32.exe', 'user32.dll,LockWorkStation'],
            'Linux':   ['bash', '-c', 'gnome-screensaver-command -l || loginctl lock-session'],
            'Darwin':  ['pmset', 'displaysleepnow'],
        }
        cmd = cmds.get(platform.system())
        if cmd:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            subprocess.Popen(cmd, creationflags=creationflags)
        self.bot.send_message(chat_id,
            f"🔒 Kilitlendi\n{self.identity.display_name()}")

    def _handle_restart(self, chat_id: int):
        self.bot.send_message(chat_id,
            f"🔄 10s içinde yeniden başlayacak...\n{self.identity.display_name()}")
        cmds = {
            'Windows': ['shutdown', '/r', '/t', '10'],
            'Linux':   ['shutdown', '-r', '+1'],
            'Darwin':  ['shutdown', '-r', '+1'],
        }
        cmd = cmds.get(platform.system())
        if cmd:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            subprocess.Popen(cmd, creationflags=creationflags)

    def _handle_shutdown(self, chat_id: int):
        self.bot.send_message(chat_id,
            f"⚠️ 10s içinde kapanacak...\n{self.identity.display_name()}")
        cmds = {
            'Windows': ['shutdown', '/s', '/t', '10'],
            'Linux':   ['shutdown', '-h', '+1'],
            'Darwin':  ['shutdown', '-h', '+1'],
        }
        cmd = cmds.get(platform.system())
        if cmd:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            subprocess.Popen(cmd, creationflags=creationflags)

    def _handle_update(self, chat_id: int, message_id: int):
        """GitHub'tan en son sürümü indir, obfüske et, yeniden başlat."""
        import urllib.request
        dest = os.path.abspath(__file__)
        tmp  = dest + '.tmp'
        try:
            # 1) İndir
            urllib.request.urlretrieve(Config.GITHUB_RAW_URL, tmp)

            # 2) Obfüske et
            with open(tmp, 'r', encoding='utf-8') as f:
                source = f.read()
            encoded = base64.b64encode(zlib.compress(source.encode('utf-8'))).decode('ascii')
            loader  = (
                "import zlib,base64;exec(zlib.decompress("
                f"base64.b64decode(b'{encoded}')).decode())"
            )
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(loader)

            # 3) Mevcut dosyanın üzerine yaz
            os.replace(tmp, dest)

            self.bot.edit_message_text(
                f"✅ Güncelleme tamamlandı — {self.identity.display_name()}\n"
                "Bot yeniden başlatılıyor...",
                chat_id, message_id)

            # 4) Yeniden başlat
            time.sleep(1)
            subprocess.Popen(
                [sys.executable, dest],
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            )
            sys.exit(0)

        except Exception as e:
            self.logger.error(f"Güncelleme hatası: {e}")
            try:
                os.remove(tmp)
            except Exception:
                pass
            self.bot.edit_message_text(
                f"❌ Güncelleme başarısız: {e}", chat_id, message_id)

    def _handle_kill_process(self, msg):
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            self.bot.send_message(msg.chat.id, "❓ Kullanım: /killps &lt;PID&gt;")
            return
        try:
            pid  = int(parts[1].strip())
            proc = psutil.Process(pid)
            name = proc.name()
            proc.kill()
            self.bot.send_message(msg.chat.id,
                f"✅ {name} (PID: {pid}) sonlandırıldı\n{self.identity.display_name()}")
        except ValueError:
            self.bot.send_message(msg.chat.id, "❌ Geçersiz PID")
        except psutil.NoSuchProcess:
            self.bot.send_message(msg.chat.id, "❌ İşlem bulunamadı")
        except psutil.AccessDenied:
            self.bot.send_message(msg.chat.id, "❌ Erişim reddedildi")
        except Exception as e:
            self.bot.send_message(msg.chat.id, f"❌ {e}")

    def _handle_mic(self, chat_id: int, duration: int = None):
        if not self.mic_recorder.has_microphone():
            self.bot.send_message(chat_id, "❌ Mikrofon bulunamadı")
            return

        dur = min(duration or Config.MIC_DURATION, Config.MIC_MAX_DURATION)
        status = self.bot.send_message(chat_id, f"🎙️ Kaydediliyor ({dur}s)...")

        def do():
            result = self.mic_recorder.record(dur)
            if result:
                buf, is_silent = result
                label = f"🎙️ {'[sessiz] ' if is_silent else ''}Mikrofon — {datetime.now().strftime('%H:%M:%S')}"
                try:
                    self.bot.delete_message(chat_id, status.message_id)
                    if getattr(buf, 'name', '').endswith('.ogg'):
                        self.bot.send_voice(chat_id, buf, duration=dur)
                    else:
                        self.bot.send_audio(chat_id, buf,
                                            title=label,
                                            performer=self.identity.display_name())
                except Exception as e:
                    self.bot.send_message(chat_id, f"❌ Ses gönderilemedi: {e}")
            else:
                err = self.mic_recorder.last_error or "Bilinmeyen hata"
                self.bot.edit_message_text(f"❌ Mikrofon: {err}", chat_id, status.message_id)

        threading.Thread(target=do, daemon=True).start()

    def _handle_mic_continuous(self, chat_id: int):
        """
        30 saniyelik VAD'lı sürekli kayıt döngüsü.
        stop_event record()'a geçirilir — /mic off anında etkili olur.
        """
        chunk   = MicRecorder.CHUNK_SECONDS
        segment = 0

        try:
            while not self._mic_stop_event.is_set():

                result = self.mic_recorder.record(chunk, stop_event=self._mic_stop_event)

                if self._mic_stop_event.is_set():
                    break

                if result is None:
                    err = self.mic_recorder.last_error or "Bilinmeyen hata"
                    self.logger.error(f"Mic continuous error: {err}")
                    self.bot.send_message(chat_id,
                        f"⚠️ Kayıt hatası: {err} — 3s sonra yeniden deneniyor")
                    time.sleep(3)
                    continue

                buf, is_silent = result
                self.logger.info(f"Mic chunk #{segment+1}: silent={is_silent} "
                                 f"size={buf.getbuffer().nbytes//1024}KB")

                if is_silent:
                    # sessiz chunk — atla ama logla
                    continue

                segment += 1
                try:
                    if getattr(buf, 'name', '').endswith('.ogg'):
                        self.bot.send_voice(chat_id, buf,
                                            duration=MicRecorder.CHUNK_SECONDS,
                                            timeout=60)
                    else:
                        buf.name = f"mic_{segment}.wav"
                        self.bot.send_audio(
                            chat_id, buf,
                            title=f"🎙️ #{segment} — {datetime.now().strftime('%H:%M:%S')}",
                            performer=self.identity.display_name(),
                            timeout=60
                        )
                except Exception as e:
                    self.logger.error(f"Mic send error: {e}")

        except Exception as e:
            self.logger.error(f"Mic continuous loop crashed: {e}")
            try:
                self.bot.send_message(chat_id, f"❌ Kayıt döngüsü çöktü: {e}")
            except Exception:
                pass

        finally:
            self._mic_continuous_active = False
            try:
                self.bot.send_message(
                    chat_id,
                    f"🛑 Kayıt durduruldu — {segment} segment gönderildi\n"
                    f"{self.identity.display_name()}"
                )
            except Exception:
                pass

    # ── Servisler ─────────────────────────────────────────────────────────────

    def start_polling(self) -> threading.Thread:
        def loop():
            while True:
                try:
                    self.logger.info("Bot polling başlatıldı")
                    self.bot.infinity_polling(timeout=30, long_polling_timeout=30)
                except Exception as e:
                    self.logger.error(f"Polling hatası: {e}")
                    time.sleep(Config.RETRY_DELAY)

        t = threading.Thread(target=loop, daemon=True, name='polling')
        t.start()
        return t


# ══════════════════════════════════════════════════════════════════════════════
# ANA UYGULAMA
# ══════════════════════════════════════════════════════════════════════════════

class WatchguardApp:
    def __init__(self):
        self._root = tk.Tk()
        self._root.withdraw()

        self.bot_manager    = TelegramBotManager(store)   # pass global store
        self.system_monitor = SystemMonitor(self.bot_manager)
        self.watchdog       = WatchdogManager(self.bot_manager.logger)

        # Cross-inject
        self.bot_manager.system_monitor = self.system_monitor
        self.bot_manager.watchdog       = self.watchdog

        log = self.bot_manager.logger
        log.info("=" * 60)
        log.info(f"Watchguard Bot v3.0 — {self.bot_manager.identity.display_name()}")
        log.info("=" * 60)

    def run(self):
        try:
            self.bot_manager.setup_handlers()
            self.bot_manager._setup_bot_commands()
            self.bot_manager.send_startup_notification()

            # Servisleri başlat
            polling_t = self.bot_manager.start_polling()
            monitor_t = self.system_monitor.start_monitoring()

            # Watchdog'a kaydet
            self.watchdog.register('polling', polling_t, self.bot_manager.start_polling)
            self.watchdog.register('monitor', monitor_t, self.system_monitor.start_monitoring)
            self.watchdog.start()

            self.bot_manager.logger.info("Tüm servisler aktif")

            # Ana loop: thread'lerin bitmesini bekle
            while True:
                time.sleep(60)

        except KeyboardInterrupt:
            self.bot_manager.logger.info("Durduruldu (KeyboardInterrupt)")
            self._shutdown()
        except Exception as e:
            self.bot_manager.logger.error(f"Kritik hata: {e}", exc_info=True)
            self._shutdown()

    def _shutdown(self):
        self.bot_manager.logger.info("Kapatılıyor...")
        try:
            self.system_monitor.stop()
            if self.bot_manager.security_mode:
                self.bot_manager.security_mode.stop()
            self.bot_manager.send_notification(
                f"🔴 Watchguard kapandı\n{self.bot_manager.identity.display_name()}"
            )
        except Exception:
            pass
        self.bot_manager.logger.info("Kapandı")


# ══════════════════════════════════════════════════════════════════════════════
# BAŞLATMA
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    try:
        WatchguardApp().run()
    except Exception as e:
        logging.basicConfig(filename=os.path.join(SCRIPT_DIR, 'watchguard_crash.log'))
        logging.error(f"Başlatma hatası: {e}", exc_info=True)
        sys.exit(1)
