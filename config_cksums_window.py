import datetime
import logging
import os
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ui.tools import Tools


class ConfigCksumsWindow:
    def __init__(self, root, db_path):
        self.db_path = db_path
        self.root = tk.Toplevel(root)
        self.root.title("Checksum Configuration")
        
        # Treeview Frame
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # Treeview
        columns = ('host', 'path', 'last_check', 'status')
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.heading('host', text='Host')
        self.tree.heading('path', text='Path')
        self.tree.heading('last_check', text='Last Check')
        self.tree.heading('status', text='Status')
        self.tree.column('host', width=100, stretch=False)
        self.tree.column('path', width=400, stretch=True)
        self.tree.column('last_check', width=150, stretch=False)
        self.tree.column('status', width=100, stretch=False)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(btn_frame, text="Add File", command=self.add_file).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Remove Selected", command=self.remove_file).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Refresh", command=self.load_data).pack(side=tk.LEFT, padx=5)
        
        self.load_data()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        Tools.center_window(self.root, 800, 400)
        
    def load_data(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        
        try:
            con = sqlite3.connect(str(self.db_path))
            cur = con.cursor()
            cur.execute("SELECT host, path, last_check, status FROM checksum_files ORDER BY host, path ASC")
            for row in cur.fetchall():
                ts = row[2]
                try:
                    dt = datetime.datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    dt = str(ts)
                self.tree.insert('', tk.END, values=(row[0], row[1], dt, row[3]))
            con.close()
        except Exception as e:
            logging.error(f"Failed to load DB: {e}")
            
    def add_file(self):
        path = filedialog.askopenfilename(title="Select Checksum File", filetypes=[("Checksum Files", "*.sha256 *_sha256"), ("All Files", "*.*")])
        if path:
            path = os.path.normpath(path)
            try:
                con = sqlite3.connect(str(self.db_path))
                with con:
                    con.execute("INSERT OR IGNORE INTO checksum_files (path, last_check, status) VALUES (?, ?, ?)", (path, 0, 'pending'))
                con.close()
                self.load_data()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def remove_file(self):
        selected = self.tree.selection()
        if not selected: return
        for item in selected:
            values = self.tree.item(item, 'values')
            host = values[0]
            path = values[1]
            try:
                con = sqlite3.connect(str(self.db_path))
                with con:
                    con.execute("DELETE FROM checksum_files WHERE path = ? AND host = ?", (path, host))
                con.close()
            except Exception as e:
                logging.error(f"Error deleting {path}: {e}")
        self.load_data()

    def on_close(self):
        self.root.destroy()
        
