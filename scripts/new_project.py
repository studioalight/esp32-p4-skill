#!/usr/bin/env python3
"""
esp32-p4 new-project - Create project from template

Clones the P4 display template and renames project components.
"""

import argparse
import subprocess
import sys
import os
import re
from pathlib import Path

TEMPLATE_REPO = "https://github.com/studioalight/esp32-p4-display-template.git"

# Get OpenClaw workspace root
OPENCLAW_WORKSPACE = Path(os.environ.get('OPENCLAW_WORKSPACE', os.path.expanduser('~/.openclaw/workspace')))

def main():
    parser = argparse.ArgumentParser(description='Create new ESP32-P4 project from template')
    parser.add_argument('--name', '-n', required=True, help='Project name (directory + IDF project name)')
    parser.add_argument('--workspace', '-w', 
                        default=os.path.expanduser('~/.openclaw/workspace/projects/esp32-p4-projects'), 
                        help='Parent directory for projects (default: ~/.openclaw/workspace/projects/esp32-p4-projects)')
    parser.add_argument('--keep-name', action='store_true', 
                        help='Keep HelloWorld as project name (directory only)')
    args = parser.parse_args()
    
    # Sanitize project name for filesystem and CMake
    project_name = args.name.replace(' ', '-').replace('_', '-')
    
    # Resolve workspace path
    workspace_arg = Path(args.workspace)
    if not workspace_arg.is_absolute():
        # Check if it's explicitly relative to CWD (./) vs relative path without ./
        if str(workspace_arg).startswith('./'):
            # Strip ./ and resolve relative to current working directory
            workspace = Path.cwd() / str(workspace_arg)[2:]
        else:
            # Relative path without ./ - resolve relative to CWD
            workspace = Path.cwd() / workspace_arg
    else:
        workspace = workspace_arg.expanduser().resolve()
    
    project_path = workspace / project_name
    
    # Check if directory already exists
    if project_path.exists():
        print(f"Error: Directory already exists: {project_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Creating new project: {project_name}")
    print(f"Location: {project_path}")
    print(f"Template: {TEMPLATE_REPO}")
    print()
    
    # Create workspace if needed
    workspace.mkdir(parents=True, exist_ok=True)
    
    # Clone template
    print("→ Cloning template...")
    result = subprocess.run(
        ['git', 'clone', TEMPLATE_REPO, str(project_path)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error: Clone failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    
    # Remove .git to detach from template history
    git_dir = project_path / '.git'
    if git_dir.exists():
        import shutil
        shutil.rmtree(git_dir)
    
    # Rename project in CMakeLists.txt (unless --keep-name)
    cmake_file = project_path / 'CMakeLists.txt'
    if cmake_file.exists() and not args.keep_name:
        print(f"→ Updating CMakeLists.txt: project({project_name})...")
        content = cmake_file.read_text()
        # Replace project(HelloWorld) with project(new-name)
        content = re.sub(r'project\s*\(\s*HelloWorld\s*\)', f'project({project_name})', content)
        cmake_file.write_text(content)
    
    # Update SKILLS.md reference if it exists
    skill_doc = project_path / 'SKILL.md'
    if skill_doc.exists():
        print("→ Updating SKILL.md...")
        content = skill_doc.read_text()
        content = content.replace('HelloWorld', project_name)
        content = content.replace('esp32-p4-display-template', project_name)
        skill_doc.write_text(content)
    
    # Initialize fresh git repo
    print("→ Initializing git repository...")
    subprocess.run(['git', 'init'], cwd=project_path, capture_output=True)
    subprocess.run(['git', 'add', '.'], cwd=project_path, capture_output=True)
    subprocess.run(['git', 'commit', '-m', f'Initial commit: {project_name}'], 
                   cwd=project_path, capture_output=True)
    
    # Success
    print("\n✓ Project created successfully!")
    print()
    print(f"Next steps:")
    print(f"  cd {project_path}")
    print(f"  source ~/esp-idf-v5.4/export.sh")
    print(f"  idf.py set-target esp32p4")
    print(f"  idf.py build")
    print()
    if args.keep_name:
        print("Note: Kept original project name 'HelloWorld' (use --keep-name)")
    else:
        print(f"Project name set to: {project_name}")
        print(f"Build output will be: build/{project_name}.bin")
    
    # Show size hint
    print(f"\nOr use the skill:")
    print(f"  esp32-p4 build --project {project_path}")

if __name__ == '__main__':
    main()
