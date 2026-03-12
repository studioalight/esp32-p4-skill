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

def resolve_project_path(path_str):
    """Resolve project path - handle relative paths and tilde expansion"""
    # Expand tilde first
    path_str = os.path.expanduser(path_str)
    path = Path(path_str)
    
    if path.is_absolute():
        return path.resolve()
    
    if str(path).startswith('./'):
        return Path.cwd() / str(path)[2:]
    else:
        return Path.cwd() / path

def get_files_from_flash_manifest(build_dir):
    """Get list of files to upload from ESP-IDF build manifest"""
    flash_args = build_dir / 'flash_args'
    flasher_json = build_dir / 'flasher_args.json'
    
    files = []
    
    # Try flash_args file (ESP-IDF format: 0xADDR path/to/file.bin)
    if flash_args.exists():
        print("Found flash_args manifest")
        with open(flash_args) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Parse "0x2000 bootloader/bootloader.bin" format
                parts = line.split(maxsplit=1)
                if len(parts) >= 2 and parts[0].startswith('0x'):
                    filepath = parts[1]
                    filename = os.path.basename(filepath)
                    
                    # Check for versioned version of app binary (not bootloader/partition)
                    is_system = any(x in filename.lower() for x in ['bootloader', 'partition'])
                    if not is_system:
                        name_base = filename.replace('.bin', '')
                        versioned_files = list(build_dir.glob(f"{name_base}-*.bin"))
                        versioned_files = [f for f in versioned_files if '-' in f.name]
                        if versioned_files:
                            versioned_files.sort(key=lambda f: len(f.name), reverse=True)
                            filename = versioned_files[0].name
                            full_path = build_dir / filename
                            files.append((full_path, filename))
                            continue
                    
                    # Check if file exists in build dir
                    full_path = build_dir / filename
                    if full_path.exists():
                        files.append((full_path, filename))
                    else:
                        for subdir in ['bootloader', 'partition_table']:
                            alt_path = build_dir / subdir / filename
                            if alt_path.exists():
                                files.append((alt_path, filename))
                                break
    
    elif flasher_json.exists():
        print("Found flasher_args.json manifest")
        with open(flasher_json) as f:
            data = json.load(f)
            for entry in data.get('flash_files', []):
                filename = os.path.basename(entry['path'])
                full_path = build_dir / filename
                if full_path.exists():
                    files.append((full_path, filename))
                else:
                    for subdir in ['bootloader', 'partition_table']:
                        alt_path = build_dir / subdir / filename
                        if alt_path.exists():
                            files.append((alt_path, filename))
                            break
    
    # Fallback to pattern matching
    else:
        print("No flash manifest found, scanning for binaries...")
        bin_files = list(build_dir.glob('*.bin'))
        for subdir in ['bootloader', 'partition_table']:
            subdir_path = build_dir / subdir
            if subdir_path.exists():
                bin_files.extend(subdir_path.glob('*.bin'))
        for bin_file in bin_files:
            files.append((bin_file, bin_file.name))
    
    # Sort: bootloader first, partition table second
    def sort_key(item):
        path, name = item
        if 'bootloader' in name.lower():
            return (0, name)
        elif 'partition' in name.lower():
            return (1, name)
        else:
            return (2, name)
    
    return sorted(files, key=sort_key)

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
    parser.add_argument('--project', '-p', help='Project directory')
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
        
        # Get files from ESP-IDF flash manifest
        files = get_files_from_flash_manifest(build_dir)
        
        print(f"Uploading from: {project_path}")
        print(f"Files: {len(files)}")
        print()
        
        for filepath, filename in files:
            if filepath.exists():
                print(f"Uploading {filename}...")
                upload_file(filepath, filename)
            else:
                print(f"⚠ Not found: {filepath}")
        
        print("\nReady to flash: esp32-p4 flash")
    
    else:
        print("Error: Specify --project or --file", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
