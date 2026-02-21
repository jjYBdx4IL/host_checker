import ctypes
import datetime
import glob
import hashlib
import json
import logging
import os
import sqlite3
import string
import subprocess
import sys
import time
from pathlib import Path

import host_checker.common as common

def _get_ssh_cmd(host, port=8022, key_file=None, remote_cmd=None) -> list[str]:
    cmd = [
        "ssh",
        "-p", str(port),
        "-o", "ConnectTimeout=55",
        "-o", "BatchMode=yes",
    ]
    if key_file:
        cmd.extend(["-i", key_file])
    cmd.append(f"root@{host}")
    if remote_cmd:
        cmd.append(remote_cmd)
    return cmd

def check_host(host, port, battery_threshold, storage_threshold, key_file=None):
    cmd =_get_ssh_cmd(host, port, key_file, "termux-battery-status; echo '|||'; df -kP /storage/emulated; echo '|||'; find storage/shared/backup/ -type f -iname '*.sha256' 2>/dev/null ||:")
    
    try:
        logging.info(f"Checking {host}...")
        startupinfo = None
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(cmd, capture_output=True, text=True, check=True, startupinfo=startupinfo, timeout=60)
        output = result.stdout.strip()
        
        if not output:
            logging.warning(f"{host}: No output received.")
            return

        parts = output.split('|||')
        battery_out = parts[0].strip()
        storage_out = parts[1].strip() if len(parts) > 1 else ""
        checksums_out = parts[2].strip() if len(parts) > 2 else None

        if battery_out:
            try:
                data = json.loads(battery_out)
                percentage = data.get("percentage", 0)
                status = data.get("status", "UNKNOWN")
                
                logging.info(f"{host}: Battery {percentage}% ({status})")
                
                if percentage < battery_threshold and status != "CHARGING":
                    common.show_warning(f"Battery Low: {host}\nCharge: {percentage}% Status: {status}")
            except json.JSONDecodeError:
                logging.error(f"Failed to check {host}: Invalid JSON output received.")

        if storage_out:
            try:
                lines = storage_out.splitlines()
                if len(lines) > 1:
                    vals = lines[-1].split()
                    free_mb = int(vals[3]) / 1024
                    logging.info(f"{host}: Storage {free_mb:.0f} MB free")
                    if free_mb < storage_threshold:
                        common.show_warning(f"Low Storage: {host}\nFree Space: {free_mb:.0f} MB")
            except Exception as e:
                logging.error(f"Failed to parse storage for {host}: {e}")

        if checksums_out is not None:
            try:
                found_paths = set(line.strip() for line in checksums_out.splitlines() if line.strip())
                con = sqlite3.connect(str(common.DB_PATH))
                with con:
                    cur = con.cursor()
                    cur.execute("SELECT path FROM checksum_files WHERE host = ?", (host,))
                    existing_paths = set(row[0] for row in cur.fetchall())
                    
                    for p in found_paths:
                        if p not in existing_paths:
                            con.execute("INSERT OR IGNORE INTO checksum_files (path, last_check, status, host) VALUES (?, 0, 'pending', ?)", (p, host))
                            logging.info(f"Found new remote checksum file: {p} on {host}")
                    
                    for p in existing_paths:
                        if p not in found_paths:
                            con.execute("UPDATE checksum_files SET status = 'missing' WHERE path = ? AND host = ?", (p,host))
                            logging.warning(f"Remote checksum file missing: {p} on {host}")
                con.close()
            except Exception as e:
                logging.error(f"Failed to process checksums for {host}: {e}")

    except subprocess.TimeoutExpired:
        logging.error(f"Failed to check {host}: SSH command timed out.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to check {host}: SSH command failed. {e.stderr.strip()}")
    except Exception as e:
        logging.error(f"Failed to check {host}: {e}")

