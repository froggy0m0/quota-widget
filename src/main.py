from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import tempfile
import time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from PIL import Image, ImageFont, ImageOps

from quota import QuotaClient, find_codex
from layered_window import LayeredWindow
from rendering import render_frame
from claude_quota import ClaudeQuotaClient

PROVIDERS = {"codex": "Codex", "claude": "Claude"}
STYLES = {"round": "동글 사슴", "antlers": "작은 뿔 사슴"}
SIZES = (128, 160)
DEFAULT_SIZE = 128


class Tooltip:
    def __init__(self, widget: tk.Widget) -> None:
        self.widget = widget
        self.text = ""
        self.window: tk.Toplevel | None = None

    def show(self, text: str) -> None:
        self.hide()
        if not text:
            return
        self.text = text
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_attributes("-topmost", True)
        label = tk.Label(self.window, text=text, bg="#2b2016", fg="white", padx=6, pady=4)
        label.pack()
        x = self.widget.winfo_pointerx() + 12
        y = self.widget.winfo_pointery() + 16
        self.window.wm_geometry(f"+{x}+{y}")

    def hide(self) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None


class DeerWidget:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.root = tk.Tk(className="QuotaWidget")
        self.root.withdraw()
        self.root.title("Quota Widget")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.wm_attributes("-toolwindow", True)
        except tk.TclError:
            pass
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.client: QuotaClient | ClaudeQuotaClient | None = None
        self.usage: float | None = None
        self.error = ""
        self.healthy = False
        self.started = time.monotonic()
        self.size = DEFAULT_SIZE
        self.style = "round"
        self.provider = "codex"
        self.settings_path = Path(args.settings_path) if args.settings_path else self.default_settings_path()
        self._load_settings()
        if args.provider:
            self.provider = args.provider

        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.images: dict[str, tuple[Image.Image, Image.Image]] = {}
        self.value_font = ImageFont.truetype(str(Path(os.environ["WINDIR"]) / "Fonts" / "consolab.ttf"), 16)
        for style in STYLES:
            with Image.open((Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "src" else Path(__file__).parent) / "assets" / f"deer-{style}.png") as image:
                color = image.convert("RGBA")
                gray = ImageOps.grayscale(color).convert("RGBA")
                gray.putalpha(color.getchannel("A"))
                self.images[style] = (color, gray)
        self.surface = LayeredWindow(self.root)
        self.tooltip = Tooltip(self.root)
        self.menu = self._make_menu()
        for widget in (self.root, self.canvas):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<Button-3>", self._popup)
            widget.bind("<Enter>", self._show_tooltip)
            widget.bind("<Leave>", lambda _event: self.tooltip.hide())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._set_appearance(self.style, self.size, save=False)
        self.root.deiconify()
        self.root.after(100, self._tick)
        self._start_client()

    def _start_client(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
        # A detached queue prevents late replies from the old service changing this service's number.
        self.events = queue.Queue()
        self.usage = None
        self.healthy = False
        self.error = ""
        self.root.title(f"{PROVIDERS[self.provider]} Quota")
        self._render()
        if self.args.demo:
            self.usage = 42.0
            self.healthy = True
            self._render()
        else:
            try:
                if self.provider == "claude":
                    self.client = ClaudeQuotaClient(self.events)
                else:
                    self.client = QuotaClient(find_codex(self.args.codex_path), self.events)
                self.client.start()
            except Exception as exc:
                self.error = str(exc)
                self._render()

    def _select_provider(self, provider: str) -> None:
        if provider not in PROVIDERS or provider == self.provider:
            return
        self.provider = provider
        self.provider_var.set(provider)
        self._save_settings()
        self._start_client()

    @staticmethod
    def default_settings_path() -> Path:
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "QuotaWidget" / "settings.json"
        return Path.home() / ".quota-widget" / "settings.json"

    def _load_settings(self) -> None:
        try:
            saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if saved.get("style") in STYLES:
                self.style = saved["style"]
            if saved.get("size") in SIZES:
                self.size = saved["size"]
            if saved.get("provider") in PROVIDERS:
                self.provider = saved["provider"]
        except (OSError, ValueError, AttributeError):
            pass

    def _save_settings(self) -> None:
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.settings_path.parent,
                delete=False, suffix=".tmp",
            ) as stream:
                json.dump({"style": self.style, "size": self.size, "provider": self.provider}, stream)
                temporary = Path(stream.name)
            temporary.replace(self.settings_path)
        except OSError:
            self.error = "모양은 바뀌었지만 설정을 저장하지 못했습니다."
            self._show_tooltip(None)

    def _make_menu(self) -> tk.Menu:
        menu = tk.Menu(self.root, tearoff=False)
        self.provider_var = tk.StringVar(value=self.provider)
        for key, title in PROVIDERS.items():
            menu.add_radiobutton(
                label=title, value=key, variable=self.provider_var,
                command=lambda provider=key: self._select_provider(provider),
            )
        menu.add_separator()
        style_menu = tk.Menu(menu, tearoff=False)
        self.style_var = tk.StringVar(value=self.style)
        for key, title in STYLES.items():
            style_menu.add_radiobutton(
                label=title, value=key, variable=self.style_var,
                command=lambda style=key: self._set_appearance(style, self.size),
            )
        size_menu = tk.Menu(menu, tearoff=False)
        self.size_var = tk.IntVar(value=self.size)
        for size in SIZES:
            size_menu.add_radiobutton(
                label=f"{size} px", value=size, variable=self.size_var,
                command=lambda value=size: self._set_appearance(self.style, value),
            )
        menu.add_cascade(label="사슴 모양", menu=style_menu)
        menu.add_cascade(label="크기", menu=size_menu)
        menu.add_separator()
        menu.add_command(label="종료", command=self.close)
        return menu

    def _set_appearance(self, style: str, size: int, *, save: bool = True) -> None:
        if style not in STYLES or size not in SIZES:
            return
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.style, self.size = style, size
        self.style_var.set(style) if hasattr(self, "style_var") else None
        self.size_var.set(size) if hasattr(self, "size_var") else None
        width = height = size
        if not self.root.winfo_viewable() and x == 0 and y == 0:
            x = max(0, self.root.winfo_screenwidth() - width - 24)
            y = 24
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.canvas.configure(width=width, height=height)
        if x < 0 or y < 0:
            self.root.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self._render()
        if save:
            self._save_settings()

    def _render(self) -> None:
        self.root.update_idletasks()
        color, gray = self.images[self.style]
        frame = render_frame(
            color, gray, self.size, self.usage, self.healthy, self.value_font,
            missing_text="—" if self.provider == "claude" else "--",
        )
        self.surface.present(frame)

    def _drag_start(self, event: tk.Event) -> None:
        self.drag_x, self.drag_y = event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y()

    def _drag(self, event: tk.Event) -> None:
        self.root.geometry(f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}")

    def _popup(self, event: tk.Event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)

    def _show_tooltip(self, _event: tk.Event | None) -> None:
        text = self.error or f"{PROVIDERS[self.provider]} 5시간 사용률 · 1분 간격 조회"
        if self.args.demo:
            text = f"{PROVIDERS[self.provider]} 데모 화면 · 실제 사용량이 아닙니다."
        self.tooltip.show(text)

    def _tick(self) -> None:
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "usage":
                self.usage = float(value)
                self.healthy = True
                self.error = ""
            else:
                if self.provider == "claude":
                    self.usage = None
                self.healthy = False
                self.error = str(value)
            self._render()
        if self.args.close_after_seconds and time.monotonic() - self.started >= self.args.close_after_seconds:
            self.close()
            return
        self.root.after(100, self._tick)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
        self.tooltip.hide()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def probe(codex_path: str | None, provider: str = "codex") -> int:
    events: queue.Queue[tuple[str, object]] = queue.Queue()
    client: QuotaClient | ClaudeQuotaClient | None = None
    try:
        client = (ClaudeQuotaClient(events) if provider == "claude"
                  else QuotaClient(find_codex(codex_path), events))
        client.start()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                kind, _value = events.get(timeout=0.2)
            except queue.Empty:
                continue
            if kind == "usage":
                if provider == "claude":
                    print(f"PASS: local Claude usage cache, displayed usage {float(_value):.0f}%.")
                else:
                    print("PASS: read the 300-minute Codex quota without a model request.")
                return 0
            raise RuntimeError(str(_value))
        raise TimeoutError("Probe timed out.")
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Codex / Claude 5-hour quota deer widget")
    parser.add_argument("--codex-path")
    parser.add_argument("--provider", choices=tuple(PROVIDERS))
    parser.add_argument("--settings-path")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--close-after-seconds", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.probe:
        return probe(args.codex_path, args.provider or "codex")
    try:
        DeerWidget(args).run()
        return 0
    except Exception as exc:
        try:
            messagebox.showerror("Quota Widget", str(exc))
        except Exception:
            print(f"Quota Widget: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
