#!/usr/bin/env python3
# encoding: utf-8
# @MAKEAPPX:AUTOSTART@
import logging
import os
import sqlite3
import sys
import threading
import tkinter as tk
from tkinter import messagebox

import portalocker
import pystray
import win32timezone  # pyinstaller will miss it otherwise
from windows_toasts import WindowsToaster

from host_checker import common
from host_checker.config_cksums_window import ConfigCksumsWindow
from host_checker.config_hosts_window import ConfigHostsWindow
from host_checker.config_window import ConfigWindow
from host_checker.task_status_window import TaskStatusWindow
from host_checker.worker_thread import WorkerThread
from ui.github_update_checker import GithubUpdateChecker
from ui.licenses_window import LicensesWindow
from ui.tkless import TkLess


def init_db():
    con = sqlite3.connect(str(common.DB_PATH))
    with con:
        con.execute("CREATE TABLE IF NOT EXISTS hosts (host TEXT PRIMARY KEY, battery_threshold INTEGER, storage_threshold INTEGER, port INTEGER)")
        con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS task_status (filename TEXT PRIMARY KEY, timeout_hours INTEGER, last_run TIMESTAMP, status TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS checksum_files (path TEXT, last_check TIMESTAMP, status TEXT, host TEXT DEFAULT '', PRIMARY KEY (host, path))")
    con.close()

def on_autostart_registry():
    try:
        os.startfile("ms-settings:startupapps")
    except Exception as e:
        pass

# Global window references for singletons
log_window = None
hosts_window = None
cksums_window = None
task_status_window = None
licenses_window = None
config_window = None

def main():
    common.LOG_DIR_PATH.mkdir(parents=False, exist_ok=True)
    common.CFG_DIR_PATH.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(process)5d - %(threadName)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(common.LOG_FILE_PATH, encoding='utf-8'), logging.StreamHandler()]
    )
    logging.info(f"{common.APPNAME} started")
    
    lock_file = open(common.LOCK_FILE_PATH, 'a')
    try:
        portalocker.lock(lock_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
    except portalocker.LockException:
        print("Another instance is already running.")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(common.APPNAME, "Another instance is already running.")
        sys.exit(1)

    try:
        init_db()
    except Exception as ex:
        logging.exception(ex)
        sys.exit(1)

    root = tk.Tk()
    root.withdraw()

    update_check_enabled = True
    try:
        con = sqlite3.connect(str(common.DB_PATH))
        cur = con.cursor()
        cur.execute("SELECT value FROM settings WHERE key='update_check_enabled'")
        row = cur.fetchone()
        if row:
            update_check_enabled = (row[0] == '1')
        con.close()
    except Exception:
        pass

    uc = GithubUpdateChecker(common.APP_GITHUB_ID, common.APPNAME, common.APP_VERSION, root=root, toaster=common.toaster)
    if update_check_enabled:
        uc.start()

    check_event = threading.Event()
    shutdown_event = threading.Event()

    icon = pystray.Icon(common.APPNAME, common.create_icon('ok'), f"{common.APPNAME} {common.APP_VERSION}")
    
    def trigger_check():
        check_event.set()

    def open_log():
        global log_window
        if log_window and log_window.root.winfo_exists():
            log_window.root.lift()
            log_window.root.focus_force()
            return
        log_window = TkLess(root, common.LOG_FILE_PATH)
    common.open_log_callback = lambda: root.after(0, open_log)

    def open_config():
        global config_window
        if config_window and config_window.root.winfo_exists():
            config_window.root.lift()
            config_window.root.focus_force()
            return
        config_window = ConfigWindow(root, common.DB_PATH, uc)

    def open_config_cksums():
        global cksums_window
        if cksums_window and cksums_window.root.winfo_exists():
            cksums_window.root.lift()
            cksums_window.root.focus_force()
            return
        cksums_window = ConfigCksumsWindow(root, common.DB_PATH)

    def open_config_hosts():
        global hosts_window
        if hosts_window and hosts_window.root.winfo_exists():
            hosts_window.root.lift()
            hosts_window.root.focus_force()
            return
        hosts_window = ConfigHostsWindow(root, common.DB_PATH)

    def open_task_status():
        global task_status_window
        if task_status_window and task_status_window.root.winfo_exists():
            task_status_window.root.lift()
            task_status_window.root.focus_force()
            return
        task_status_window = TaskStatusWindow(root, common.DB_PATH)

    def open_licenses():
        global licenses_window
        if licenses_window and licenses_window.winfo_exists():
            licenses_window.lift()
            return
        licenses_window = LicensesWindow(root)

    def quit_app():
        logging.info("shutdown requested by user")
        uc.stop()
        shutdown_event.set()
        check_event.set()
        icon.stop()
        root.quit()

    icon.menu = pystray.Menu(pystray.MenuItem('Check Now', lambda i, it: root.after(0, trigger_check)),
                             pystray.MenuItem('Settings', lambda i, it: root.after(0, open_config)),
                             pystray.MenuItem('Config Host Checks', lambda i, it: root.after(0, open_config_hosts)),
                             pystray.MenuItem('Config Checksum Checks', lambda i, it: root.after(0, open_config_cksums)),
                             pystray.MenuItem('Config Task Status Checks', lambda i, it: root.after(0, open_task_status)),
                             pystray.MenuItem('Open Log', lambda i, it: root.after(0, open_log)),
                             pystray.MenuItem("Open Autostart Registry", lambda i, it: root.after(0, on_autostart_registry)),
                             pystray.MenuItem('Show Licenses', lambda i, it: root.after(0, open_licenses)),
                             pystray.MenuItem('Quit', lambda i, it: root.after(0, quit_app)))
    
    t = WorkerThread(icon, check_event, shutdown_event)
    t.start()
    
    # Run icon in separate thread so main thread can handle GUI
    icon_thread = threading.Thread(target=icon.run, daemon=True)
    icon_thread.start()

    try:
        root.mainloop()
    finally:
        shutdown_event.set()
        icon.stop()
        logging.debug("Waiting for icon thread...")
        icon_thread.join()
        logging.debug("Waiting for worker thread...")
        t.join()

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.exception("")
    finally:
        logging.info("terminated")