def agestr(delta) -> str:
    total_seconds = int(delta.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if seconds or not parts: parts.append(f"{seconds}s")
    return "".join(parts)

def check_task_execution():
    default_timeout = 12
    try:
        con = sqlite3.connect(str(common.DB_PATH))
        cur = con.cursor()
        cur.execute("SELECT filename, timeout_hours FROM task_status")
        db_tasks = {row[0]: row[1] for row in cur.fetchall()}
        
        found_files = set()

        for status_file in common.LOG_DIR_PATH.glob("*.status"):
            filename = status_file.name
            found_files.add(filename)
            
            timeout = db_tasks.get(filename)
            if timeout is None:
                timeout = default_timeout
                with con:
                    con.execute("INSERT INTO task_status (filename, timeout_hours, last_run, status) VALUES (?, ?, ?, ?)", (filename, timeout, 0, 'new'))
                db_tasks[filename] = timeout

            current_status = 'ok'
            try:
                mtime = datetime.datetime.fromtimestamp(status_file.stat().st_mtime)
                now = datetime.datetime.now()
                if (now - mtime).total_seconds() > timeout * 3600:
                    logging.warning(f"task {filename} stale: last run (updated {agestr(now - mtime)} ago)")
                    with con:
                        con.execute("UPDATE task_status SET last_run = ?, status = 'stale' WHERE filename = ?", (mtime.timestamp(), filename))
                    continue

                for i in range(10):
                    try:
                        content = status_file.read_text(encoding='utf-8').strip()
                        break
                    except Exception:
                        if i == 9: raise
                        time.sleep(3)

                if not content.startswith("0:"):
                    logging.warning(f"task {filename} failed: '{content}' (updated {agestr(now - mtime)} ago)")
                    current_status = 'failed'
                else:
                    logging.info(f"task {filename} successful: '{content}' (updated {agestr(now - mtime)} ago)")
                    current_status = 'ok'
                
                with con:
                    con.execute("UPDATE task_status SET last_run = ?, status = ? WHERE filename = ?", (mtime.timestamp(), current_status, filename))
            except Exception as ex:
                logging.error(f"Error checking {filename}: {ex}")
                with con:
                    con.execute("UPDATE task_status SET status = ? WHERE filename = ?", (f"error: {str(ex)}", filename))

        for filename in db_tasks:
            if filename not in found_files:
                logging.warning(f"task {filename} status file missing")
                with con:
                    con.execute("UPDATE task_status SET status = 'missing' WHERE filename = ?", (filename,))
        
        cur.execute("SELECT filename, status FROM task_status WHERE status != 'ok'")
        rows = cur.fetchall()
        if rows:
            msg = f"Task {rows[0][0]}: {rows[0][1]}"
            if len(rows) > 1:
                msg += f" ({len(rows) - 1} more...)"
            common.show_warning(msg)

        con.close()
    except Exception as ex:
        logging.exception("check_task_execution failed")

def get_fixed_drives():
    drives = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            drive = f"{letter}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(drive) == 3:
                drives.append(drive)
        bitmask >>= 1
    return drives

def verify_file_checksum(checksum_file):
    base_dir = os.path.dirname(checksum_file)
    try:
        with open(checksum_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        logging.error(f"Failed to read checksum file {checksum_file}: {e}")
        return False

    all_ok = True
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'): continue
        
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        
        expected_hash = parts[0].lower()
        filename = parts[1].lstrip('*')
        
        target_path = os.path.join(base_dir, filename)
        if not os.path.exists(target_path):
            logging.error(f"File missing for checksum: {target_path}")
            all_ok = False
            continue
            
        try:
            sha256 = hashlib.sha256()
            with open(target_path, 'rb') as tf:
                while chunk := tf.read(8192 * 1024):
                    sha256.update(chunk)
            calculated_hash = sha256.hexdigest().lower()
            
            if calculated_hash != expected_hash:
                logging.error(f"Checksum mismatch for {target_path}")
                all_ok = False
        except Exception as e:
            logging.error(f"Error verifying {target_path}: {e}")
            all_ok = False
            
    return all_ok

def check_checksums():
    try:
        con = sqlite3.connect(str(common.DB_PATH))
        cur = con.cursor()
        
        drives = get_fixed_drives()

        # find new local checksum files and add them to the db
        with con:
            for drive in drives:
                patterns = [os.path.join(drive, "*_sha256"), os.path.join(drive, "*.sha256")]
                for pattern in patterns:
                    for filepath in glob.glob(pattern):
                        con.execute("INSERT OR IGNORE INTO checksum_files (path, last_check, status, host) VALUES (?, 0, 'pending', '')", (filepath,))

        cur.execute("SELECT path, last_check, status, host FROM checksum_files")
        all_files = cur.fetchall()
        
        ssh_key = get_ssh_key_path()

        for row in all_files:
            path, last_check, status, host = row
            
            needs_check = False
            if status != 'ok':
                needs_check = True
            else:
                try:
                    if time.time() - float(last_check) > 7 * 86400:
                        needs_check = True
                except (ValueError, TypeError):
                    needs_check = True
            
            if not needs_check:
                continue

            new_status = 'failed'
            
            if not host:
                if not os.path.exists(path):
                    new_status = 'missing'
                else:
                    logging.info(f"Verifying local checksums in {path}...")
                    if verify_file_checksum(path):
                        new_status = 'ok'
                    else:
                        new_status = 'failed'
            else:
                logging.info(f"Verifying remote checksums in {path} on {host}...")

                remote_cmd = f'cd "{Path(path).parent.as_posix()}" && sha256sum -c "{Path(path).name}"'
                cmd = _get_ssh_cmd(host, key_file=ssh_key, remote_cmd=remote_cmd)
                
                try:
                    startupinfo = None
                    if sys.platform == 'win32':
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    
                    res = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, timeout=300)
                    
                    if res.returncode == 0:
                        new_status = 'ok'
                        logging.info(f"Remote checksum passed: {path}")
                    else:
                        new_status = 'failed'
                        logging.warning(f"Remote checksum failed: {path}\n{res.stderr}")
                except Exception as e:
                    logging.error(f"Remote verification error for {path}: {e}")
                    new_status = 'error'

            with con:
                con.execute("UPDATE checksum_files SET last_check = ?, status = ? WHERE path = ? AND host = ?", (time.time(), new_status, path, host))

        cur.execute("SELECT path, status, host FROM checksum_files WHERE status != 'ok'")
        for row in cur.fetchall():
            p, s, h = row
            prefix = f"Remote ({h})" if h else "Local"
            common.show_warning(f"Checksum validation failed [{prefix}]: {p} ({s})")

        con.close()
    except Exception as ex:
        logging.exception("check_checksums failed")

def get_monitored_hosts():
    hosts = []
    try:
        con = sqlite3.connect(str(common.DB_PATH))
        cur = con.cursor()
        cur.execute("SELECT host, battery_threshold, storage_threshold, port FROM hosts")
        hosts = cur.fetchall()
        con.close()
    except Exception as e:
        logging.error(f"Failed to get hosts from DB: {e}")
    return hosts

def get_ssh_key_path():
    key_path = None
    try:
        con = sqlite3.connect(str(common.DB_PATH))
        cur = con.cursor()
        cur.execute("SELECT value FROM settings WHERE key = 'ssh_key_path'")
        row = cur.fetchone()
        if row:
            key_path = row[0]
        con.close()
    except Exception:
        pass
    return key_path