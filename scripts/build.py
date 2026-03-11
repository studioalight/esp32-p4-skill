#!/usr/bin/env python3
"""
esp32-p4 build - Compile ESP32-PF projects in container

Generates version header with git commit info before building.
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

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

def get_git_info(project_path):
    """Get git commit hash and date"""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=project_path, capture_output=True, text=True
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
            # Check if dirty
            dirty_result = subprocess.run(
                ['git', 'diff', '--quiet'],
                cwd=project_path, capture_output=True
            )
            if dirty_result.returncode != 0:
                commit += '-dirty'
            return commit
    except Exception:
        pass
    return 'unknown'

def generate_version_header(project_path, project_name):
    """Generate version.h with build info"""
    git_commit = get_git_info(project_path)
    build_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    version_content = f'''/* Auto-generated version header */
#ifndef VERSION_H
#define VERSION_H

#define PROJECT_NAME "{project_name}"
#define GIT_COMMIT "{git_commit}"
#define BUILD_TIME "{build_time}"

#endif /* VERSION_H */
'''
    
    # Create components/version directory
    version_component = project_path / 'components' / 'version'
    version_component.mkdir(parents=True, exist_ok=True)
    
    # Write header
    (version_component / 'version.h').write_text(version_content)
    
    # Write CMakeLists.txt for the component if it doesn't exist
    cmake_file = version_component / 'CMakeLists.txt'
    if not cmake_file.exists():
        cmake_file.write_text('idf_component_register(INCLUDE_DIRS ".")\n')
    
    return git_commit

def main():
    parser = argparse.ArgumentParser(description='Build ESP32-P4 project')
    parser.add_argument('--project', '-p', required=True, help='Project directory (absolute or relative to workspace)')
    parser.add_argument('--clean', action='store_true', help='Clean build first')
    parser.add_argument('--target', default='esp32p4', help='Target chip (default: esp32p4)')
    parser.add_argument('--idf-path', default=os.path.expanduser('~/esp-idf-v5.4'), help='ESP-IDF path')
    args = parser.parse_args()
    
    # Resolve project path
    project_path = resolve_project_path(args.project)
    
    if not project_path.exists():
        print(f"Error: Project not found: {project_path}", file=sys.stderr)
        sys.exit(1)
    
    # Extract project name from CMakeLists.txt
    project_name = "project"
    cmake_file = project_path / 'CMakeLists.txt'
    if cmake_file.exists():
        content = cmake_file.read_text()
        import re
        match = re.search(r'project\s*\(\s*([\w-]+)', content)
        if match:
            project_name = match.group(1)
    
    # Generate version header
    print(f"Project: {project_name}")
    git_commit = generate_version_header(project_path, project_name)
    print(f"Git commit: {git_commit}")
    
    # Build command
    cmd = f"""
source {args.idf_path}/export.sh && \
cd {project_path} && \
{'rm -rf build && ' if args.clean else ''}
# Ensure target is set (critical for ESP32-P4)
if [ ! -f sdkconfig ] || ! grep -q "CONFIG_IDF_TARGET=\\"{args.target}\\"" sdkconfig 2>/dev/null; then
    idf.py set-target {args.target}
fi && \
idf.py build
"""
    
    print(f"Building: {project_path}")
    print(f"Target: {args.target}")
    if args.clean:
        print("Clean build requested")
    print()
    
    result = subprocess.run(cmd, shell=True, executable='/bin/bash')
    
    if result.returncode == 0:
        print("\n✓ Build successful!")
        
        # Find the output binary (ESP-IDF names it after the project)
        build_dir = project_path / 'build'
        expected_app = build_dir / f"{project_name}.bin"
        
        if expected_app.exists():
            size = expected_app.stat().st_size
            print(f"  build/{expected_app.name}: {size:,} bytes")
            
            # Create versioned copy
            if git_commit != 'unknown':
                versioned_name = f"{project_name}-{git_commit}.bin"
                versioned_path = build_dir / versioned_name
                if not versioned_path.exists():
                    import shutil
                    shutil.copy2(expected_app, versioned_path)
                    print(f"  {versioned_name}: {size:,} bytes (versioned)")
                else:
                    print(f"  {versioned_name}: already exists")
            
            print(f"\nReady: esp32-p4 upload --project {args.project}")
        else:
            print(f"\nReady: esp32-p4 upload --project {args.project}")
    else:
        print("\n✗ Build failed", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
