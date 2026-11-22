# Contributing to Sideband

Sideband does not use GitHub pull requests. Contributions are submitted as **email patches** using `git send-email`.

## Table of Contents

1. [How to Submit Changes](#how-to-submit-changes)
2. [Building for Android — Quick Start](#building-for-android--quick-start)
3. [Building for x86_64 (Waydroid / Emulator)](#building-for-x86_64-waydroid--emulator)
4. [Building for arm64-v8a (Physical Devices)](#building-for-arm64-v8a-physical-devices)
5. [Testing with Waydroid](#testing-with-waydroid)
6. [Loading Files into Waydroid](#loading-files-into-waydroid)
7. [Desktop Development Run](#desktop-development-run)

---

## How to Submit Changes

Sideband accepts patches by email. The maintainer's address is `mark@unsigned.io`.

### 1. Set up `git send-email`

Install the package:

```bash
sudo apt install git-email
```

Configure SMTP (Gmail example — needs an [App Password](https://myaccount.google.com/apppasswords)):

```bash
git config --global sendemail.smtpserver smtp.gmail.com
git config --global sendemail.smtpencryption tls
git config --global sendemail.smtpserverport 587
git config --global sendemail.smtpuser YOUR_EMAIL@gmail.com
git config --global user.name "Your Name"
git config --global user.email YOUR_EMAIL@gmail.com
```

| Provider | `smtpserver` | `smtpencryption` | `smtpserverport` |
|---|---|---|---|
| Gmail | `smtp.gmail.com` | `tls` | `587` |
| ProtonMail | `127.0.0.1` (via Bridge) | `starttls` | `1025` |
| Outlook | `smtp-mail.outlook.com` | `tls` | `587` |

### 2. Make your changes

Create a feature branch:

```bash
git checkout -b feature/my-feature
# ... edit code ...
git add <files>
git commit -m "Short description of the change"
```

### 3. Generate and review the patch

```bash
git format-patch -1 HEAD -o /tmp/
```

### 4. Send the patch with a personal note

```bash
git send-email --to mark@unsigned.io --annotate /tmp/0001-*.patch
```

The `--annotate` flag opens your editor. Write your message **after the `---` line but before the diff**. Anything there becomes part of the email body and won't appear in the applied commit. Example:

```
From fc14e81... Mon Sep 17 00:00:00 2001
From: Your Name <you@gmail.com>
Date: ...
Subject: [PATCH] Add file manager sort menu and image attachment preview

---
Hi Mark,

This patch adds a sort menu to the file manager and an image
preview before attaching. Tested on Waydroid (x86_64) and desktop.

Thanks for building Sideband!

Best,
Your Name

 sbapp/main.py | 84 +++++...
```

### 5. Multi-patch series

If your feature spans multiple commits, generate all patches with `git format-patch origin/main` and send them as a series with `--cover-letter`:

```bash
git format-patch origin/main --cover-letter -o /tmp/
# Edit /tmp/0000-cover-letter.patch with an overview
git send-email --to mark@unsigned.io /tmp/0000-*.patch /tmp/0001-*.patch ...
```

---

## Building for Android — Quick Start

Full build documentation: **[BUILDING.md](BUILDING.md)** and **[BUILDING-DIFF.md](BUILDING-DIFF.md)**.

### Prerequisites (Debian/Ubuntu)

```bash
# Build tools
sudo apt install -y cmake autoconf default-jdk git gcc

# Waydroid (for testing)
sudo apt install -y waydroid
sudo waydroid init

# Buildozer (Android build orchestrator)
pipx install buildozer
```

### Clone repositories

```bash
git clone https://github.com/markqvist/Sideband.git
cd ..
git clone https://github.com/markqvist/Reticulum.git
git clone https://github.com/markqvist/LXMF.git
git clone https://github.com/markqvist/LXST.git
cd Sideband
```

Expected layout:

```
/home/asd/Projects/
├── Sideband/
├── Reticulum/RNS/
├── LXMF/LXMF/
└── LXST/LXST/
```

---

## Building for x86_64 (Waydroid / Emulator)

Target x86_64 when testing on Waydroid or the Android emulator.

### 1. Configure buildozer.spec

In `sbapp/buildozer.spec`, line 40:

```ini
android.archs = x86_64
```

### 2. Configure Makefile paths

In `sbapp/Makefile`, all build paths reference an architecture directory. Replace all `arm64-v8a` with `x86_64` (22 occurrences across lines 22–64). Example:

```makefile
# Line 22 (before):
cp patches/HIDDeviceUSB.java .buildozer/android/platform/build-arm64-v8a/build/...
# Line 22 (after):
cp patches/HIDDeviceUSB.java .buildozer/android/platform/build-x86_64/build/...
```

### 3. Apply recipe fixes

Six recipe bugs must be fixed before building. See **[BUILDING.md §3](BUILDING.md#3-recipe-fixes)** and **[BUILDING-DIFF.md](BUILDING-DIFF.md)** for exact diffs.

Quick summary of what's broken:

| Recipe | Issue |
|---|---|
| `lxst/` | Dir name mismatch + hardcoded absolute paths |
| `codec2/` | Missing native host tool `generate_codebook` |
| `python3/` | Missing `get_python_root()` + no `make install` |
| `hostpython3/` | Missing pip properties + wrong build flow |
| `opusfile/` | Debug `rich` import left in production code |
| `pycodec2/` | numpy not installed in host Python at build time |

### 4. Build

```bash
conda deactivate          # exit Conda — it breaks Android cross-compilation
cd sbapp
make -C . cleanlibs       # clean previous artifacts (only needed once)
make devapk               # build debug APK
```

Output: `sbapp/bin/sideband-1.9.2-x86_64-debug.apk`

---

## Building for arm64-v8a (Physical Devices)

Target `arm64-v8a` when building for a physical ARM Android phone/tablet.

### 1. Configure buildozer.spec

In `sbapp/buildozer.spec`, line 40:

```ini
android.archs = arm64-v8a
```

Keep x86_64 commented for reference:

```ini
#android.archs = x86_64
android.archs = arm64-v8a
```

### 2. Configure Makefile paths

In `sbapp/Makefile`, replace all `x86_64` with `arm64-v8a` (22 occurrences). This affects the targets:

| Target | Lines | What changes |
|---|---|---|
| `patchsdl` | 22–34 | `build-x86_64` → `build-arm64-v8a` |
| `patchpycodec2` | 37 | `_python_bundle__x86_64` → `_python_bundle__arm64-v8a` |
| `injectxml` | 42–47 | `build-x86_64` → `build-arm64-v8a` |
| `injectlibs` | 51 | `_python_bundle__x86_64` → `_python_bundle__arm64-v8a` |
| `prebake` | 58 | Marker file check path |
| `install` | 98 | APK filename suffix |

### 3. Build

```bash
conda deactivate
cd sbapp
make -C . cleanlibs       # recommended when switching architectures
make devapk
```

Output: `sbapp/bin/sideband-1.9.2-arm64-v8a-debug.apk`

### 4. Install on device

```bash
adb install sbapp/bin/sideband-1.9.2-arm64-v8a-debug.apk
adb logcat | grep "python\|sideband"
```

---

## Testing with Waydroid

Waydroid runs a full Android container natively on Linux, allowing you to test APK builds without a physical device.

### Installation

```bash
# Add Waydroid repository (Debian/Ubuntu)
curl -fsSL https://repo.waydro.id/waydroid.gpg | sudo gpg --dearmor -o /usr/share/keyrings/waydroid.gpg
echo "deb [signed-by=/usr/share/keyrings/waydroid.gpg] https://repo.waydro.id/ $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/waydroid.list
sudo apt update
sudo apt install -y waydroid

# Initialize (first time only)
sudo waydroid init
```

### Session management

```bash
waydroid session start         # start the Android container
waydroid status                # check status: Session: RUNNING
waydroid show-full-ui          # show the Android window

# Stop:
waydroid session stop

# Restart:
waydroid session restart
```

### Smartphone-sized window

```bash
# Persistent:
waydroid prop set persist.waydroid.width 412
waydroid prop set persist.waydroid.height 915
waydroid prop set persist.waydroid.density 420
waydroid session restart

# One-shot (launch-time only, not persistent):
waydroid show-full-ui -w 412 -h 915
```

### Install and launch APK

```bash
waydroid app install sbapp/bin/sideband-1.9.2-x86_64-debug.apk
waydroid app launch io.unsigned.sideband
```

### Reinstall after rebuild

```bash
waydroid app uninstall io.unsigned.sideband
waydroid app install sbapp/bin/sideband-1.9.2-x86_64-debug.apk
waydroid app launch io.unsigned.sideband
```

### Debugging with ADB

Waydroid exposes ADB over the container network bridge. The ADB daemon runs inside the container as root (no `adb root` needed).

```bash
# Find the container IP from the DHCP lease
cat /run/waydroid-lxc/dnsmasq.leases
# Shows: ... 192.168.240.112 WayDroid-x86-64-Device ...

# Connect
adb connect 192.168.240.112:5555

# Verify
adb devices

# View logs
adb logcat | grep "python\|sideband"

# Clear logs before a crash test
adb logcat -c
```

If ADB connection is refused:

1. Check the property: `waydroid prop get persist.waydroid.adb` → should be `true`
2. If not: `waydroid prop set persist.waydroid.adb true && waydroid session restart`
3. On the Waydroid window, tap **"Allow"** on the USB debugging authorization popup
4. Retry: `adb connect 192.168.240.112:5555`

### Find Waydroid filesystem on host

| Android path | Host path |
|---|---|
| `/storage/emulated/0/` | Not directly writable from host (tmpfs inside container) |
| Android `/data` partition | `/var/lib/waydroid/rootfs/data` (mount point) |
| Container images | `/var/lib/waydroid/images/system.img`, `vendor.img` |
| Config / props | `/var/lib/waydroid/waydroid.prop` |
| ADB keys | `/var/lib/waydroid/rootfs/data/misc/adb/adb_keys` |

---

## Loading Files into Waydroid

Since `/storage/emulated/0` is a tmpfs inside the container and not directly writable from the host, use ADB to push files.

### Push a single file

```bash
adb -s 192.168.240.112:5555 push myfile.apk /storage/emulated/0/Download/
```

### Push a directory of images (for testing attachments)

```bash
# Create a test folder
mkdir -p /tmp/test_images
cp /path/to/some/photos/*.jpg /tmp/test_images/

# Push to Android Pictures directory
adb push /tmp/test_images/ /storage/emulated/0/Pictures/test_images/

# Verify
adb shell ls /storage/emulated/0/Pictures/test_images/
```

Images pushed this way appear in the Android Gallery app and are selectable from the Sideband file picker.

### Pull files from Waydroid

```bash
adb pull /storage/emulated/0/Download/saved_attachment.jpg .
```

---

## Desktop Development Run

For quick feedback during development, run Sideband directly on desktop (no Android build needed):

```bash
cd /home/asd/Projects/Sideband
python main.py          # run the app
python main.py -v       # verbose logging
python main.py -d       # headless daemon mode
```

Or install via pip:

```bash
pip install -e .
sideband
```

A [Conda environment](BUILDING-DIFF.md#12-new-file-environmentyml-optional-conda) is available for desktop use only — never use Conda when building Android APKs.

---

## References

- **[BUILDING.md](BUILDING.md)** — Full Android build guide with narrative explanations
- **[BUILDING-DIFF.md](BUILDING-DIFF.md)** — Exact before/after diffs for every modified file
- **[README.md](README.md)** — Project overview and installation
- [Waydroid Documentation](https://docs.waydro.id/)
- [python-for-android Documentation](https://python-for-android.readthedocs.io/)
- [Buildozer Documentation](https://buildozer.readthedocs.io/)
