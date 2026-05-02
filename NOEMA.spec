# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

webview_datas,   webview_bins,   webview_hidden   = collect_all('webview')
uvicorn_datas,   uvicorn_bins,   uvicorn_hidden   = collect_all('uvicorn')
fastapi_datas,   fastapi_bins,   fastapi_hidden   = collect_all('fastapi')
starlette_datas, starlette_bins, starlette_hidden = collect_all('starlette')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=webview_bins + uvicorn_bins,
    datas=[
        ('index.html',      '.'),
        ('security.json',   '.'),
        ('curriculum.json', '.'),
    ] + webview_datas + uvicorn_datas + fastapi_datas + starlette_datas,
    hiddenimports=(
        ['server', 'audit'] +
        webview_hidden + uvicorn_hidden + fastapi_hidden + starlette_hidden +
        collect_submodules('bs4') +
        collect_submodules('requests') +
        collect_submodules('anyio') +
        ['h11', 'h11._connection', 'h11._events', 'h11._util']
    ),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NOEMA',
    debug=False,
    strip=False,
    upx=False,
    console=False,        # no terminal window
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='NOEMA',
)

app = BUNDLE(
    coll,
    name='NOEMA.app',
    icon='noema.icns',
    bundle_identifier='com.noema.personalai',
    info_plist={
        'CFBundleName':             'NOEMA',
        'CFBundleDisplayName':      'NOEMA',
        'CFBundleVersion':          '1.0',
        'CFBundleShortVersionString': '1.0',
        'NSHighResolutionCapable':  True,
        'LSMinimumSystemVersion':   '12.0',
        'NSRequiresAquaSystemAppearance': False,
        'NSAppTransportSecurity': {
            'NSAllowsLocalNetworking': True,
        },
    },
)
