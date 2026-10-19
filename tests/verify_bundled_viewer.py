"""Exercise the viewer bytecode shipped inside the executable without the app mutex."""
import sys
import types
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader
from PySide6.QtCore import QTemporaryDir, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QTest

archive = CArchiveReader(sys.argv[1])
pyz = archive.open_embedded_archive('PYZ.pyz')
module = types.ModuleType('bundled_viewer')
exec(pyz.extract('src.viewer'), module.__dict__)
app = QApplication([])
temporary = QTemporaryDir()
path = Path(temporary.path())/'viewer-test.png'
image = QImage(900,480,QImage.Format_RGB32)
image.fill(QColor('#248757'))
assert image.save(str(path))
viewer = module.ImageViewer(path)
viewer.show()
app.processEvents()
assert viewer.isVisible() and viewer.pixmap.toImage() == image
assert not viewer.findChildren(QPushButton)
assert viewer.windowFlags() & Qt.WindowCloseButtonHint
assert not viewer.windowFlags() & Qt.WindowMinMaxButtonsHint
QTest.keyClick(viewer,Qt.Key_Escape)
assert not viewer.isVisible()
print('Bundled viewer: original pixels, read-only display and close passed')
