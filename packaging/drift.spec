# PyInstaller spec for the DRIFT desktop app (one-folder build).
# Build: pyinstaller packaging/drift.spec   ->  dist/DRIFT/DRIFT(.exe)
# FFmpeg/FFprobe are not bundled; install them and keep them on PATH (montage-editor doctor checks).
from pathlib import Path
import montage_editor

package = Path(montage_editor.__file__).parent
resources = [(str(path), str(Path('montage_editor')/path.relative_to(package).parent))
             for path in (package/'resources').rglob('*') if path.is_file()]

analysis = Analysis([str(Path(SPECPATH)/'drift_studio.py')], datas=resources,
                    hiddenimports=['montage_editor.vision_director', 'montage_editor.music_sources',
                                   'montage_editor.ai_director'],
                    excludes=['tkinter'])
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='DRIFT', console=False)
COLLECT(exe, analysis.binaries, analysis.datas, name='DRIFT')
