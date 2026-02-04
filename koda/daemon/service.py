"""Daemon Service - Run Koda as a background service.

Provides functionality to install and manage Koda as a system daemon
on macOS (launchd) and Linux (systemd).
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def get_koda_executable() -> str:
    """Get the path to the koda executable."""
    # Try to find koda in PATH
    koda_path = shutil.which("koda")
    if koda_path:
        return koda_path
    
    # Try python -m koda
    return f"{sys.executable} -m koda"


def get_service_name() -> str:
    """Get the service name."""
    return "com.koda.gateway" if platform.system() == "Darwin" else "koda"


class DaemonManager:
    """
    Manages Koda as a system daemon.
    
    Supports:
    - macOS: launchd (launchctl)
    - Linux: systemd (systemctl)
    """
    
    def __init__(self):
        self.system = platform.system()
        self.service_name = get_service_name()
        self.koda_exec = get_koda_executable()
        
        # Paths
        if self.system == "Darwin":
            self.service_dir = Path.home() / "Library" / "LaunchAgents"
            self.service_file = self.service_dir / f"{self.service_name}.plist"
            self.log_dir = Path.home() / "Library" / "Logs" / "Koda"
        else:
            self.service_dir = Path.home() / ".config" / "systemd" / "user"
            self.service_file = self.service_dir / f"{self.service_name}.service"
            self.log_dir = Path.home() / ".local" / "share" / "koda" / "logs"
    
    def _generate_launchd_plist(self) -> str:
        """Generate macOS launchd plist content."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self.service_name}</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>{self.koda_exec.split()[0]}</string>
        {f'<string>{self.koda_exec.split()[1]}</string>' if len(self.koda_exec.split()) > 1 else ''}
        {f'<string>{self.koda_exec.split()[2]}</string>' if len(self.koda_exec.split()) > 2 else ''}
        <string>gateway</string>
    </array>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    
    <key>StandardOutPath</key>
    <string>{self.log_dir}/koda.log</string>
    
    <key>StandardErrorPath</key>
    <string>{self.log_dir}/koda.error.log</string>
    
    <key>WorkingDirectory</key>
    <string>{Path.home()}</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>{Path.home()}</string>
    </dict>
    
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
'''
    
    def _generate_systemd_unit(self) -> str:
        """Generate Linux systemd unit file content."""
        return f'''[Unit]
Description=Koda AI Assistant Gateway
After=network.target

[Service]
Type=simple
ExecStart={self.koda_exec} gateway
Restart=on-failure
RestartSec=10
WorkingDirectory={Path.home()}

Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="HOME={Path.home()}"

StandardOutput=append:{self.log_dir}/koda.log
StandardError=append:{self.log_dir}/koda.error.log

