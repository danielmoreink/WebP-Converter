# WebP Animator

WebP Animator converts a folder of image frames into an animated WebP file using `ffmpeg`.

The project includes:

- `webp_animator.py` - the Python source for the desktop and command-line app.
- `WebP Animator Single EXE/WebP Animator.exe` - a standalone Windows build for people who just want to run it.

## Use The Standalone App

Download or clone the repository, then run:

```text
WebP Animator Single EXE\WebP Animator.exe
```

Choose a folder containing image frames, set the conversion options, and click **Convert**.

Supported input formats include PNG, JPG, JPEG, BMP, GIF, WebP, TIF, and TIFF. Frames are sorted naturally by file name, so names like `frame1.png`, `frame2.png`, and `frame10.png` are handled in the expected order.

The app requires `ffmpeg`. If it is missing on Windows, the GUI can install the `Gyan.FFmpeg` package through `winget`.

## Run From Source

Requirements:

- Python 3.10 or newer
- `ffmpeg` available on `PATH`

Start the GUI:

```powershell
python webp_animator.py
```

Convert from the command line:

```powershell
python webp_animator.py .\frames --fps 24 --quality 80 --overwrite
```

Write to a specific output file:

```powershell
python webp_animator.py .\frames -o .\animation.webp --fps 12 --loop 0 --overwrite
```

Useful options:

- `--fps` sets the frame rate.
- `--quality` sets WebP quality from `0` to `100`.
- `--lossless` enables lossless WebP output.
- `--width` and `--height` resize output.
- `--recursive` includes frames in subfolders.
- `--ffmpeg` points to a specific `ffmpeg.exe`.
- `--ffmpeg-args` appends advanced ffmpeg options before the output file.

## Repository Notes

The hidden `.runtime/` folder is a local packaging runtime and is not needed for GitHub. The standalone executable is kept separately in `WebP Animator Single EXE/`.
