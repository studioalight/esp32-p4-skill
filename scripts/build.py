#!/usr/bin/env python3
"""
esp32-p4 build - Compile ESP32-PF projects in container

Generates version header with git commit info before building.
Configures chip revision compatibility for early P4 samples.
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

def resolve_project_path(path_str):
    """Resolve project path - handle relative paths"""
    path = Path(path_str)
    if not path.is_absolute():
        if str(path).startswith('./'):
            return Path.cwd() / str(path)[2:]
        else:
            return Path.cwd() / path
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
    
    version_component = project_path / 'components' / 'version'
    version_component.mkdir(parents=True, exist_ok=True)
    (version_component / 'version.h').write_text(version_content)
    cmake_file = version_component / 'CMakeLists.txt'
    if not cmake_file.exists():
        cmake_file.write_text('idf_component_register(INCLUDE_DIRS ".")\n')
    
    return git_commit

def configure_chip_revision(project_path):
    """Configure chip revision compatibility for early P4 samples (v1.0)"""
    sdkconfig_path = project_path / 'sdkconfig'
    
    if not sdkconfig_path.exists():
        return False
    
    content = sdkconfig_path.read_text()
    
    # Check if revision already configured
    if 'CONFIG_ESP32P4_REV_MIN_' in content:
        return False
    
    # Add v1.0 revision compatibility
    revision_config = """
# Chip revision compatibility for early P4 samples (v1.0)
CONFIG_ESP32P4_REV_MIN_100=y
CONFIG_ESP32P4_REV_MIN_FULL=100
CONFIG_ESP_REV_MIN_FULL=100
CONFIG_ESP_EFUSE_BLOCK_REV_MIN_FULL=0
"""
    
    with open(sdkconfig_path, 'a') as f:
        f.write(revision_config)
    
    print("  Configured chip revision for v1.0 compatibility")
    return True

def main():
    parser = argparse.ArgumentParser(description='Build ESP32-P4 project')
    parser.add_argument('--project', '-p', required=True, help='Project directory')
    parser.add_argument('--clean', action='store_true', help='Clean build first')
    parser.add_argument('--target', default='esp32p4', help='Target chip (default: esp32p4)')
    parser.add_argument('--idf-path', default=os.path.expanduser('~/esp-idf-v5.4'), help='ESP-IDF path')
    args = parser.parse_args()
    
    project_path = resolve_project_path(args.project)
    
    if not project_path.exists():
        print(f"Error: Project not found: {project_path}", file=sys.stderr)
        sys.exit(1)
    
    # Extract project name
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
    
    # Run set-target if needed
    sdkconfig = project_path / 'sdkconfig'
    target_set = False
    if not sdkconfig.exists():
        print(f"Setting target: {args.target}")
        result = subprocess.run(
            f'source {args.idf_path}/export.sh && cd {project_path} && idf.py set-target {args.target}',
            shell=True, executable='/bin/bash'
        )
        if result.returncode != 0:
            print("✗ set-target failed", file=sys.stderr)
            sys.exit(1)
        target_set = True
    else:
        with open(sdkconfig) as f:
            if f'CONFIG_IDF_TARGET="{args.target}"' not in f.read():
                print(f"Setting target: {args.target}")
                result = subprocess.run(
                    f'source {args.idf_path}/export.sh && cd {project_path} && idf.py set-target {args.target}',
                    shell=True, executable='/bin/bash'
                )
                if result.returncode != 0:
                    print("✗ set-target failed", file=sys.stderr)
                    sys.exit(1)
                target_set = True
    
    # Configure chip revision for v1.0 compatibility
    if target_set or sdkconfig.exists():
        configure_chip_revision(project_path)
    
    # Clean if requested
    if args.clean:
        print("Clean build requested")
        subprocess.run(
            f'source {args.idf_path}/export.sh && cd {project_path} && rm -rf build',
            shell=True, executable='/bin/bash'
        )
    
    # Build
    print(f"Building: {project_path}")
    print(f"Target: {args.target}")
    result = subprocess.run(
        f'source {args.idf_path}/export.sh && cd {project_path} && idf.py build',
        shell=True, executable='/bin/bash'
    )
    
    if result.returncode == 0:
        print("\n✓ Build successful!")
        build_dir = project_path / 'build'
        expected_app = build_dir / f"{project_name}.bin"
        
        if expected_app.exists():
            size = expected_app.stat().st_size
            print(f"  build/{expected_app.name}: {size:,} bytes")
            
            if git_commit != 'unknown':
                versioned_name = f"{project_name}-{git_commit}.bin"
                versioned_path = build_dir / versioned_name
                if not versioned_path.exists():
                    import shutil
                    shutil.copy2(expected_app, versioned_path)
                    print(f"  {versioned_name}: {size:,} bytes (versioned)")
            
            print(f"\nReady: esp32-p4 upload --project {args.project}")
    else:
        print("\n✗ Build failed", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
