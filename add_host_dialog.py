import sqlite3
import tkinter as tk
from tkinter import messagebox

from ui.tools import Tools


class AddHostDialog:
    def __init__(self, parent, db_path, callback, current_data=None):
        self.top = tk.Toplevel(parent)
        self.top.title("Add/Edit Host")
        self.db_path = db_path
        self.callback = callback
        self.current_data = current_data
        
        tk.Label(self.top, text="Host:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.host_var = tk.StringVar()
        tk.Entry(self.top, textvariable=self.host_var, width=30).grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(self.top, text="Battery %:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.batt_var = tk.IntVar(value=15)
        tk.Entry(self.top, textvariable=self.batt_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        tk.Label(self.top, text="Storage MB:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.store_var = tk.IntVar(value=1024)
        tk.Entry(self.top, textvariable=self.store_var, width=10).grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        tk.Label(self.top, text="Port:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.port_var = tk.IntVar(value=8022)
        tk.Entry(self.top, textvariable=self.port_var, width=10).grid(row=3, column=1, padx=5, pady=5, sticky="w")
        
        tk.Button(self.top, text="Save", command=self.save).grid(row=4, column=0, columnspan=2, pady=10)
        
        if current_data:
            self.host_var.set(current_data[0])
            self.port_var.set(current_data[1])
            self.batt_var.set(current_data[2])
            self.store_var.set(current_data[3])
        
        self.top.transient(parent)
        Tools.center_window(self.top)
        
    def save(self):
        host = self.host_var.get().strip()
        if not host: return
        try:
            con = sqlite3.connect(str(self.db_path))
            with con:
                if self.current_data and self.current_data[0] != host:
                    con.execute("DELETE FROM hosts WHERE host = ?", (self.current_data[0],))
                
                con.execute("INSERT OR REPLACE INTO hosts (host, battery_threshold, storage_threshold, port) VALUES (?, ?, ?, ?)", 
                            (host, self.batt_var.get(), self.store_var.get(), self.port_var.get()))
            con.close()
            self.callback()
            self.top.destroy()
        except Exception as e:
            messagebox.showerror("Error", str(e))