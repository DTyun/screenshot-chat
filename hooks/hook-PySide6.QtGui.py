"""Collect desktop Qt plugins without unused PDF or virtual keyboard engines."""
from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

collect_plugins = pyside6_library_info.collect_plugins


def desktop_plugins(plugin_type):
    if plugin_type not in {'platforms','styles','imageformats','iconengines','tls'}:
        return []
    return [(source,destination) for source,destination in collect_plugins(plugin_type)
            if Path(source).name.lower() != 'qpdf.dll'
            and (plugin_type != 'platforms' or Path(source).name.lower() == 'qwindows.dll')]


pyside6_library_info.collect_plugins = desktop_plugins
hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
