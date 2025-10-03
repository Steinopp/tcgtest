#!/usr/bin/env python3
"""
Sony rapid capture via gphoto2 (full-resolution stills).

What this does
--------------
- Frees the camera from common macOS/Sony grabbers (Imaging Edge, PTPCamera)
- Finds the camera (auto or explicit usb:BUS,DEV)
- Shoots N photos at a fixed interval and downloads them to disk

Usage examples
--------------
  python src/capture_sony.py --frames 120 --interval 1.0 \
      --outdir datasets/cards/images/train --prefix table

  python src/capture_sony.py --frames 50 --interval 1.5 \
      --outdir datasets/cards/images/val --prefix val --keep-on-camera

Camera setup (Sony)
-------------------
- Menu > Setup > USB Connection: PC Remote (PTP)
- Disable Wi-Fi / Control w/ Smartphone
- Photo mode
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

def run(cmd, check=True, capture=False):
    return subprocess.run(
        cmd, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None
    )

def kill_grabbers():
    """
    Close processes that commonly claim the camera before gphoto2 can:
      - Sony Imaging Edge (Webcam/Desktop)
      - macOS PTPCamera
      - Canon EOS utilities (harmless if not present)
    """
    for name in [
        "Imaging Edge Webcam",
        "Imaging Edge Desktop",
        "PTPCamera",
        "EOS Webcam Utility",
        "EOS Utility Agent",
        "EOS Utility",
    ]:
        run(["pkill", "-f", name], check=False)

def check_gphoto2_or_install():
    if shutil.which("gphoto2") is None:
        os_name = platform.system().lower()
        print("gphoto2 not found.")
        if "darwin" in os_name:
            print("Install with Homebrew:\n  brew install gphoto2")
        elif "linux" in os_name:
            print("Install with apt:\n  sudo apt-get update && sudo apt-get install gphoto2")
        else:
            print("Install from: https://www.gphoto.org/")
        sys.exit(1)

def list_usb_ports():
    out = run(["gphoto2", "--list-ports"], capture=True).stdout or ""
    # look for usb:BUS,DEV patterns
    return sorted(set(re.findall(r"usb:\d+,\d+", out)))

def autodetect_output():
    return run(["gphoto2", "--auto-detect"], capture=True).stdout or ""

def try_summary(port=None):
    cmd = ["gphoto2"]
    if port:
        cmd += ["--port", port]
    cmd += ["--summary"]
    return run(cmd, check=False, capture=True)

def ensure_camera():
    """
    Strategy:
      1) Try --auto-detect
      2) If not found, enumerate usb:BUS,DEV and probe each with --summary
      3) Return None for auto, or the explicit port string
    """
    ad = autodetect_output()
    if "usb:" in ad.lower():
        print(ad.strip())
        return None  # auto mode is fine

    ports = list_usb_ports()
    if not ports:
        print("No camera detected.")
        print("- Check USB cable/port (use a data-capable cable)")
        print("- Set Sony USB Connection = PC Remote")
        print("- Disable Wi-Fi / Control w/ Smartphone")
        print("- Close Imaging Edge / OBS / Zoom, etc.")
        print(ad.strip())
        sys.exit(1)

    for p in ports:
        print(f"Trying port {p} …")
        res = try_summary(p)
        if res.returncode == 0 and ("Device capabilities" in (res.stdout or "") or "Camera summary" in (res.stdout or "")):
            print(f"Using port: {p}")
            return p

    print("Found USB ports but none responded to gphoto2 --summary.")
    print("Another process may still be holding the device (Imaging Edge / PTPCamera).")
    sys.exit(1)

def maybe_set_capture_target(keep_on_camera: bool, port: str | None):
    """
    On some Sony bodies, capturetarget may be supported:
      0 = RAM/internal, 1 = memory card
    It's okay if this no-ops on your model.
    """
    if not keep_on_camera:
        return
    cmd = ["gphoto2"]
    if port:
        cmd += ["--port", port]
    cmd += ["--set-config", "capturetarget=1"]
    run(cmd, check=False)

def main():
    ap = argparse.ArgumentParser(description="Sony rapid capture via gphoto2")
    ap.add_argument("--frames", type=int, default=100, help="Number of photos to take")
    ap.add_argument("--interval", type=float, default=1.5, help="Seconds between photos")
    ap.add_argument("--outdir", type=str, default="datasets/cards/images/train", help="Output directory")
    ap.add_argument("--prefix", type=str, default="shot", help="Filename prefix")
    ap.add_argument("--keep-on-camera", action="store_true", help="Also save to camera's card (if supported)")
    ap.add_argument("--dry-run", action="store_true", help="Print command and exit")
    args = ap.parse_args()

    check_gphoto2_or_install()
    kill_grabbers()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    port = ensure_camera()  # None ⇒ use auto; otherwise explicit usb:BUS,DEV

    maybe_set_capture_target(args.keep_on_camera, port)

    template = f"{args.prefix}_%Y%m%d-%H%M%S_%03n.jpg"
    filename = str((outdir / template).as_posix())

    cmd = ["gphoto2"]
    if port:
        cmd += ["--port", port]
    cmd += [
        "--capture-image-and-download",
        f"--frames={args.frames}",
        f"--interval={args.interval}",
        f"--filename={filename}",
        "--force-overwrite",
    ]

    print("\n=== Sony Rapid Capture (gphoto2) ===")
    print("Start           :", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("Frames          :", args.frames)
    print("Interval (sec)  :", args.interval)
    print("Output directory:", outdir.resolve())
    print("Filename prefix :", args.prefix)
    print("Using port      :", port or "auto")
    print("Command         :", " ".join(cmd))
    print("Tip: if this fails, unplug/replug, ensure USB Connection=PC Remote, Wi-Fi off, and re-run.")

    if args.dry_run:
        print("Dry-run; exiting.")
        return

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except subprocess.CalledProcessError as e:
        print(f"\nCapture failed (exit {e.returncode}).")
        print("If Imaging Edge / OBS is running, quit them and retry.")
        print("Also try a direct USB connection (avoid hubs) and a known good data cable.")

if __name__ == "__main__":
    main()
