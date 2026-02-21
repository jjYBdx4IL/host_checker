import logging
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw
from windows_toasts import Toast, WindowsToaster

# Constants
APPNAME = "host_checker"
APP_GITHUB_ID = "jjYBdx4IL/host_checker"
APP_VERSION = "0.8.0.0"

LAPPDATA_PATH = Path(os.environ.get('LOCALAPPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Local')))
LOG_DIR_PATH = LAPPDATA_PATH / 'log'
LOG_FILE_PATH = LOG_DIR_PATH / f'{APPNAME}.log'

CFG_DIR_PATH = LAPPDATA_PATH / 'py_apps' / APPNAME
LOCK_FILE_PATH = CFG_DIR_PATH / 'lock'
DB_PATH = CFG_DIR_PATH / 'sqlite.db'

# Global State
warning_triggered = False
open_log_callback = None
toaster = WindowsToaster(APPNAME)

def show_warning(message):
    global warning_triggered
    warning_triggered = True
    try:
        logging.warning(message)
        new_toast = Toast()
        new_toast.text_fields = [f"⚠️ {message}"]
        def on_click(args):
            if open_log_callback:
                open_log_callback()
            else:
                subprocess.Popen(['notepad.exe', str(LOG_FILE_PATH)])
        new_toast.on_activated = on_click
        toaster.show_toast(new_toast)
    except Exception as e:
        logging.error(f"Failed to show toast: {e}")

def create_icon(status):
    width = 64
    height = 64
    image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    dc = ImageDraw.Draw(image)
    
    if status == 'ok':
        dc.ellipse((4, 4, 60, 60), fill='green', outline='black')
    else:
        dc.ellipse((4, 4, 60, 60), fill='red', outline='black')
        dc.rectangle((28, 14, 36, 42), fill='white')
        dc.ellipse((28, 48, 36, 56), fill='white')
        
    return image
