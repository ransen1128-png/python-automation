"""Prepare the desktop browser dependency, then launch the resumable queue."""
import subprocess
import sys
import venv
from pathlib import Path

root=Path(__file__).resolve().parent
python=root/'.venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
try:
    if not python.exists():
        print('Preparing the desktop Python environment...',flush=True)
        venv.EnvBuilder(with_pip=True).create(root/'.venv')
    ready=subprocess.run([str(python),'-c','import playwright.sync_api'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if ready.returncode:
        print('Installing the desktop browser helper (first run only)...',flush=True)
        subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements-desktop.txt')],check=True)
    raise SystemExit(subprocess.call([str(python),str(root/'participant_queue.py'),*sys.argv[1:]],cwd=root))
except (OSError,subprocess.CalledProcessError) as error:
    print('Unable to start the desktop queue:',error)
    raise SystemExit(1)
