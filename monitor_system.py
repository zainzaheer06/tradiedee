#!/usr/bin/env python3
"""
System Monitor for LiveKit Voice Agent Application
Monitors RAM and CPU utilization of all running components
"""

import psutil
import time
import os
import sys
from datetime import datetime
from pathlib import Path


class SystemMonitor:
    def __init__(self):
        self.process_names = [
            "agent.py",
            "agent-inbound.py",
            "campaign_worker.py",
            "app.py"
        ]

    def get_process_info(self, process):
        """Get CPU and memory info for a process"""
        try:
            # Get process info
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)  # Convert to MB

            return {
                'pid': process.pid,
                'name': process.name(),
                'cpu_percent': cpu_percent,
                'memory_mb': memory_mb,
                'status': process.status()
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def find_app_processes(self):
        """Find all processes related to the application"""
        app_processes = []

        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline:
                    cmdline_str = ' '.join(cmdline)
                    # Check if any of our process names are in the command line
                    for app_name in self.process_names:
                        if app_name in cmdline_str:
                            app_processes.append(proc)
                            break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return app_processes

    def get_system_stats(self):
        """Get overall system statistics"""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        return {
            'cpu_percent': cpu_percent,
            'memory_total_mb': memory.total / (1024 * 1024),
            'memory_used_mb': memory.used / (1024 * 1024),
            'memory_percent': memory.percent
        }

    def display_stats(self, clear_screen=True):
        """Display current statistics"""
        if clear_screen:
            os.system('cls' if os.name == 'nt' else 'clear')

        print("=" * 80)
        print(f"🔍 LiveKit Voice Agent System Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        # System-wide stats
        sys_stats = self.get_system_stats()
        print("\n📊 SYSTEM RESOURCES:")
        print(f"   CPU Usage:    {sys_stats['cpu_percent']:.1f}%")
        print(f"   RAM Usage:    {sys_stats['memory_used_mb']:.1f} MB / {sys_stats['memory_total_mb']:.1f} MB ({sys_stats['memory_percent']:.1f}%)")

        # Application processes
        app_processes = self.find_app_processes()

        if not app_processes:
            print("\n⚠️  No application processes found!")
            print("   Make sure the application is running (python start_system.py)")
        else:
            print(f"\n🤖 APPLICATION PROCESSES ({len(app_processes)} running):")
            print("-" * 80)
            print(f"{'PROCESS NAME':<30} {'PID':<10} {'CPU %':<10} {'RAM (MB)':<12} {'STATUS':<10}")
            print("-" * 80)

            total_cpu = 0
            total_memory = 0

            for proc in app_processes:
                info = self.get_process_info(proc)
                if info:
                    # Extract process name from cmdline
                    try:
                        cmdline = proc.cmdline()
                        process_display_name = "Unknown"
                        for name in self.process_names:
                            if name in ' '.join(cmdline):
                                process_display_name = name
                                break
                    except:
                        process_display_name = info['name']

                    print(f"{process_display_name:<30} {info['pid']:<10} {info['cpu_percent']:<10.1f} {info['memory_mb']:<12.1f} {info['status']:<10}")
                    total_cpu += info['cpu_percent']
                    total_memory += info['memory_mb']

            print("-" * 80)
            print(f"{'TOTAL':<30} {'':<10} {total_cpu:<10.1f} {total_memory:<12.1f}")

        print("\n" + "=" * 80)
        print("Press Ctrl+C to stop monitoring")
        print("=" * 80)

    def monitor_continuous(self, interval=2):
        """Continuously monitor and display stats"""
        print("Starting system monitor...")
        print(f"Refresh interval: {interval} seconds")
        time.sleep(1)

        try:
            while True:
                self.display_stats()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n✅ Monitoring stopped")

    def monitor_once(self):
        """Display stats once and exit"""
        self.display_stats(clear_screen=False)


def main():
    monitor = SystemMonitor()

    # Check if we want continuous monitoring or single snapshot
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        monitor.monitor_once()
    else:
        # Default to continuous monitoring
        interval = 2  # seconds
        if len(sys.argv) > 1:
            try:
                interval = int(sys.argv[1])
            except ValueError:
                print(f"Invalid interval. Using default: {interval} seconds")

        monitor.monitor_continuous(interval)


if __name__ == "__main__":
    main()
