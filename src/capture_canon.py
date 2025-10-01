#!/usr/bin/env python3
"""
Canon rapid-capture helper for building a Pokémon TCG detection dataset.

This script:
  • Controls your Canon camera via gphoto2
  • Lets you set how many photos to take (--frames), how fast (--interval),
    and where to save them (--outdir)
  • Saves files as <prefix>_YYYYmmdd-HHMMSS_###.jpg

If gphoto2 isn’t found, the script will try to guide you through installation.
"""

import argparse
import datetime as dt
import shutil
import subprocess
import sys
import platform
from pathlib import Path


def install_gphoto2():
    """Try to help the user install gphoto2 based on their OS."""
    os_name = platform.system().lower()
    if "darwin" in os_name:  # macOS
        print("\n--- gphoto2 missing ---")
        print("Attempting to install gphoto2 with Homebrew...")
        try:
            subprocess.run(["brew", "install", "gphoto2"], check=True)
            print("✅ Installed gphoto2. Re-run this script.")
        except Exception as e:
            print("❌ Failed to install gphoto2 with brew.")
            print("Make sure Homebrew is installed (https://brew.sh), then run:")
            print("    brew install gphoto2")
    elif "linux" in os_name:
        print("\n--- gphoto2 missing ---")
        print("Attempting to install gphoto2 with apt (Debian/Ubuntu)...")
        try:
            subprocess.run(
                ["sudo", "apt-get", "update"], check=True
            )
            subprocess.run(
                ["sudo", "apt-get", "install", "-y", "gphoto2"], check=True
            )
            print("✅ Installed gphoto2. Re-run this script.")
        except Exception as e:
            print("❌ Failed to install gphoto2 automatically.")
            print("On Ubuntu/Debian, try:")
            print("    sudo apt-get update && sudo apt-get install gphoto2")
    else:
        print("\n--- gphoto2 missing ---")
        print("⚠️ Automatic install not supported for your OS.")
        print("Install manually: https://gphoto.org/ or use your system’s package manager.")
    sys.exit(1)


def check_gphoto2():
    """Ensure gphoto2 is available, or attempt to install it."""
    if shutil.which("gphoto2") is None:
        install_gphoto2()


def ensure_camera_detected():
    """Check that gphoto2 can see your camera."""
    try:
        out = subprocess.check_output(["gphoto2", "--auto-detect"], text=True)
    except subprocess.CalledProcessError:
        sys.exit("Error: 'gphoto2 --auto-detect' failed. Is the camera connected and turned on?")
    if "usb:" not in out.lower():
        print(out.strip())
        sys.exit(
            "No camera detected.\n"
            "- Check the USB cable/port\n"
            "- Disable Wi-Fi on the camera\n"
            "- Set the camera to PHOTO mode\n"
            "- Try again"
        )


def build_filename_template(outdir: Path, prefix: str) -> str:
    """Return gphoto2 filename template with timestamp + counter."""
    template = f"{prefix}_%Y%m%d-%H%M%S_%03n.jpg"
    return str((outdir / template).as_posix())


def maybe_set_capture_target(keep_on_camera: bool):
    """If requested, set capturetarget=1 (save to camera card too)."""
    if not keep_on_camera:
        return
    try:
        subprocess.run(
            ["gphoto2", "--set-config", "capturetarget=1"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Rapid Canon capture via gphoto2 for dataset collection."
    )
    parser.add_argument("--frames", type=int, default=100,
                        help="Number of photos (default: 100)")
    parser.add_argument("--interval", type=float, default=1.5,
                        help="Seconds between shots (default: 1.5)")
    parser.add_argument("--outdir", type=str, default="datasets/cards/images/train",
                        help="Directory to save (default: datasets/cards/images/train)")
    parser.add_argument("--prefix", type=str, default="shot",
                        help="Filename prefix (default: shot)")
    parser.add_argument("--keep-on-camera", action="store_true",
                        help="Keep photos on camera card as well (if supported)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print command but don’t capture")
    args = parser.parse_args()

    # 1) Check deps & camera
    check_gphoto2()
    ensure_camera_detected()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    maybe_set_capture_target(args.keep_on_camera)
    filename_template = build_filename_template(outdir, args.prefix)

    cmd = [
        "gphoto2",
        "--capture-image-and-download",
        f"--frames={args.frames}",
        f"--interval={args.interval}",
        f"--filename={filename_template}",
        "--force-overwrite",
    ]

    print("\n=== Canon Rapid Capture ===")
    print("Frames   :", args.frames)
    print("Interval :", args.interval, "sec")
    print("Output   :", outdir.resolve())
    print("Prefix   :", args.prefix)
    print("Command  :", " ".join(cmd))
    print("Tip: rearrange cards every few shots for dataset diversity.")
    print("Press Ctrl+C to stop early.\n")

    if args.dry_run:
        print("Dry-run complete. No photos taken.")
        return

    start = dt.datetime.now()
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except subprocess.CalledProcessError as e:
        print(f"\nCapture failed (exit {e.returncode}).")
    finally:
        elapsed = (dt.datetime.now() - start).total_seconds()
        print(f"\nDone. Elapsed: {elapsed:.1f}s")
        print(f"Files saved under: {outdir.resolve()}")


if __name__ == "__main__":
    main()
