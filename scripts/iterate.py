#!/usr/bin/env python3
"""
esp32-p4 iterate - Full loop: Build + Upload + Flash + Monitor
"""

import subprocess
import sys
import argparse
import os
from pathlib import Path

# Get OpenClaw workspace root
OPENCLAW_WORKSPACE = Path(os.environ.get('OPENCLAW_WORKSPACE', os.path.expanduser('~/.openclaw/workspace')))

def resolve_project_path(path_str):
    """Resolve project path - handle relative paths and tilde expansion"""
    # Expand tilde first
    path_str = os.path.expanduser(path_str)
    path = Path(path_str)
    
    if path.is_absolute():
        return path.resolve()
    
    if str(path).startswith('./'):
        # ./projects/... means relative to current directory
        return Path.cwd() / str(path)[2:]
    else:
        # Relative without ./ - also relative to current directory
        return Path.cwd() / path

def run_step(name, cmd):
    """Run a step and report"""
    print(f"\n{'='*50}")
    print(f"STEP: {name}")
    print('='*50)
    
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        print(f"\n✗ {name} failed", file=sys.stderr)
        return False
    
    print(f"✓ {name} complete")
    return True

def main():
    parser = argparse.ArgumentParser(description='Full iteration: Build + Upload + Flash + Monitor')
    parser.add_argument('--project', '-p', required=True, help='Project directory (absolute or relative to workspace, e.g., ./projects/esp32-p4-projects/my-project)')
    parser.add_argument('--clean', action='store_true', help='Clean build')
    parser.add_argument('--no-flash', action='store_true', help='Skip flash')
    parser.add_argument('--no-monitor', action='store_true', help='Skip monitor')
    parser.add_argument('--monitor-duration', type=int, default=15, help='Monitor duration in seconds')
    parser.add_argument('--idf-path', default=os.path.expanduser('~/esp-idf-v5.4'), help='ESP-IDF path')
    
    args = parser.parse_args()
    
    # Resolve project path for display
    project_path_resolved = resolve_project_path(args.project)
    scripts_dir = Path(__file__).parent
    
    print("="*50)
    print("ESP32-P4 ITERATION")
    print("Design → Build → Upload → Flash → Verify")
    print(f"Project: {args.project}")
    print(f"Resolved: {project_path_resolved}")
    print("="*50)
    
    # Step 1: Build
    build_cmd = [
        'python3', str(scripts_dir / 'build.py'),
        '--project', args.project,  # Pass original path, build.py will resolve
        '--idf-path', args.idf_path
    ]
    
    if args.clean:
        build_cmd.append('--clean')
    
    if not run_step('BUILD', build_cmd):
        sys.exit(1)
    
    # Step 2: Upload
    upload_cmd = [
        'python3', str(scripts_dir / 'upload.py'),
        '--project', args.project  # Pass original path
    ]
    
    if not run_step('UPLOAD', upload_cmd):
        sys.exit(1)
    
    # Step 3: Flash
    if not args.no_flash:
        flash_cmd = [
            'python3', str(scripts_dir / 'flash.py'),
            '--project', args.project  # Pass original path for version discovery
        ]
        
        if not run_step('FLASH', flash_cmd):
            sys.exit(1)
    
    # Step 4: Monitor
    if not args.no_monitor:
        monitor_cmd = [
            'python3', str(scripts_dir / 'monitor.py'),
            '--duration', str(args.monitor_duration)
        ]
        
        run_step('MONITOR', monitor_cmd)
    
    print("\n" + "="*50)
    print("✓ ITERATION COMPLETE")
    print("="*50)
    
    if not args.no_flash and not args.no_monitor:
        print("\nVerify display is showing expected output.")
    
    print()

if __name__ == '__main__':
    main()
