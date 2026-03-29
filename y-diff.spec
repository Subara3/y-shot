# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('flet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('flet_desktop')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


# Exclude heavy packages not used by y-diff
_excludes = [
    'torch', 'torchvision', 'torchaudio',
    'tensorflow', 'keras',
    'transformers', 'tokenizers', 'huggingface_hub', 'safetensors',
    'scipy', 'pandas', 'matplotlib',
    'cv2', 'opencv', 'onnxruntime',
    'bitsandbytes', 'sympy',
    'IPython', 'notebook', 'jupyter',
    'tkinter', '_tkinter',
    'selenium',
    'test', 'tests',
]

a = Analysis(
    ['y_diff.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
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
    name='y-diff',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\diff_icon.ico'],
)
