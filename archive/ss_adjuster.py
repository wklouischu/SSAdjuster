from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw


@dataclass(frozen=True)
class RGB:
    r: int
    g: int
    b: int


@dataclass(frozen=True)
class Component:
    count: int
    min_x: int
    min_y: int
    max_x: int
    max_y: int
    sum_x: int
    sum_y: int

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1

    @property
    def height(self) -> int:
        return self.max_y - self.min_y + 1

    @property
    def center(self) -> tuple[float, float]:
        return ((self.min_x + self.max_x + 1) / 2, (self.min_y + self.max_y + 1) / 2)

    @property
    def centroid(self) -> tuple[float, float]:
        return (self.sum_x / self.count, self.sum_y / self.count)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.min_x, self.min_y, self.max_x, self.max_y)


@dataclass
class FrameDetection:
    frame_index: int
    bottom: Component
    ruler: Component
    scale: float
    source_bbox: tuple[float, float, float, float] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Settings:
    frame_width: int
    frame_height: int
    target_character_height: int
    input_mode: str = "grid"
    bottom_padding: int = 0
    ruler_side: str = "none"
    bottom_marker_color: RGB = field(default_factory=lambda: RGB(255, 0, 255))
    ruler_marker_color: RGB = field(default_factory=lambda: RGB(0, 255, 0))
    marker_tolerance: int = 0
    min_marker_pixels: int = 4
    max_bottom_marker_size: int = 12
    clear_markers: bool = True
    output_background_color: RGB | None = None
    debug_output: Path | None = None


