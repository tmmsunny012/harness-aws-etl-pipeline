#!/usr/bin/env python3
"""
Lambda Package Builder
======================
Builds the Lambda deployment package with dependencies.
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
ETL_DIR = PROJECT_ROOT / "etl"
BUILD_DIR = PROJECT_ROOT / "build"
LAMBDA_PACKAGE_DIR = BUILD_DIR / "lambda_package"
OUTPUT_ZIP = BUILD_DIR / "lambda_function.zip"


def clean_build():
    """Clean previous build artifacts."""
    print("Cleaning previous build...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)


def install_dependencies():
    """Install Lambda dependencies."""
    print("Installing dependencies...")
    LAMBDA_PACKAGE_DIR.mkdir(parents=True, exist_ok=True)

    requirements_file = ETL_DIR / "requirements-lambda.txt"

    # Install to package directory (Linux compatible for Lambda)
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "-r", str(requirements_file),
        "-t", str(LAMBDA_PACKAGE_DIR),
        "--platform", "manylinux2014_x86_64",
        "--implementation", "cp",
        "--python-version", "3.9",
        "--only-binary=:all:",
        "--upgrade"
    ], check=True)

    # Clean up unnecessary files
    print("Cleaning up package...")
    patterns_to_remove = [
        "*.dist-info",
        "*.egg-info",
        "__pycache__",
        "tests",
        "test",
        "*.pyc",
        "*.pyo",
    ]

    for pattern in patterns_to_remove:
        for path in LAMBDA_PACKAGE_DIR.rglob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def copy_source_code():
    """Copy ETL source code to package."""
    print("Copying source code...")

    # Copy lambda_handler.py to root
    shutil.copy(ETL_DIR / "lambda_handler.py", LAMBDA_PACKAGE_DIR)

    # Copy src directory
    src_dest = LAMBDA_PACKAGE_DIR / "src"
    if src_dest.exists():
        shutil.rmtree(src_dest)

    shutil.copytree(
        ETL_DIR / "src",
        src_dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    )


def create_zip():
    """Create the Lambda deployment zip."""
    print(f"Creating deployment package: {OUTPUT_ZIP}")

    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(LAMBDA_PACKAGE_DIR):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            for file in files:
                if file.endswith(('.pyc', '.pyo')):
                    continue

                file_path = Path(root) / file
                arcname = file_path.relative_to(LAMBDA_PACKAGE_DIR)
                zf.write(file_path, arcname)

    # Show package size
    size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"Package size: {size_mb:.2f} MB")

    if size_mb > 50:
        print("WARNING: Package exceeds 50MB. Consider using Lambda Layers.")
    if size_mb > 250:
        print("ERROR: Package exceeds 250MB limit. Must use Lambda Layers or container.")
        sys.exit(1)


def main():
    """Build the Lambda deployment package."""
    print("=" * 60)
    print("Building Lambda Deployment Package")
    print("=" * 60)

    clean_build()
    install_dependencies()
    copy_source_code()
    create_zip()

    print("=" * 60)
    print("Build complete!")
    print(f"Output: {OUTPUT_ZIP}")
    print("=" * 60)


if __name__ == "__main__":
    main()
