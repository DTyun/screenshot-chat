"""Package the executable and license materials; never include local chat data."""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.version import APP_VERSION

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('executable',type=Path)
args = parser.parse_args()
output = root/'dist'/'release'/('v'+APP_VERSION)
output.mkdir(parents=True,exist_ok=True)
stem = f'ScreenshotChat-v{APP_VERSION}-win64'
exe = output/(stem+'.exe')
shutil.copyfile(args.executable,exe)
archive = output/(stem+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    z.write(exe,'截图聊天/截图聊天.exe')
    for name in ('LICENSE','THIRD_PARTY_NOTICES.md','README.md','CHANGELOG.md'):
        z.write(root/name,'截图聊天/'+name)
    for path in sorted((root/'licenses').rglob('*')):
        if path.is_file():
            z.write(path,'截图聊天/'+path.relative_to(root).as_posix())
for source in (root/'.release-build'/'thirdparty-sources').glob('*.tar.xz'):
    shutil.copyfile(source,output/source.name)
assets = sorted(p for p in output.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt')
(output/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in assets),encoding='utf-8')
print(output)