def parse_hex_color(value: str | None) -> RGB | None:
    if value is None:
        return None

    text = value.strip()
    if text.lower() in {"none", "transparent", "null"}:
        return None
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6:
        raise ValueError(f"color must be #RRGGBB: {value!r}")

    try:
        return RGB(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError as exc:
        raise ValueError(f"color must be #RRGGBB: {value!r}") from exc


def color_to_tuple(color: RGB | None) -> tuple[int, int, int, int]:
    if color is None:
        return (0, 0, 0, 0)
    return (color.r, color.g, color.b, 255)


def load_config(config_path: Path | None) -> dict[str, object]:
    config: dict[str, object] = {}
    if config_path is not None:
        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
        if not isinstance(config, dict):
            raise ValueError("config file must contain a JSON object")
    return config


def get_path_setting(config: dict[str, object], name: str) -> Path | None:
    value = config.get(name)
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None
    return Path(text)


def is_directory_path(path: Path) -> bool:
    return (path.exists() and path.is_dir()) or path.suffix == ""


def resolve_input_path(config: dict[str, object], args: argparse.Namespace) -> Path:
    config_input_path = get_path_setting(config, "input_path")
    if args.input is not None:
        if args.input.is_absolute() or config_input_path is None:
            return args.input
        if is_directory_path(config_input_path):
            return config_input_path / args.input
        return args.input

    if config_input_path is None:
        raise ValueError("missing input path: pass input or set input_path in config")
    if config_input_path.exists() and config_input_path.is_dir():
        raise ValueError("input_path is a directory; pass an input filename such as takeoff.png")
    return config_input_path


def resolve_output_directory(path: Path) -> Path:
    if is_directory_path(path):
        return path
    return path.parent


def resolve_io_paths(config: dict[str, object], args: argparse.Namespace) -> tuple[Path, Path]:
    input_path = resolve_input_path(config, args)

    config_output_path = get_path_setting(config, "output_path")
    if args.output is not None and config_output_path is not None:
        output_path = resolve_output_directory(config_output_path) / args.output.name
    else:
        output_path = args.output or config_output_path

    if output_path is None:
        suffix = input_path.suffix or ".png"
        output_path = input_path.with_name(f"{input_path.stem}.output{suffix}")
    elif is_directory_path(output_path):
        output_path = output_path / input_path.name

    return input_path, output_path


def load_settings(config: dict[str, object], args: argparse.Namespace) -> Settings:

    def get(name: str, default: object = None) -> object:
        override = getattr(args, name, None)
        if override is not None:
            return override
        return config.get(name, default)

    required = ["frame_width", "frame_height", "target_character_height"]
    missing = [name for name in required if get(name) is None]
    if missing:
        raise ValueError(f"missing required setting(s): {', '.join(missing)}")

    settings = Settings(
        input_mode=str(get("input_mode", "grid")).lower(),
        frame_width=int(get("frame_width")),
        frame_height=int(get("frame_height")),
        target_character_height=int(get("target_character_height")),
        bottom_padding=int(get("bottom_padding", 0)),
        ruler_side="none" if get("ruler_side", None) is None else str(get("ruler_side")).lower(),
        bottom_marker_color=parse_hex_color(str(get("bottom_marker_color", "#ff00ff"))),
        ruler_marker_color=parse_hex_color(str(get("ruler_marker_color", "#00ff00"))),
        marker_tolerance=int(get("marker_tolerance", 0)),
        min_marker_pixels=int(get("min_marker_pixels", 4)),
        max_bottom_marker_size=int(get("max_bottom_marker_size", 12)),
        clear_markers=bool(get("clear_markers", True)),
        output_background_color=parse_hex_color(
            None if get("output_background_color") is None else str(get("output_background_color"))
        ),
        debug_output=Path(str(get("debug_output"))) if get("debug_output") is not None else None,
    )

    validate_settings(settings)
    return settings


def validate_settings(settings: Settings) -> None:
    positive_fields = {
        "frame_width": settings.frame_width,
        "frame_height": settings.frame_height,
        "target_character_height": settings.target_character_height,
        "min_marker_pixels": settings.min_marker_pixels,
        "max_bottom_marker_size": settings.max_bottom_marker_size,
    }
    for name, value in positive_fields.items():
        if value <= 0:
            raise ValueError(f"{name} must be greater than 0")

    if settings.bottom_padding < 0:
        raise ValueError("bottom_padding must be 0 or greater")
    if settings.bottom_padding > settings.frame_height:
        raise ValueError("bottom_padding cannot be greater than frame_height")
    if settings.marker_tolerance < 0 or settings.marker_tolerance > 255:
        raise ValueError("marker_tolerance must be between 0 and 255")
    if settings.bottom_marker_color is None:
        raise ValueError("bottom_marker_color cannot be null")
    if settings.ruler_side != "none" and settings.ruler_marker_color is None:
        raise ValueError("ruler_marker_color cannot be null")
    if settings.input_mode not in {"grid", "auto"}:
        raise ValueError("input_mode must be either 'grid' or 'auto'")
    if settings.ruler_side not in {"right", "left", "nearest", "none"}:
        raise ValueError("ruler_side must be 'right', 'left', 'nearest', or 'none'")


def matches_color(pixel: tuple[int, int, int, int], color: RGB, tolerance: int) -> bool:
    if pixel[3] == 0:
        return False
    return (
        abs(pixel[0] - color.r) <= tolerance
        and abs(pixel[1] - color.g) <= tolerance
        and abs(pixel[2] - color.b) <= tolerance
    )


def find_components(image: Image.Image, color: RGB, tolerance: int) -> list[Component]:
    width, height = image.size
    pixels = image.load()
    visited = bytearray(width * height)
    components: list[Component] = []

    def index(x: int, y: int) -> int:
        return y * width + x

    for start_y in range(height):
        for start_x in range(width):
            start_index = index(start_x, start_y)
            if visited[start_index]:
                continue
            visited[start_index] = 1
            if not matches_color(pixels[start_x, start_y], color, tolerance):
                continue

            stack = [(start_x, start_y)]
            count = 0
            min_x = max_x = start_x
            min_y = max_y = start_y
            sum_x = 0
            sum_y = 0

            while stack:
                x, y = stack.pop()
                count += 1
                sum_x += x
                sum_y += y
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

                for next_x, next_y in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if next_x < 0 or next_y < 0 or next_x >= width or next_y >= height:
                        continue
                    next_index = index(next_x, next_y)
                    if visited[next_index]:
                        continue
                    visited[next_index] = 1
                    if matches_color(pixels[next_x, next_y], color, tolerance):
                        stack.append((next_x, next_y))

            components.append(
                Component(
                    count=count,
                    min_x=min_x,
                    min_y=min_y,
                    max_x=max_x,
                    max_y=max_y,
                    sum_x=sum_x,
                    sum_y=sum_y,
                )
            )

    return components


def bottom_marker_candidates(components: list[Component], settings: Settings) -> list[Component]:
    return [
        component
        for component in components
        if component.count >= settings.min_marker_pixels
        and component.width <= settings.max_bottom_marker_size
        and component.height <= settings.max_bottom_marker_size
    ]


def ruler_candidates(components: list[Component], settings: Settings) -> list[Component]:
    return [
        component
        for component in components
        if component.count >= settings.min_marker_pixels and component.height >= component.width
    ]


def select_bottom_marker(components: list[Component], settings: Settings) -> tuple[Component, list[str]]:
    warnings: list[str] = []
    candidates = bottom_marker_candidates(components, settings)

    if not candidates:
        if not components:
            raise ValueError("bottom marker not found")
        candidates = sorted(components, key=lambda component: component.count, reverse=True)[:1]
        warnings.append("no square-sized bottom marker found; using largest matching color component")

    if len(candidates) > 1:
        warnings.append(f"found {len(candidates)} bottom marker candidates; using lowest one")

    return max(candidates, key=lambda component: (component.center[1], component.count)), warnings


def select_ruler(components: list[Component], settings: Settings) -> tuple[Component, list[str]]:
    warnings: list[str] = []
    candidates = ruler_candidates(components, settings)

    if not candidates:
        if not components:
            raise ValueError("ruler marker not found")
        candidates = sorted(components, key=lambda component: component.height, reverse=True)[:1]
        warnings.append("no vertical ruler candidate found; using tallest matching color component")

    if len(candidates) > 1:
        warnings.append(f"found {len(candidates)} ruler candidates; using tallest one")

    return max(candidates, key=lambda component: (component.height, component.count)), warnings


def detect_frame(frame: Image.Image, frame_index: int, settings: Settings) -> FrameDetection:
    bottom_components = find_components(frame, settings.bottom_marker_color, settings.marker_tolerance)
    bottom, bottom_warnings = select_bottom_marker(bottom_components, settings)

    if settings.ruler_side == "none":
        ruler = make_synthetic_ruler(frame.height, round(bottom.center[0]))
        ruler_warnings: list[str] = []
    else:
        ruler_components = find_components(frame, settings.ruler_marker_color, settings.marker_tolerance)
        ruler, ruler_warnings = select_ruler(ruler_components, settings)

    if ruler.height <= 0:
        raise ValueError("ruler height must be greater than 0")

    scale = settings.target_character_height / ruler.height
    return FrameDetection(
        frame_index=frame_index,
        bottom=bottom,
        ruler=ruler,
        scale=scale,
        warnings=bottom_warnings + ruler_warnings,
    )


def make_synthetic_ruler(image_height: int, x: int) -> Component:
    h = image_height
    return Component(
        count=h,
        min_x=x,
        min_y=0,
        max_x=x,
        max_y=h - 1,
        sum_x=x * h,
        sum_y=h * (h - 1) // 2,
    )


def ruler_pair_score(bottom: Component, ruler: Component, settings: Settings) -> float | None:
    bottom_x, bottom_y = bottom.center
    ruler_x, _ = ruler.center
    ruler_bottom_y = ruler.max_y + 0.5
    dx = ruler_x - bottom_x

    if settings.ruler_side == "right" and dx < 0:
        return None
    if settings.ruler_side == "left" and dx > 0:
        return None

    return abs(dx) + abs(ruler_bottom_y - bottom_y) * 4


def source_bbox_for_detection(detection: FrameDetection, settings: Settings) -> tuple[float, float, float, float]:
    anchor_x, anchor_y = detection.bottom.center
    target_anchor_x = settings.frame_width / 2
    target_anchor_y = settings.frame_height - settings.bottom_padding
    source_width = settings.frame_width / detection.scale
    source_height = settings.frame_height / detection.scale
    source_left = anchor_x - target_anchor_x / detection.scale
    source_top = anchor_y - target_anchor_y / detection.scale
    return (source_left, source_top, source_left + source_width, source_top + source_height)


def detect_auto_frames(sheet: Image.Image, settings: Settings) -> list[FrameDetection]:
    bottom_components = find_components(sheet, settings.bottom_marker_color, settings.marker_tolerance)
    bottoms = bottom_marker_candidates(bottom_components, settings)

    if not bottoms:
        raise ValueError("auto mode found no bottom markers")

    if settings.ruler_side == "none":
        paired: list[tuple[Component, Component, list[str]]] = [
            (bottom, make_synthetic_ruler(sheet.height, round(bottom.center[0])), [])
            for bottom in sorted(bottoms, key=lambda c: c.center[0])
        ]
    else:
        ruler_components = find_components(sheet, settings.ruler_marker_color, settings.marker_tolerance)
        rulers = ruler_candidates(ruler_components, settings)

        if not rulers:
            raise ValueError("auto mode found no ruler markers")
        if len(bottoms) != len(rulers):
            raise ValueError(
                f"auto mode found {len(bottoms)} bottom markers and {len(rulers)} ruler markers; counts must match"
            )

        remaining_rulers = list(rulers)
        paired = []
        for bottom in sorted(bottoms, key=lambda component: component.center[0]):
            scored = [
                (score, ruler)
                for ruler in remaining_rulers
                if (score := ruler_pair_score(bottom, ruler, settings)) is not None
            ]
            warnings: list[str] = []
            if not scored:
                scored = [
                    (abs(ruler.center[0] - bottom.center[0]) + abs((ruler.max_y + 0.5) - bottom.center[1]) * 4, ruler)
                    for ruler in remaining_rulers
                ]
                warnings.append(f"no unused ruler found on the {settings.ruler_side}; using nearest ruler")

            _, ruler = min(scored, key=lambda item: item[0])
            remaining_rulers.remove(ruler)
            paired.append((bottom, ruler, warnings))

    detections: list[FrameDetection] = []
    for frame_index, (bottom, ruler, warnings) in enumerate(
        sorted(paired, key=lambda item: item[0].center[0])
    ):
        if ruler.height <= 0:
            raise ValueError(f"frame {frame_index}: ruler height must be greater than 0")

        scale = settings.target_character_height / ruler.height
        detection = FrameDetection(
            frame_index=frame_index,
            bottom=bottom,
            ruler=ruler,
            scale=scale,
            warnings=warnings,
        )
        detection.source_bbox = source_bbox_for_detection(detection, settings)
        left, top, right, bottom_edge = detection.source_bbox
        if left < 0 or top < 0 or right > sheet.width or bottom_edge > sheet.height:
            detection.warnings.append("source crop extends beyond input image; outside area will be transparent/background")
        detections.append(detection)

    return detections


def clear_marker_pixels(frame: Image.Image, settings: Settings) -> Image.Image:
    if not settings.clear_markers:
        return frame.copy()

    output = frame.copy()
    pixels = output.load()
    width, height = output.size
    marker_colors = [settings.bottom_marker_color]
    if settings.ruler_side != "none":
        marker_colors.append(settings.ruler_marker_color)
    for y in range(height):
        for x in range(width):
            pixel = pixels[x, y]
            if any(matches_color(pixel, color, settings.marker_tolerance) for color in marker_colors):
                pixels[x, y] = (pixel[0], pixel[1], pixel[2], 0)
    return output


def make_canvas(width: int, height: int, background: RGB | None) -> Image.Image:
    return Image.new("RGBA", (width, height), color_to_tuple(background))


def paste_clipped(canvas: Image.Image, overlay: Image.Image, left: int, top: int) -> None:
    right = left + overlay.width
    bottom = top + overlay.height
    canvas_left = max(0, left)
    canvas_top = max(0, top)
    canvas_right = min(canvas.width, right)
    canvas_bottom = min(canvas.height, bottom)

    if canvas_left >= canvas_right or canvas_top >= canvas_bottom:
        return

    crop_box = (
        canvas_left - left,
        canvas_top - top,
        canvas_right - left,
        canvas_bottom - top,
    )
    canvas.alpha_composite(overlay.crop(crop_box), (canvas_left, canvas_top))


def resampling_filter() -> int:
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def affine_transform_method() -> int:
    try:
        return Image.Transform.AFFINE
    except AttributeError:
        return Image.AFFINE


def transform_resampling_filter() -> int:
    try:
        return Image.Resampling.BICUBIC
    except AttributeError:
        return Image.BICUBIC


def adjust_frame(frame: Image.Image, detection: FrameDetection, settings: Settings) -> Image.Image:
    clean = clear_marker_pixels(frame, settings)
    new_width = max(1, math.ceil(settings.frame_width * detection.scale))
    new_height = max(1, math.ceil(settings.frame_height * detection.scale))
    scaled = clean.resize((new_width, new_height), resample=resampling_filter())

    anchor_x, anchor_y = detection.bottom.center
    target_anchor_x = settings.frame_width / 2
    target_anchor_y = settings.frame_height - settings.bottom_padding
    paste_left = round(target_anchor_x - anchor_x * detection.scale)
    paste_top = round(target_anchor_y - anchor_y * detection.scale)

    output = make_canvas(settings.frame_width, settings.frame_height, settings.output_background_color)
    paste_clipped(output, scaled, paste_left, paste_top)
    return output


def adjust_auto_frame(clean_sheet: Image.Image, detection: FrameDetection, settings: Settings) -> Image.Image:
    source_left, source_top, _, _ = source_bbox_for_detection(detection, settings)
    inverse_scale = 1 / detection.scale
    transformed = clean_sheet.transform(
        (settings.frame_width, settings.frame_height),
        affine_transform_method(),
        (inverse_scale, 0, source_left, 0, inverse_scale, source_top),
        resample=transform_resampling_filter(),
        fillcolor=color_to_tuple(settings.output_background_color),
    )

    output = make_canvas(settings.frame_width, settings.frame_height, settings.output_background_color)
    output.alpha_composite(transformed, (0, 0))
    return output


def annotate_debug_frame(frame: Image.Image, detection: FrameDetection, settings: Settings) -> Image.Image:
    debug = frame.copy()
    draw = ImageDraw.Draw(debug)
    target_x = settings.frame_width / 2
    target_y = settings.frame_height - settings.bottom_padding

    draw.rectangle(detection.bottom.bbox, outline=(255, 255, 255, 255), width=1)
    draw.rectangle(detection.ruler.bbox, outline=(255, 255, 255, 255), width=1)
    draw.line((target_x, 0, target_x, settings.frame_height), fill=(255, 255, 0, 180), width=1)
    draw.line((0, target_y, settings.frame_width, target_y), fill=(255, 255, 0, 180), width=1)
    draw.text((2, 2), f"{detection.frame_index}: x{detection.scale:.3f}", fill=(255, 255, 255, 255))
    return debug


def annotate_auto_debug_sheet(sheet: Image.Image, detections: list[FrameDetection], settings: Settings) -> Image.Image:
    debug = sheet.copy()
    draw = ImageDraw.Draw(debug, "RGBA")

    for detection in detections:
        bottom_x, bottom_y = detection.bottom.center
        ruler_x, _ = detection.ruler.center
        ruler_bottom_y = detection.ruler.max_y + 0.5
        label_x = max(0, int(bottom_x) + 4)
        label_y = max(0, int(detection.bottom.min_y) - 14)

        draw.rectangle(detection.bottom.bbox, outline=(255, 255, 255, 255), width=1)
        draw.rectangle(detection.ruler.bbox, outline=(255, 255, 255, 255), width=1)
        draw.line((bottom_x, bottom_y, ruler_x, ruler_bottom_y), fill=(255, 255, 0, 180), width=1)

        source_bbox = tuple(round(value) for value in (detection.source_bbox or source_bbox_for_detection(detection, settings)))
        draw.rectangle(source_bbox, outline=(255, 255, 0, 180), width=1)
        draw.text((label_x, label_y), f"{detection.frame_index}: x{detection.scale:.3f}", fill=(255, 255, 255, 255))

    return debug


def iter_frames(sheet: Image.Image, settings: Settings) -> Iterable[tuple[int, Image.Image]]:
    frame_count = sheet.width // settings.frame_width
    for frame_index in range(frame_count):
        left = frame_index * settings.frame_width
        box = (left, 0, left + settings.frame_width, settings.frame_height)
        yield frame_index, sheet.crop(box)


def adjust_sheet_grid(sheet: Image.Image, output_path: Path, settings: Settings) -> list[FrameDetection]:
    if sheet.height != settings.frame_height:
        raise ValueError(
            f"input height ({sheet.height}) must equal frame_height ({settings.frame_height}) for a one-row sheet"
        )
    if sheet.width % settings.frame_width != 0:
        raise ValueError(
            f"input width ({sheet.width}) must be divisible by frame_width ({settings.frame_width})"
        )

    frame_count = sheet.width // settings.frame_width
    output = make_canvas(sheet.width, settings.frame_height, settings.output_background_color)
    debug = make_canvas(sheet.width, settings.frame_height, settings.output_background_color)
    detections: list[FrameDetection] = []

    for frame_index, frame in iter_frames(sheet, settings):
        try:
            detection = detect_frame(frame, frame_index, settings)
        except ValueError as exc:
            raise ValueError(f"frame {frame_index}: {exc}") from exc

        adjusted = adjust_frame(frame, detection, settings)
        output.alpha_composite(adjusted, (frame_index * settings.frame_width, 0))

        if settings.debug_output is not None:
            debug_frame = annotate_debug_frame(frame, detection, settings)
            debug.alpha_composite(debug_frame, (frame_index * settings.frame_width, 0))

        detections.append(detection)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path)
    if settings.debug_output is not None:
        settings.debug_output.parent.mkdir(parents=True, exist_ok=True)
        debug.save(settings.debug_output)

    if frame_count == 0:
        raise ValueError("input sheet contains no frames")

    return detections


