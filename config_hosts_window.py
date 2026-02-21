import concurrent.futures
import ipaddress
import logging
import os
import socket
import sqlite3
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import host_checker.common as common
from host_checker.add_host_dialog import AddHostDialog
from host_checker.battery_window import BatteryAnalysisWindow
from ui.tools import Tools


class ConfigHostsWindow:
    def __init__(self, root, db_path):
        self.db_path = db_path
        self.root = tk.Toplevel(root)
        self.root.title(f"{common.APPNAME} {common.APP_VERSION} - Hosts Configuration")
        
        # Treeview
        columns = ('host', 'port', 'battery', 'storage')
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.heading('host', text='Host')
        self.tree.heading('port', text='Port')
        self.tree.heading('battery', text='Battery %')
        self.tree.heading('storage', text='Storage MB')
        self.tree.column('host', width=250, stretch=True)
        self.tree.column('port', width=60, stretch=False)
        self.tree.column('battery', width=80, stretch=False)
        self.tree.column('storage', width=80, stretch=False)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_host())
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(btn_frame, text="Add Host", command=self.add_host).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Edit Host", command=self.edit_host).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Remove Selected", command=self.remove_host).pack(side=tk.LEFT, padx=5)
        self.analyze_btn = tk.Button(btn_frame, text="Analyze Battery", command=self.analyze_battery, state=tk.DISABLED)
        self.analyze_btn.pack(side=tk.LEFT, padx=5)
        self.scan_btn = tk.Button(btn_frame, text="Auto Scan", command=self.auto_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        # Global Settings
        settings_frame = tk.LabelFrame(self.root, text="Global Settings")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(settings_frame, text="SSH Key:").pack(side=tk.LEFT, padx=5)
        self.key_var = tk.StringVar()
        tk.Entry(settings_frame, textvariable=self.key_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        tk.Button(settings_frame, text="...", width=3, command=self.browse_key).pack(side=tk.LEFT, padx=2)
        tk.Button(settings_frame, text="Save", command=self.save_key).pack(side=tk.LEFT, padx=5)
        tk.Button(settings_frame, text="Test", command=self.test_key).pack(side=tk.LEFT, padx=5)

        self.load_data()
        Tools.center_window(self.root, 500, 400)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_tree_select(self, event):
        if len(self.tree.selection()) == 1:
            self.analyze_btn.config(state=tk.NORMAL)
        else:
            self.analyze_btn.config(state=tk.DISABLED)

    def analyze_battery(self):
        selected = self.tree.selection()
        if not selected: return
        values = self.tree.item(selected[0], 'values')
        host = values[0]
        BatteryAnalysisWindow(self.root, host, common.LOG_FILE_PATH)

    def load_data(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        try:
            con = sqlite3.connect(str(self.db_path))
            cur = con.cursor()
            cur.execute("SELECT host, battery_threshold, storage_threshold, port FROM hosts ORDER BY host ASC")
            for row in cur.fetchall():
                self.tree.insert('', tk.END, values=(row[0], row[3] if row[3] is not None else 8022, row[1] if row[1] is not None else 15, row[2] if row[2] is not None else 1024))
            
            try:
                cur.execute("SELECT value FROM settings WHERE key = 'ssh_key_path'")
                row = cur.fetchone()
                if row: self.key_var.set(row[0])
            except sqlite3.OperationalError:
                pass
            con.close()
        except Exception as e:
            logging.error(f"Failed to load hosts DB: {e}")

    def add_host(self):
        AddHostDialog(self.root, self.db_path, self.load_data)

    def edit_host(self):
        selected = self.tree.selection()
        if not selected: return
        values = self.tree.item(selected[0], 'values')
        # values: host, port, battery, storage
        AddHostDialog(self.root, self.db_path, self.load_data, current_data=values)

    def remove_host(self):
        selected = self.tree.selection()
        if not selected: return
        for item in selected:
            values = self.tree.item(item, 'values')
            host = values[0]
            try:
                con = sqlite3.connect(str(self.db_path))
                with con:
                    con.execute("DELETE FROM hosts WHERE host = ?", (host,))
                con.close()
            except Exception as e:
                logging.error(f"Error deleting {host}: {e}")
        self.load_data()

    def auto_scan(self):
        default_subnet = "192.168.1.0/24"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('10.255.255.255', 1))
            local_ip = s.getsockname()[0]
            s.close()
            default_subnet = str(ipaddress.IPv4Network(f"{local_ip}/24", strict=False))
        except Exception:
            pass

        subnet_str = simpledialog.askstring("Auto Scan", "Enter IPv4 Subnet (CIDR):", initialvalue=default_subnet, parent=self.root)
        if not subnet_str: return

        try:
            network = ipaddress.IPv4Network(subnet_str, strict=False)
        except ValueError:
            messagebox.showerror("Error", "Invalid subnet format")
            return

        self.scan_btn.config(state=tk.DISABLED, text="Scanning...")
        
        def run_scan():
            found = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(self.check_ssh_port, str(ip)): str(ip) for ip in network.hosts()}
                for future in concurrent.futures.as_completed(futures):
                    if future.result():
                        found.append(futures[future])
            self.root.after(0, lambda: self.finish_scan(found))

        threading.Thread(target=run_scan, daemon=True).start()

    def check_ssh_port(self, ip):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect((ip, 8022))
            banner = sock.recv(1024)
            sock.close()
            if b'SSH' in banner:
                return True
        except Exception:
            pass
        return False

    def finish_scan(self, hosts):
        if hosts:
            try:
                con = sqlite3.connect(str(self.db_path))
                with con:
                    for host in hosts:
                        con.execute("INSERT OR IGNORE INTO hosts (host, battery_threshold, storage_threshold, port) VALUES (?, 15, 1024, 8022)", (host,))
                con.close()
                self.load_data()
            except Exception as e:
                logging.error(f"Scan save error: {e}")
        
        self.scan_btn.config(state=tk.NORMAL, text="Auto Scan")
        messagebox.showinfo("Scan Complete", f"Scan finished. Found {len(hosts)} hosts.")

    def on_close(self):
        self.root.destroy()

    def browse_key(self):
        initial = os.path.expanduser("~/.ssh")
        if not os.path.exists(initial):
            initial = os.path.expanduser("~")
        path = filedialog.askopenfilename(initialdir=initial, title="Select Private Key")
        if path:
            self.key_var.set(path)

    def save_key(self):
        path = self.key_var.get().strip()
        try:
            con = sqlite3.connect(str(self.db_path))
            with con:
                con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
                con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ssh_key_path', ?)", (path,))
            con.close()
            messagebox.showinfo("Success", "SSH Key path saved.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save key: {e}")

    def test_key(self):
        key_path = self.key_var.get().strip()
        if not key_path:
            messagebox.showerror("Error", "No key file specified.")
            return
        if not os.path.exists(key_path):
            messagebox.showerror("Error", "Key file not found.")
            return
            
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select Host", "Please select a host from the list to test the connection.")
            return
            
        item = self.tree.item(selected[0])
        host = item['values'][0]
        port = item['values'][1]
        
        try:
            cmd = ["ssh", "-p", str(port), "-i", key_path, "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", f"root@{host}", "echo OK"]
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, timeout=10)
            if proc.returncode == 0:
                messagebox.showinfo("Success", f"Connection to {host} successful!")
            else:
                messagebox.showerror("Failure", f"Connection failed:\n{proc.stderr}")
        except Exception as e:
            messagebox.showerror("Error", f"Test failed: {e}")
