from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from types import SimpleNamespace
from typing import Callable


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
FFMPEG_WINGET_PACKAGE = "Gyan.FFmpeg"
APP_ICON_ICO = Path("assets") / "app-icon.ico"
APP_ICON_PNG = Path("assets") / "app-icon.png"


def resource_path(relative_path: Path) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def console_write(message: str, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    print(message, file=stream)


def natural_key(path: Path) -> list[object]:
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def quote_concat_path(path: Path) -> str:
    ffmpeg_path = path.resolve().as_posix()
    return ffmpeg_path.replace("'", "'\\''")


def find_ffmpeg(explicit_path: str | None = None) -> str:
    if explicit_path:
        path = Path(explicit_path)
        if path.is_file():
            return str(path)
        raise FileNotFoundError(f"ffmpeg was not found at: {explicit_path}")

    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    raise FileNotFoundError(
        "ffmpeg.exe was not found. Install ffmpeg and make sure it is available on PATH, then restart this app."
    )


def find_ffmpeg_or_none() -> str | None:
    try:
        return find_ffmpeg()
    except FileNotFoundError:
        return None


def collect_frames(input_dir: Path, recursive: bool) -> list[Path]:
    iterator = input_dir.rglob("*") if recursive else input_dir.iterdir()
    frames = [path for path in iterator if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(frames, key=natural_key)


def build_filter(args: SimpleNamespace) -> str:
    filters = [f"fps={args.fps}"]
    width = str(args.width) if args.width else "-1"
    height = str(args.height) if args.height else "-1"
    if args.width or args.height:
        filters.append(f"scale={width}:{height}:flags=lanczos")
    return ",".join(filters)


def write_concat_file(frames: list[Path], frame_duration: float, list_path: Path) -> None:
    with open(list_path, "w", encoding="utf-8") as file:
        for frame in frames:
            file.write(f"file '{quote_concat_path(frame)}'\n")
            file.write(f"duration {frame_duration:.10f}\n")
        file.write(f"file '{quote_concat_path(frames[-1])}'\n")


def parse_extra_ffmpeg_args(value: str) -> list[str]:
    try:
        return shlex.split(value)
    except ValueError as error:
        raise ValueError(f"Extra ffmpeg arguments are invalid: {error}") from error


def convert(args: SimpleNamespace, log: Callable[[str], None] = console_write) -> int:
    def write_log(message: str) -> None:
        log(message)

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input directory does not exist: {input_dir}")

    output = args.output or input_dir / f"{input_dir.name}.webp"
    if output.suffix.lower() != ".webp":
        output = output.with_suffix(".webp")

    frames = collect_frames(input_dir, args.recursive)
    if not frames:
        extensions = ", ".join(sorted(IMAGE_EXTENSIONS))
        raise RuntimeError(f"No image frames found in {input_dir}. Supported: {extensions}")

    ffmpeg = find_ffmpeg(args.ffmpeg)
    frame_duration = 1.0 / args.fps
    extra_args = parse_extra_ffmpeg_args(getattr(args, "ffmpeg_args", ""))

    with tempfile.TemporaryDirectory(prefix="webp_animator_") as temp_dir:
        concat_file = Path(temp_dir) / "frames.txt"
        write_concat_file(frames, frame_duration, concat_file)

        command = [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-y" if args.overwrite else "-n",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-vf",
            build_filter(args),
            "-loop",
            str(args.loop),
            "-c:v",
            "libwebp_anim",
            "-quality",
            str(args.quality),
            "-lossless",
            "1" if args.lossless else "0",
            "-compression_level",
            str(args.compression),
        ]
        command.extend(extra_args)
        command.append(str(output))

        write_log(f"Frames: {len(frames)}")
        write_log(f"FPS: {args.fps:g}")
        write_log(f"Output: {output}")
        write_log("Running ffmpeg...")

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            write_log(line.rstrip())

        return_code = process.wait()
        if return_code == 0:
            write_log("Done.")
        return return_code


class WebpAnimatorApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.app_icon_image = None
        self.set_app_icon()
        self.root.title("WebP Animator")
        self.root.geometry("820x650")
        self.root.minsize(760, 620)

        self.input_dir = tk.StringVar()
        self.output = tk.StringVar()
        self.fps = tk.StringVar(value="24")
        self.quality = tk.IntVar(value=80)
        self.compression = tk.IntVar(value=4)
        self.loop = tk.StringVar(value="0")
        self.width = tk.StringVar()
        self.height = tk.StringVar()
        self.recursive = tk.BooleanVar(value=False)
        self.overwrite = tk.BooleanVar(value=True)
        self.lossless = tk.BooleanVar(value=False)
        self.ffmpeg_args = tk.StringVar()
        self.convert_button = None
        self.install_ffmpeg_button = None
        self.log_text = None

        self.build()
        self.refresh_ffmpeg_controls(show_warning=True)

        self.root.after(100, self.show_window)

    def set_app_icon(self) -> None:
        ico_path = resource_path(APP_ICON_ICO)
        if ico_path.is_file():
            try:
                self.root.iconbitmap(default=str(ico_path))
            except tk.TclError:
                pass

        png_path = resource_path(APP_ICON_PNG)
        if png_path.is_file():
            try:
                self.app_icon_image = tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, self.app_icon_image)
            except tk.TclError:
                self.app_icon_image = None

    def build(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(7, weight=1)

        ttk.Label(main, text="Frames folder").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(main, textvariable=self.input_dir).grid(row=0, column=1, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(main, text="Browse...", command=self.choose_input).grid(row=0, column=2, sticky="ew", pady=(0, 8))

        ttk.Label(main, text="Output WebP").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(main, textvariable=self.output).grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(main, text="Save as...", command=self.choose_output).grid(row=1, column=2, sticky="ew", pady=(0, 8))

        options = ttk.LabelFrame(main, text="Conversion", padding=12)
        options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        for column in range(4):
            options.columnconfigure(column, weight=1)

        self._add_labeled_spinbox(
            options,
            0,
            0,
            "FPS",
            self.fps,
            "Frames per second. 12-15 choppy, 24 film-like, 30/60 smoother.",
        )
        self._add_labeled_spinbox(
            options,
            0,
            1,
            "Quality (0-100)",
            self.quality,
            "Higher keeps more detail but makes larger files. 75-85 is a good default.",
            from_=0,
            to=100,
        )
        self._add_labeled_spinbox(
            options,
            0,
            2,
            "Compression effort (0-6)",
            self.compression,
            "Higher is slower and may reduce file size. 4 is balanced; 6 is smallest/slowest.",
            from_=0,
            to=6,
        )
        self._add_labeled_entry(options, 1, 0, "Loop", self.loop, "0 loops forever. 1 plays once, 2 plays twice, etc.")
        self._add_labeled_entry(
            options,
            1,
            1,
            "Width",
            self.width,
            "Optional. Leave blank to keep original size or preserve aspect ratio.",
        )
        self._add_labeled_entry(
            options,
            1,
            2,
            "Height",
            self.height,
            "If only width or height is set, the other dimension is auto-calculated.",
        )

        checks = ttk.Frame(main)
        checks.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Checkbutton(checks, text="Include subdirectories", variable=self.recursive).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(checks, text="Overwrite output", variable=self.overwrite).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(checks, text="Lossless", variable=self.lossless).pack(side="left")

        ttk.Label(main, text="Extra ffmpeg arguments").grid(row=4, column=0, sticky="w", pady=(4, 4))
        ttk.Entry(main, textvariable=self.ffmpeg_args).grid(row=4, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(4, 4))
        ttk.Label(
            main,
            text='Advanced: appended before the output file, for example "-preset picture". Leave blank unless you know you need this.',
        ).grid(row=5, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(0, 12))

        actions = ttk.Frame(main)
        actions.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        actions.columnconfigure(0, weight=1)
        self.install_ffmpeg_button = ttk.Button(actions, text="Install ffmpeg", command=self.install_ffmpeg)
        self.install_ffmpeg_button.grid(row=0, column=0, sticky="w")
        self.convert_button = ttk.Button(actions, text="Convert", command=self.start_convert)
        self.convert_button.grid(row=0, column=1, sticky="e")

        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.grid(row=7, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _add_labeled_spinbox(self, parent, row, column, label, variable, help_text, from_=1, to=9999):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, sticky="nw", padx=(0, 16), pady=(0, 12))
        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Spinbox(frame, textvariable=variable, from_=from_, to=to, width=10).pack(anchor="w", pady=(2, 2))
        ttk.Label(frame, text=help_text, wraplength=220).pack(anchor="w")

    def _add_labeled_entry(self, parent, row, column, label, variable, help_text):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, sticky="nw", padx=(0, 16), pady=(0, 12))
        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Entry(frame, textvariable=variable, width=12).pack(anchor="w", pady=(2, 2))
        ttk.Label(frame, text=help_text, wraplength=220).pack(anchor="w")

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.attributes("-topmost", True)
        self.root.after(750, lambda: self.root.attributes("-topmost", False))

    def choose_input(self) -> None:
        path = filedialog.askdirectory(title="Select frames folder")
        if not path:
            return
        self.input_dir.set(path)
        if not self.output.get():
            input_path = Path(path)
            self.output.set(str(input_path / f"{input_path.name}.webp"))

    def choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save animated WebP",
            defaultextension=".webp",
            filetypes=[("WebP image", "*.webp")],
        )
        if path:
            self.output.set(path)

    def log(self, message: str) -> None:
        def append() -> None:
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")

        self.root.after(0, append)

    def set_busy(self, busy: bool) -> None:
        self.convert_button.configure(state="disabled" if busy else "normal")
        if self.install_ffmpeg_button is not None:
            self.install_ffmpeg_button.configure(state="disabled" if busy else "normal")

    def refresh_ffmpeg_controls(self, show_warning: bool = False) -> bool:
        try:
            find_ffmpeg()
        except FileNotFoundError as error:
            if self.install_ffmpeg_button is not None:
                self.install_ffmpeg_button.grid()
                if shutil.which("winget") is None:
                    self.install_ffmpeg_button.configure(state="disabled")
            if show_warning:
                self.root.after(250, lambda: messagebox.showwarning("ffmpeg not installed", str(error)))
            return False

        if self.install_ffmpeg_button is not None:
            self.install_ffmpeg_button.grid_remove()
        return True

    def install_ffmpeg(self) -> None:
        if find_ffmpeg_or_none():
            self.refresh_ffmpeg_controls()
            messagebox.showinfo("ffmpeg installed", "ffmpeg is already available on PATH.")
            return

        winget = shutil.which("winget")
        if winget is None:
            messagebox.showerror(
                "winget not found",
                "Windows Package Manager (winget) was not found. Install ffmpeg manually and restart this app.",
            )
            return

        self.log_text.delete("1.0", "end")
        self.set_busy(True)
        self.log(f"Installing ffmpeg with winget package {FFMPEG_WINGET_PACKAGE}...")

        def worker() -> None:
            command = [
                winget,
                "install",
                FFMPEG_WINGET_PACKAGE,
                "--exact",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ]
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                assert process.stdout is not None
                for line in process.stdout:
                    self.log(line.rstrip())
                return_code = process.wait()

                if return_code != 0:
                    self.root.after(
                        0,
                        lambda: messagebox.showerror(
                            "ffmpeg install failed", f"winget exited with code {return_code}."
                        ),
                    )
                    return

                if find_ffmpeg_or_none():
                    self.root.after(0, lambda: self.refresh_ffmpeg_controls())
                    self.root.after(0, lambda: messagebox.showinfo("ffmpeg installed", "ffmpeg is ready to use."))
                else:
                    self.root.after(0, lambda: self.refresh_ffmpeg_controls())
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "ffmpeg installed",
                            "winget finished installing ffmpeg. If the app still cannot find it, restart the app so PATH is refreshed.",
                        ),
                    )
            except Exception as error:
                message = str(error)
                self.log(f"Error: {message}")
                self.root.after(0, lambda: messagebox.showerror("ffmpeg install failed", message))
            finally:
                self.root.after(0, lambda: self.set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def build_args(self) -> SimpleNamespace:
        input_dir = self.input_dir.get().strip()
        if not input_dir:
            raise ValueError("Choose a frames folder.")

        output = self.output.get().strip()
        width = int(self.width.get()) if self.width.get().strip() else None
        height = int(self.height.get()) if self.height.get().strip() else None
        fps = float(self.fps.get())
        quality = int(self.quality.get())
        compression = int(self.compression.get())
        loop = int(self.loop.get())

        if fps <= 0:
            raise ValueError("FPS must be greater than 0.")
        if quality < 0 or quality > 100:
            raise ValueError("Quality must be between 0 and 100.")
        if compression < 0 or compression > 6:
            raise ValueError("Compression must be between 0 and 6.")
        if loop < 0:
            raise ValueError("Loop cannot be negative.")

        return SimpleNamespace(
            input_dir=Path(input_dir),
            output=Path(output) if output else None,
            fps=fps,
            quality=quality,
            compression=compression,
            loop=loop,
            width=width,
            height=height,
            recursive=self.recursive.get(),
            overwrite=self.overwrite.get(),
            lossless=self.lossless.get(),
            ffmpeg=None,
            ffmpeg_args=self.ffmpeg_args.get(),
        )

    def start_convert(self) -> None:
        try:
            args = self.build_args()
            find_ffmpeg()
        except Exception as error:
            messagebox.showerror("Invalid settings", str(error))
            return

        self.log_text.delete("1.0", "end")
        self.set_busy(True)

        def worker() -> None:
            try:
                return_code = convert(args, self.log)
                if return_code == 0:
                    self.root.after(0, lambda: messagebox.showinfo("WebP Animator", "Conversion finished."))
                else:
                    self.root.after(0, lambda: messagebox.showerror("ffmpeg failed", f"ffmpeg exited with code {return_code}."))
            except Exception as error:
                message = str(error)
                self.log(f"Error: {message}")
                self.root.after(0, lambda: messagebox.showerror("Conversion failed", message))
            finally:
                self.root.after(0, lambda: self.set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="webp-animator",
        description="Convert a directory of image frames into an animated WebP using ffmpeg.",
    )
    parser.add_argument("input_dir", nargs="?", type=Path, help="Directory containing animation frames.")
    parser.add_argument("-o", "--output", type=Path, help="Output .webp file. Defaults to <input-dir-name>.webp in the input directory.")
    parser.add_argument("--fps", type=float, default=24.0, help="Animation frame rate. Default: 24.")
    parser.add_argument("--quality", type=int, default=80, choices=range(0, 101), metavar="0-100", help="WebP quality. Default: 80.")
    parser.add_argument("--lossless", action="store_true", help="Use lossless WebP compression.")
    parser.add_argument("--compression", type=int, default=4, choices=range(0, 7), metavar="0-6", help="Lossy compression effort. Default: 4.")
    parser.add_argument("--loop", type=int, default=0, help="Loop count. 0 means loop forever. Default: 0.")
    parser.add_argument("--width", type=int, help="Resize output width while preserving aspect ratio if height is omitted.")
    parser.add_argument("--height", type=int, help="Resize output height while preserving aspect ratio if width is omitted.")
    parser.add_argument("--recursive", action="store_true", help="Include supported images in subdirectories.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the output file if it exists.")
    parser.add_argument("--ffmpeg", help="Path to ffmpeg.exe. By default, checks PATH.")
    parser.add_argument("--ffmpeg-args", default="", help="Extra ffmpeg arguments appended before the output file.")
    parser.add_argument("--gui", action="store_true", help="Open the desktop user interface.")

    args = parser.parse_args(argv)
    if args.gui:
        return args
    if args.input_dir is None:
        parser.error("input_dir is required unless --gui is used.")
    if args.fps <= 0:
        parser.error("--fps must be greater than 0.")
    if args.width is not None and args.width <= 0:
        parser.error("--width must be greater than 0.")
    if args.height is not None and args.height <= 0:
        parser.error("--height must be greater than 0.")
    if args.loop < 0:
        parser.error("--loop cannot be negative.")
    return args


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    if not raw_args:
        return WebpAnimatorApp().run()

    args = parse_args(raw_args)
    if args.gui:
        return WebpAnimatorApp().run()

    try:
        return convert(args)
    except KeyboardInterrupt:
        console_write("Cancelled.", True)
        return 130
    except Exception as error:
        console_write(f"Error: {error}", True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