def adjust_sheet_auto(sheet: Image.Image, output_path: Path, settings: Settings) -> list[FrameDetection]:
    detections = detect_auto_frames(sheet, settings)
    output_width = len(detections) * settings.frame_width
    output = make_canvas(output_width, settings.frame_height, settings.output_background_color)
    clean_sheet = clear_marker_pixels(sheet, settings)

    for detection in detections:
        adjusted = adjust_auto_frame(clean_sheet, detection, settings)
        output.alpha_composite(adjusted, (detection.frame_index * settings.frame_width, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path)
    if settings.debug_output is not None:
        settings.debug_output.parent.mkdir(parents=True, exist_ok=True)
        annotate_auto_debug_sheet(sheet, detections, settings).save(settings.debug_output)

    return detections


def adjust_sheet(input_path: Path, output_path: Path, settings: Settings) -> list[FrameDetection]:
    sheet = Image.open(input_path).convert("RGBA")
    if settings.input_mode == "auto":
        return adjust_sheet_auto(sheet, output_path, settings)
    return adjust_sheet_grid(sheet, output_path, settings)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize a one-row sprite sheet using per-frame bottom markers and height rulers."
    )
    parser.add_argument("input", nargs="?", type=Path, help="input horizontal sprite sheet PNG")
    parser.add_argument("-o", "--output", type=Path, help="output sprite sheet PNG or output directory")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.json"),
        help="JSON config file (default: config.json)",
    )
    parser.add_argument("--input-mode", choices=["grid", "auto"])
    parser.add_argument("--frame-width", type=int)
    parser.add_argument("--frame-height", type=int)
    parser.add_argument("--target-character-height", type=int)
    parser.add_argument("--bottom-padding", type=int)
    parser.add_argument("--ruler-side", choices=["right", "left", "nearest", "none"])
    parser.add_argument("--bottom-marker-color")
    parser.add_argument("--ruler-marker-color")
    parser.add_argument("--marker-tolerance", type=int)
    parser.add_argument("--min-marker-pixels", type=int)
    parser.add_argument("--max-bottom-marker-size", type=int)
    parser.add_argument("--clear-markers", action=argparse.BooleanOptionalAction)
    parser.add_argument("--output-background-color")
    parser.add_argument("--debug-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        settings = load_settings(config, args)
        input_path, output_path = resolve_io_paths(config, args)
        detections = adjust_sheet(input_path, output_path, settings)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for detection in detections:
        print(
            "frame {index}: ruler={ruler}px scale={scale:.4f} bottom=({x:.1f},{y:.1f})".format(
                index=detection.frame_index,
                ruler=detection.ruler.height,
                scale=detection.scale,
                x=detection.bottom.center[0],
                y=detection.bottom.center[1],
            )
        )
        for warning in detection.warnings:
            print(f"warning: frame {detection.frame_index}: {warning}", file=sys.stderr)

    print(f"wrote {output_path}")
    if settings.debug_output is not None:
        print(f"wrote debug sheet {settings.debug_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
