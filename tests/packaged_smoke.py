"""Start the shipped executable twice and verify its single-instance activation pipe."""
import os
import subprocess
import time
import ctypes
from ctypes import wintypes
import uuid
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket

app = QCoreApplication([])
root = Path(__file__).resolve().parents[1]
exe = root / 'dist' / '截图聊天.exe'
data = root / 'artifacts' / 'test-data' / ('packaged-' + uuid.uuid4().hex[:8])
data.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, LOCALAPPDATA=str(data))
first = subprocess.Popen([str(exe), '--autostart'], env=env)
try:
    user32 = ctypes.WinDLL('user32')
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    for _ in range(400):
        if first.poll() is not None:
            raise AssertionError(f'Executable exited at startup: {first.returncode}')
        if (data / 'Pianyu' / 'history.db').exists():
            time.sleep(.5)
            break
        time.sleep(.1)
    hwnd = user32.FindWindowW(None, '截图聊天')
    assert not hwnd or not user32.IsWindowVisible(hwnd), 'Login startup should stay in tray'
    connected = False
    for _ in range(400):
        if first.poll() is not None:
            raise AssertionError(f'Executable exited at startup: {first.returncode}')
        sock = QLocalSocket()
        sock.connectToServer('PianyuScreenshot_1')
        if sock.waitForConnected(200):
            connected = True
            sock.disconnectFromServer()
            break
        sock.abort()
        time.sleep(.1)
    assert connected, 'Activation pipe never became ready'
    # The preceding pipe probe activates the window. Verify the process remains
    # responsive when a login-started instance is opened by a manual second run.
    second = subprocess.run([str(exe)], env=env, timeout=120)
    assert second.returncode == 0
    assert first.poll() is None
    for _ in range(30):
        hwnd = user32.FindWindowW(None, '截图聊天')
        if hwnd and user32.IsWindowVisible(hwnd):
            break
        time.sleep(.1)
    assert hwnd and user32.IsWindowVisible(hwnd), 'Second launch should restore the existing window'
    assert (data / 'Pianyu' / 'history.db').exists()
    log = data / 'Pianyu' / 'app.log'
    assert not log.exists() or not log.read_text().strip(), log.read_text()
    print('PASS: packaged EXE login startup stays in tray; second launch restores the existing window; database ready; no errors')
finally:
    subprocess.run(['taskkill', '/PID', str(first.pid), '/T', '/F'], capture_output=True)
