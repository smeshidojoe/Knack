# -*- mode: python ; coding: utf-8 -*-

import importlib.util
import re

# --- версия ----------------------------------------------------------------- #
# Единственный источник — knack/core/constants.py. Отдельный version_info.txt не
# заводим: он дублировал бы ту же строку и однажды разошёлся бы с реальностью.
_APP_VERSION = re.search(
    r'APP_VERSION\s*=\s*"([^"]+)"',
    open('knack/core/constants.py', encoding='utf-8').read()).group(1)
_VER_TUPLE = tuple(int(x) for x in (_APP_VERSION.split('.') + ['0'] * 4)[:4])

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
    VarStruct, VSVersionInfo)

_VERSION_RES = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_VER_TUPLE, prodvers=_VER_TUPLE,
                      mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'SmeshidoJoe'),
            StringStruct('FileDescription', 'Knack'),
            StringStruct('FileVersion', _APP_VERSION),
            StringStruct('InternalName', 'Knack'),
            StringStruct('LegalCopyright', '© 2026 SmeshidoJoe'),
            StringStruct('OriginalFilename', 'Knack.exe'),
            StringStruct('ProductName', 'Knack'),
            StringStruct('ProductVersion', _APP_VERSION),
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ])

# --- необязательные зависимости --------------------------------------------- #
# Проекции WinRT и бэкенды перевода импортируются внутри функций, и анализатор
# PyInstaller их не находит — в сборке вкладка «Музыка» осталась бы пустой.
# Перечисляем руками.
_HIDDEN = [
    'winrt.runtime',
    'winrt.windows.media.control',
    'winrt.windows.storage.streams',
    'winrt.windows.foundation',
    'winrt.windows.foundation.collections',
]

# DeepL ходит через requests.
if importlib.util.find_spec('requests'):
    _HIDDEN.append('requests')

_DATAS = [('assets', 'assets')]
_BINARIES = []

# --- офлайн-переводчик -------------------------------------------------------- #
# Кладём в сборку: DeepL есть не у всех, а переводчик должен работать у каждого.
#
# Голый argostranslate тянет за собой spacy, stanza и torch — вместе почти
# полтора гигабайта, из них torch 1.2 ГБ. Ни один из трёх при переводе готовой
# моделью не работает: stanza и spacy нужны для разбиения на предложения (мы
# принудительно ставим minisbd через ARGOS_CHUNK_TYPE), torch с transformers —
# для конвертации чужих моделей, чего мы не делаем вовсе.
#
# Поэтому три пакета исключены, а вместо них подставляются пустые модули из
# pyi_hooks/stub_heavy_deps.py. Проверено: перевод en->ru работает.
BUNDLE_ARGOS = True

# В окружении разработчика обычно стоят и другие привязки Qt (PyQt5, PyQt6), а
# также matplotlib, который сам тянет их своими бэкендами. PyInstaller не умеет
# класть в сборку два набора привязок сразу и обрывает сборку. Ничего из этого
# нам не нужно — исключаем независимо от переводчика.
_EXCLUDES = [
    'PyQt5', 'PyQt6', 'PySide2', 'shiboken2',
    'matplotlib', 'tkinter', 'IPython', 'notebook', 'pytest',
]

if BUNDLE_ARGOS:
    if not importlib.util.find_spec('argostranslate'):
        raise SystemExit(
            'Нет argostranslate. Поставь: pip install -r requirements.txt '
            'или выключи BUNDLE_ARGOS в Knack.spec.')
    from PyInstaller.utils.hooks import collect_all
    for _package in ('argostranslate', 'ctranslate2', 'sentencepiece',
                     'sacremoses', 'minisbd'):
        if not importlib.util.find_spec(_package):
            continue
        _d, _b, _h = collect_all(_package)
        _DATAS += _d
        _BINARIES += _b
        _HIDDEN += _h
    # Всё это приезжает вместе с argostranslate и конвертерами ctranslate2, но
    # при переводе готовой моделью не участвует. Без исключений exe весил 232 МБ.
    _EXCLUDES += [
        'torch', 'torchvision', 'torchaudio', 'transformers',
        'spacy', 'thinc', 'stanza', 'spacy_legacy', 'spacy_loggers',
        'srsly', 'preshed', 'cymem', 'murmurhash', 'blis',
        'weasel', 'confection', 'catalogue',
        'openai', 'huggingface_hub', 'gradio', 'gradio_client',
        'pandas', 'scipy', 'numba', 'llvmlite', 'sqlalchemy', 'openpyxl',
        'gevent', 'trio', 'anyio', 'httpx', 'pydantic', 'narwhals',
        'pytz', 'tzdata', 'pygments', 'rich', 'markdown_it',
        'joblib', 'PIL', 'setuptools', 'pkg_resources',
    ]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_BINARIES,
    # Шрифты SF Pro, иконки и app.ico нужны программе в рантайме.
    datas=_DATAS,
    hiddenimports=_HIDDEN,
    hookspath=[],
    hooksconfig={},
    # Заглушки ставятся ДО основного кода, иначе argostranslate не импортируется.
    runtime_hooks=['pyi_hooks/stub_heavy_deps.py'],
    excludes=_EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Knack',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # панель живёт в трее, консоль не нужна
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\app.ico'],
    version=_VERSION_RES,
)
