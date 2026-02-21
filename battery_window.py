import datetime
import re
import tkinter as tk
from tkinter import messagebox

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ui.tools import Tools


class BatteryAnalysisWindow:
    def __init__(self, parent, host, log_path):
        self.top = tk.Toplevel(parent)
        self.top.title(f"Battery Analysis: {host}")
        self.host = host
        self.log_path = log_path
        self.canvas = None
        
        # Controls
        ctrl_frame = tk.Frame(self.top)
        ctrl_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(ctrl_frame, text="Last N Days (0=All):").pack(side=tk.LEFT)
        self.days_var = tk.IntVar(value=0)
        tk.Entry(ctrl_frame, textvariable=self.days_var, width=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(ctrl_frame, text="Refresh", command=self.analyze).pack(side=tk.LEFT, padx=5)
        
        # Stats
        self.stats_lbl = tk.Label(self.top, text="Ready", justify=tk.LEFT, font=("Consolas", 10))
        self.stats_lbl.pack(fill=tk.X, padx=5, pady=5)
        
        # Plot Frame
        self.plot_frame = tk.Frame(self.top)
        self.plot_frame.pack(fill=tk.BOTH, expand=True)
        
        Tools.center_window(self.top, 900, 700)
        self.analyze()
        
    def analyze(self):
        days = self.days_var.get()
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days) if days > 0 else datetime.datetime.min
        
        data = [] # (time, pct, status)
        pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - .* - INFO - " + re.escape(self.host) + r": Battery (\d+)% \((.*)\)")
        
        try:
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    m = pattern.match(line)
                    if m:
                        dt_str, pct_str, status = m.groups()
                        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                        if dt >= cutoff:
                            data.append((dt, int(pct_str), status))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read log: {e}")
            return

        if not data:
            self.stats_lbl.config(text="No data found for this host in the specified period.")
            if self.canvas: self.canvas.get_tk_widget().destroy()
            self.canvas = None
            return

        data.sort(key=lambda x: x[0])
        
        slopes = []
        current_segment = []
        
        for i in range(len(data)):
            dt, pct, status = data[i]
            if status == 'DISCHARGING':
                if not current_segment:
                    current_segment.append(data[i])
                else:
                    last_dt, last_pct, _ = current_segment[-1]
                    if (dt - last_dt).total_seconds() < 7200 and pct <= last_pct:
                        current_segment.append(data[i])
                    else:
                        self.process_segment(current_segment, slopes)
                        current_segment = [data[i]]
            else:
                if current_segment:
                    self.process_segment(current_segment, slopes)
                    current_segment = []
        
        if current_segment:
            self.process_segment(current_segment, slopes)
            
        if slopes:
            avg_slope = np.mean(slopes) # %/hr
            std_slope = np.std(slopes)
            if avg_slope > 0:
                est_duration = 100.0 / avg_slope
                est_error = est_duration * (std_slope / avg_slope)
                stats_text = (f"Based on {len(slopes)} discharge segments.\n"
                              f"Average Drain Rate: {avg_slope:.2f}% / hr (±{std_slope:.2f})\n"
                              f"Estimated Total Duration: {est_duration:.1f} hours (±{est_error:.1f})")
            else:
                stats_text = "Drain rate is zero or negative?"
        else:
            stats_text = "No valid discharge segments found for analysis."
            
        self.stats_lbl.config(text=stats_text)
        self.plot(data)

    def process_segment(self, segment, slopes):
        if len(segment) < 2: return
        start_dt, start_pct, _ = segment[0]
        end_dt, end_pct, _ = segment[-1]
        duration_hours = (end_dt - start_dt).total_seconds() / 3600.0
        drop = start_pct - end_pct
        if drop >= 1 and duration_hours >= 0.5:
            slope = drop / duration_hours
            slopes.append(slope)

    def plot(self, data):
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
        
        fig, ax = plt.subplots(figsize=(8, 5), dpi=100)
        times = [x[0] for x in data]
        pcts = [x[1] for x in data]
        ax.plot(times, pcts, marker='.', linestyle='-', markersize=2, label='Battery %')
        ax.set_title(f"Battery History: {self.host}")
        ax.set_ylabel("Percentage")
        ax.set_xlabel("Time")
        ax.grid(True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        fig.autofmt_xdate()
        self.canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)