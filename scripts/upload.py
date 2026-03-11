#!/usr/bin/env python3
"""
esp32-p4 upload - Upload binaries to bridge via HTTP
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
import json

BRIDGE_URL = "https://esp32-bridge.tailbdd5a.ts.net:5679"

# Get OpenClaw workspace root
OPENCLAW_WORKSPACE = Path(os.environ.get('OPENCLAW_WORKSPACE', os.path.expanduser('~/.openclaw/workspace')))

def resolve_project_path(path_str):
    """Resolve project path - handle relative to workspace"""
    path = Path(path_str)
    if not path.is_absolute():
        if str(path).startswith('./'):
            return OPENCLAW_WORKSPACE / str(path)[2:]
        else:
            return OPENCLAW_WORKSPACE / path
    return path.expanduser().resolve()

def upload_file(filepath, dest_name=None):
    """Upload single file to bridge"""
    filepath = Path(filepath)
    dest = dest_name if dest_name else filepath.name
    cmd = [
        'curl', '-k', '-s',
        '-F', f'file=@{filepath};filename={dest}',
        f'{BRIDGE_URL}/upload'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            if data.get('success'):
                print(f"✓ Uploaded: {dest} ({data['size']:,} bytes)")
                return True
        except json.JSONDecodeError:
            pass
    
    print(f"✗ Upload failed: {filepath}", file=sys.stderr)
    print(f"  Response: {result.stdout}", file=sys.stderr)
    return False

def main():
    parser = argparse.ArgumentParser(description='Upload binaries to bridge')
    parser.add_argument('--project', '-p', help='Project directory (absolute or relative to workspace)')
    parser.add_argument('--file', '-f', help='Single file to upload')
    parser.add_argument('--list', '-l', action='store_true', help='List uploaded files')
    args = parser.parse_args()
    
    if args.list:
        subprocess.run(['curl', '-k', '-s', f'{BRIDGE_URL}/files'])
        return
    
    if args.file:
        upload_file(args.file)
    
    elif args.project:
        project_path = resolve_project_path(args.project)
        build_dir = project_path / 'build'
        
        # Find the application binary (not bootloader or partition table)
        bin_files = list(build_dir.glob('*.bin'))
        app_bins = [f for f in bin_files 
                    if f.name not in ['bootloader.bin', 'partition-table.bin']]
        
        if app_bins:
            # Prefer versioned binary (has git hash in name) over plain binary
            # Sort: first by whether name contains '-' (versioned), then by size
            versioned_bins = [f for f in app_bins if '-' in f.name]
            if versioned_bins:
                # Among versioned, pick the one with longest name (most specific)
                versioned_bins.sort(key=lambda f: len(f.name), reverse=True)
                app_bin_path = versioned_bins[0]
            else:
                # No versioned found, use largest by size
                app_bins.sort(key=lambda f: f.stat().st_size, reverse=True)
                app_bin_path = app_bins[0]
            app_bin_name = app_bin_path.name
        else:
            app_bin_path = build_dir / 'HelloWorld.bin'
            app_bin_name = 'HelloWorld.bin'
        
        files = [
            (build_dir / 'bootloader' / 'bootloader.bin', 'bootloader.bin'),
            (build_dir / 'partition_table' / 'partition-table.bin', 'partition-table.bin'),
            (app_bin_path, app_bin_name)  # Use actual versioned name
        ]
        
        print(f"Uploading from: {project_path}")
        print(f"Application binary: {app_bin_name}")
        print()
        
        for filepath, dest_name in files:
            if filepath.exists():
                print(f"Uploading {dest_name}...")
                upload_file(filepath, dest_name)
            else:
                print(f"⚠ Not found: {filepath}")
        
        print("\nReady to flash: esp32-p4 flash")
    
    else:
        print("Error: Specify --project or --file", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