[Install]
WantedBy=default.target
'''
    
    def install(self) -> tuple[bool, str]:
        """
        Install Koda as a system daemon.
        
        Returns:
            (success, message)
        """
        try:
            # Create directories
            self.service_dir.mkdir(parents=True, exist_ok=True)
            self.log_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate and write service file
            if self.system == "Darwin":
                content = self._generate_launchd_plist()
            else:
                content = self._generate_systemd_unit()
            
            self.service_file.write_text(content)
            logger.info(f"Created service file: {self.service_file}")
            
            # Load/enable the service
            if self.system == "Darwin":
                # Unload first if exists
                subprocess.run(
                    ["launchctl", "unload", str(self.service_file)],
                    capture_output=True
                )
                result = subprocess.run(
                    ["launchctl", "load", str(self.service_file)],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    return False, f"Failed to load service: {result.stderr}"
            else:
                # Reload systemd and enable
                subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
                result = subprocess.run(
                    ["systemctl", "--user", "enable", self.service_name],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    return False, f"Failed to enable service: {result.stderr}"
            
            return True, f"Service installed: {self.service_file}"
            
        except Exception as e:
            logger.error(f"Failed to install daemon: {e}")
            return False, str(e)
    
    def uninstall(self) -> tuple[bool, str]:
        """
        Uninstall the Koda daemon.
        
        Returns:
            (success, message)
        """
        try:
            # Stop first
            self.stop()
            
            if self.system == "Darwin":
                subprocess.run(
                    ["launchctl", "unload", str(self.service_file)],
                    capture_output=True
                )
            else:
                subprocess.run(
                    ["systemctl", "--user", "disable", self.service_name],
                    capture_output=True
                )
            
            # Remove service file
            if self.service_file.exists():
                self.service_file.unlink()
            
            return True, "Service uninstalled"
            
        except Exception as e:
            logger.error(f"Failed to uninstall daemon: {e}")
            return False, str(e)
    
    def start(self) -> tuple[bool, str]:
        """
        Start the Koda daemon.
        
        Returns:
            (success, message)
        """
        try:
            if self.system == "Darwin":
                result = subprocess.run(
                    ["launchctl", "start", self.service_name],
                    capture_output=True,
                    text=True
                )
            else:
                result = subprocess.run(
                    ["systemctl", "--user", "start", self.service_name],
                    capture_output=True,
                    text=True
                )
            
            if result.returncode != 0:
                return False, f"Failed to start: {result.stderr}"
            
            return True, "Service started"
            
        except Exception as e:
            return False, str(e)
    
    def stop(self) -> tuple[bool, str]:
        """
        Stop the Koda daemon.
        
        Returns:
            (success, message)
        """
        try:
            if self.system == "Darwin":
                result = subprocess.run(
                    ["launchctl", "stop", self.service_name],
                    capture_output=True,
                    text=True
                )
            else:
                result = subprocess.run(
                    ["systemctl", "--user", "stop", self.service_name],
                    capture_output=True,
                    text=True
                )
            
            return True, "Service stopped"
            
        except Exception as e:
            return False, str(e)
    
    def restart(self) -> tuple[bool, str]:
        """
        Restart the Koda daemon.
        
        Returns:
            (success, message)
        """
        self.stop()
        return self.start()
    
    def status(self) -> dict:
        """
        Get the status of the Koda daemon.
        
        Returns:
            Status dictionary with running state and info.
        """
        status = {
            "installed": self.service_file.exists(),
            "running": False,
            "service_file": str(self.service_file),
            "log_file": str(self.log_dir / "koda.log"),
            "system": self.system
        }
        
        try:
            if self.system == "Darwin":
                result = subprocess.run(
                    ["launchctl", "list", self.service_name],
                    capture_output=True,
                    text=True
                )
                status["running"] = result.returncode == 0
                if status["running"]:
                    # Parse PID from output
                    for line in result.stdout.split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 1 and parts[0].isdigit():
                            status["pid"] = int(parts[0])
                            break
            else:
                result = subprocess.run(
                    ["systemctl", "--user", "is-active", self.service_name],
                    capture_output=True,
                    text=True
                )
                status["running"] = result.stdout.strip() == "active"
                
                if status["running"]:
                    # Get PID
                    pid_result = subprocess.run(
                        ["systemctl", "--user", "show", self.service_name, "--property=MainPID"],
                        capture_output=True,
                        text=True
                    )
                    if "MainPID=" in pid_result.stdout:
                        status["pid"] = int(pid_result.stdout.split("=")[1].strip())
        except:
            pass
        
        return status
    
    def logs(self, lines: int = 50) -> str:
        """
        Get recent log output.
        
        Args:
            lines: Number of lines to return.
        
        Returns:
            Log content.
        """
        log_file = self.log_dir / "koda.log"
        
        if not log_file.exists():
            return "No logs found"
        
        try:
            with open(log_file) as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except Exception as e:
            return f"Error reading logs: {e}"


# CLI commands for daemon management
def install_daemon() -> None:
    """Install Koda as a system daemon."""
    manager = DaemonManager()
    success, message = manager.install()
    
    if success:
        print(f"✅ {message}")
        print(f"\nKoda will now start automatically on login.")
        print(f"Logs: {manager.log_dir}")
        print(f"\nCommands:")
        print(f"  koda daemon start   - Start the service")
        print(f"  koda daemon stop    - Stop the service")
        print(f"  koda daemon status  - Check status")
        print(f"  koda daemon logs    - View logs")
    else:
        print(f"❌ Installation failed: {message}")
        sys.exit(1)


def uninstall_daemon() -> None:
    """Uninstall the Koda daemon."""
    manager = DaemonManager()
    success, message = manager.uninstall()
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ Uninstall failed: {message}")
        sys.exit(1)


def daemon_status() -> None:
    """Show daemon status."""
    manager = DaemonManager()
    status = manager.status()
    
    print("🐕 Koda Daemon Status")
    print("=" * 40)
    print(f"System:    {status['system']}")
    print(f"Installed: {'✅ Yes' if status['installed'] else '❌ No'}")
    print(f"Running:   {'✅ Yes' if status['running'] else '❌ No'}")
    
    if status.get("pid"):
        print(f"PID:       {status['pid']}")
    
    print(f"\nService:   {status['service_file']}")
    print(f"Logs:      {status['log_file']}")


def daemon_logs(lines: int = 50) -> None:
    """Show daemon logs."""
    manager = DaemonManager()
    print(manager.logs(lines))
