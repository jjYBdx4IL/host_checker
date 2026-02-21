import logging
import sqlite3
import tkinter as tk
from tkinter import messagebox

from host_checker import common
from ui.tools import Tools


class ConfigWindow:
    def __init__(self, root, db_path, update_checker):
        self.db_path = db_path
        self.update_checker = update_checker
        self.root = tk.Toplevel(root)
        self.root.title(f"{common.APPNAME} Settings")
        
        self.var_updates = tk.BooleanVar(value=True)
        
        frame = tk.Frame(self.root, padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Updates
        lf_updates = tk.LabelFrame(frame, text="Updates")
        lf_updates.pack(fill=tk.X, pady=5)
        
        tk.Checkbutton(lf_updates, text="Check for updates automatically", variable=self.var_updates).pack(anchor=tk.W, padx=5, pady=5)
        tk.Button(lf_updates, text="Check Now", command=self.check_now).pack(anchor=tk.W, padx=5, pady=5)
        
        # Save/Cancel
        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        tk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=self.root.destroy).pack(side=tk.LEFT)
        
        self.load_settings()
        Tools.center_window(self.root, 300, 200)

    def load_settings(self):
        try:
            con = sqlite3.connect(str(self.db_path))
            cur = con.cursor()
            cur.execute("SELECT value FROM settings WHERE key='update_check_enabled'")
            row = cur.fetchone()
            if row:
                self.var_updates.set(row[0] == '1')
            con.close()
        except Exception as e:
            logging.error(f"Failed to load settings: {e}")

    def save(self):
        enabled = self.var_updates.get()
        try:
            con = sqlite3.connect(str(self.db_path))
            with con:
                con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('update_check_enabled', ?)", ('1' if enabled else '0',))
            con.close()
            
            if self.update_checker:
                if enabled:
                    self.update_checker.start()
                else:
                    self.update_checker.stop()
            
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def check_now(self):
        if self.update_checker:
            self.update_checker.check_now_interactive(self.root)