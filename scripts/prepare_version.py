"""Generate Windows file metadata from the application's single version source."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.version import APP_VERSION, APP_NAME, AUTHOR

root = Path(__file__).resolve().parents[1]
folder = root/'.release-build'
folder.mkdir(exist_ok=True)
version_tuple = tuple(map(int,APP_VERSION.split('.'))) + (0,)
content = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={version_tuple!r}, prodvers={version_tuple!r}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
  kids=[StringFileInfo([StringTable('080404B0',[
    StringStruct('CompanyName',{AUTHOR!r}),
    StringStruct('FileDescription',{APP_NAME!r}),
    StringStruct('FileVersion',{APP_VERSION!r}),
    StringStruct('ProductName',{APP_NAME!r}),
    StringStruct('ProductVersion',{APP_VERSION!r}),
    StringStruct('LegalCopyright','Copyright (c) 2026 yumi202607; MIT License'),
    StringStruct('OriginalFilename','截图聊天.exe')
  ])]),VarFileInfo([VarStruct('Translation',[2052,1200])])]
)'''
(folder/'version-info.txt').write_text(content,encoding='utf-8')
