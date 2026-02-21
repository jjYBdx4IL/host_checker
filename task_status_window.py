import datetime
import logging
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from ui.tools import Tools


class TaskStatusWindow:
    def __init__(self, root, db_path):
        self.db_path = db_path
        self.root = tk.Toplevel(root)
        self.root.title("Task Status")
        
        # Treeview Frame
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # Treeview
        columns = ('filename', 'timeout', 'last_run', 'status')
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.heading('filename', text='Filename')
        self.tree.heading('timeout', text='Timeout (h)')
        self.tree.heading('last_run', text='Last Run')
        self.tree.heading('status', text='Status')
        self.tree.column('filename', width=200, stretch=True)
        self.tree.column('timeout', width=80, stretch=False)
        self.tree.column('last_run', width=150, stretch=False)
        self.tree.column('status', width=100, stretch=False)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_task())
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        
        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(btn_frame, text="Remove Selected", command=self.remove_selected).pack(side=tk.LEFT, padx=5)
        self.btn_edit = tk.Button(btn_frame, text="Edit", command=self.edit_task, state=tk.DISABLED)
        self.btn_edit.pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Refresh", command=self.load_data).pack(side=tk.LEFT, padx=5)
        
        self.load_data()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        Tools.center_window(self.root, 600, 400)
        
    def load_data(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.on_select(None)
        
        try:
            con = sqlite3.connect(str(self.db_path))
            cur = con.cursor()
            cur.execute("SELECT filename, timeout_hours, last_run, status FROM task_status")
            for row in cur.fetchall():
                filename, timeout, last_run, status = row
                dt_str = "Never"
                if last_run:
                    try:
                        dt = datetime.datetime.fromtimestamp(float(last_run))
                        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        dt_str = str(last_run)
                
                self.tree.insert('', tk.END, values=(filename, timeout, dt_str, status))
            con.close()
        except Exception as e:
            logging.error(f"Failed to load DB: {e}")
            
    def on_select(self, event):
        if len(self.tree.selection()) == 1:
            self.btn_edit.config(state=tk.NORMAL)
        else:
            self.btn_edit.config(state=tk.DISABLED)

    def edit_task(self):
        selected = self.tree.selection()
        if not selected: return
        
        item = self.tree.item(selected[0])
        values = item['values']
        old_filename = values[0]
        old_timeout = values[1]
        
        dlg = tk.Toplevel(self.root)
        dlg.title("Edit Task")
        
        tk.Label(dlg, text="Filename:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        var_filename = tk.StringVar(value=old_filename)
        tk.Entry(dlg, textvariable=var_filename, width=30).grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(dlg, text="Timeout (hours):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        var_timeout = tk.IntVar(value=old_timeout)
        tk.Entry(dlg, textvariable=var_timeout, width=10).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        def save():
            new_filename = var_filename.get().strip()
            try:
                new_timeout = var_timeout.get()
            except Exception:
                messagebox.showerror("Error", "Timeout must be an integer")
                return

            if not new_filename:
                messagebox.showerror("Error", "Filename cannot be empty")
                return

            try:
                con = sqlite3.connect(str(self.db_path))
                with con:
                    if new_filename != old_filename:
                        cur = con.cursor()
                        cur.execute("SELECT 1 FROM task_status WHERE filename = ?", (new_filename,))
                        if cur.fetchone():
                            messagebox.showerror("Error", "Task with this filename already exists")
                            return
                        con.execute("UPDATE task_status SET filename = ?, timeout_hours = ? WHERE filename = ?", (new_filename, new_timeout, old_filename))
                    else:
                        con.execute("UPDATE task_status SET timeout_hours = ? WHERE filename = ?", (new_timeout, old_filename))
                con.close()
                self.load_data()
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")

        tk.Button(dlg, text="Save", command=save).grid(row=2, column=0, columnspan=2, pady=10)
        Tools.center_window(dlg, 350, 150)

    def remove_selected(self):
        selected = self.tree.selection()
        if not selected: return
        if not messagebox.askyesno("Confirm", "Remove selected tasks from tracking?"):
            return
            
        try:
            con = sqlite3.connect(str(self.db_path))
            with con:
                for item in selected:
                    values = self.tree.item(item, 'values')
                    filename = values[0]
                    con.execute("DELETE FROM task_status WHERE filename = ?", (filename,))
            con.close()
            self.load_data()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_close(self):
        self.root.destroy()
