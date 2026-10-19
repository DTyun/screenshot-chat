import ctypes
import subprocess
import sys
import winreg
from pathlib import Path
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtGui import QKeySequence


class Startup:
    """Per-user Windows login startup, changed only by Settings → Save."""
    key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
    value_name = '截图聊天'

    def __init__(self, key_path=None):
        if key_path is not None:
            self.key_path = key_path

    def command(self):
        if getattr(sys, 'frozen', False):
            args = [sys.executable, '--autostart']
        else:
            pythonw = Path(sys.executable).with_name('pythonw.exe')
            args = [str(pythonw if pythonw.exists() else sys.executable),
                    str(Path(__file__).resolve().parent.parent / 'main.py'), '--autostart']
        return subprocess.list2cmdline(args)

    def read(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_READ) as key:
                try:
                    return winreg.QueryValueEx(key, self.value_name)
                except FileNotFoundError:
                    return winreg.QueryValueEx(key, 'Pianyu')
        except FileNotFoundError:
            return None

    def restore(self, value):
        if value is None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_SET_VALUE) as key:
                    for name in (self.value_name, 'Pianyu'):
                        try:
                            winreg.DeleteValue(key, name)
                        except FileNotFoundError:
                            pass
            except FileNotFoundError:
                pass
        else:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self.value_name, 0, value[1], value[0])
                try:
                    winreg.DeleteValue(key, 'Pianyu')
                except FileNotFoundError:
                    pass

    def set_enabled(self, enabled):
        self.restore((self.command(), winreg.REG_SZ) if enabled else None)


def parse_hotkey(text):
    parts = text.upper().replace(' ', '').split('+')
    modifiers = {'ALT': 1, 'CTRL': 2, 'SHIFT': 4, 'META': 8, 'WIN': 8}
    flags = 0
    for part in parts[:-1]:
        if part not in modifiers:
            raise ValueError('请设置一个组合键，例如 Ctrl+Alt+A')
        flags |= modifiers[part]
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key)
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key in {'PRINT', 'PRINTSCREEN', 'PRTSC'}:
        vk = 0x2C
    else:
        raise ValueError('支持字母、数字、F1–F24 或 PrintScreen')
    if not flags and not (0x70 <= vk <= 0x87 or vk == 0x2C):
        raise ValueError('字母和数字必须搭配 Ctrl、Alt 或 Shift')
    return flags | 0x4000, vk


class HotkeyEvents(QObject):
    triggered = Signal()


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, app):
        super().__init__()
        self.events = HotkeyEvents()
        self.app = app
        self.current = None
        self.identifier = 0xA731
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.app.installNativeEventFilter(self)

    def set(self, text):
        new = parse_hotkey(text)
        if self.current and new == self.current[1]:
            return
        candidate = self.identifier + 1
        if not self.user32.RegisterHotKey(None, candidate, *new):
            raise ValueError('这个快捷键已被其他程序占用，请换一个组合键')
        if self.current:
            self.user32.UnregisterHotKey(None, self.identifier)
        self.identifier = candidate
        self.current = (text, new)

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam == self.identifier:
            self.events.triggered.emit()
            return True, 0
        return False, 0

    def close(self):
        if self.current:
            self.user32.UnregisterHotKey(None, self.identifier)
        self.app.removeNativeEventFilter(self)


class SingleInstance:
    def __init__(self, name='Global\\PianyuScreenshot_1'):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel = kernel
        self.handle = kernel.CreateMutexW(None, False, name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.is_primary = ctypes.get_last_error() != 183

    def close(self):
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
