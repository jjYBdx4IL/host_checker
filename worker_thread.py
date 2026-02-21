import logging
import threading

import pythoncom

import host_checker.checks as checks
import host_checker.common as common


class WorkerThread(threading.Thread):
    def __init__(self, icon, check_event, shutdown_event):
        super().__init__(name="WorkerThread")
        self.icon = icon
        self.check_event = check_event
        self.shutdown_event = shutdown_event

    def run(self):
        logging.info("Worker thread started.")
        pythoncom.CoInitialize()
        try:
            while not self.shutdown_event.is_set():
                logging.info("Starting checks...")
                common.warning_triggered = False
                
                current_hosts = checks.get_monitored_hosts()
                key_file = checks.get_ssh_key_path()
                for host_data in current_hosts:
                    if self.shutdown_event.is_set(): break
                    host = host_data[0]
                    batt = host_data[1] if host_data[1] is not None else 15
                    store = host_data[2] if host_data[2] is not None else 1024
                    port = host_data[3] if len(host_data) > 3 and host_data[3] is not None else 8022
                    checks.check_host(host, port, batt, store, key_file)

                if self.shutdown_event.is_set(): break
                checks.check_task_execution()
                
                if self.shutdown_event.is_set(): break
                checks.check_checksums()
                
                if common.warning_triggered:
                    self.icon.icon = common.create_icon('error')
                else:
                    self.icon.icon = common.create_icon('ok')
                    
                self.check_event.wait(1800)
                self.check_event.clear()
        finally:
            pythoncom.CoUninitialize()
            logging.info("Worker thread stopped.")