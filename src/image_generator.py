"""
Image generator for Discord-like liquid text effects.

This module consumes a configuration dictionary describing typography, color
palettes, glow, and drip effects and renders presets to PNG files.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


# ----------------------------- Data definitions -----------------------------

Color = Tuple[int, int, int, int]


def _hex_to_rgba(value: str, alpha_override: Optional[int] = None) -> Color:
    """Convert a hex string (#RGB, #RRGGBB, or #RRGGBBAA) into an RGBA tuple."""
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) == 6:
        value += "ff"
    if len(value) != 8:
        raise ValueError(f"Unsupported color {value!r}")
    components = tuple(int(value[i : i + 2], 16) for i in range(0, 8, 2))
    if alpha_override is not None:
        components = components[:3] + (alpha_override,)
    return components  # type: ignore[return-value]


@dataclass
class GlowConfig:
    enabled: bool = False
    mode: str = "outer"
    intensity: str = "medium"
    radius_px: int = 80
    spread_pct: int = 20
    per_word_color_glow: bool = False


@dataclass
class InnerShadowConfig:
    enabled: bool = False
    opacity: float = 0.25
    blur_px: int = 4
    offset_px: Tuple[int, int] = (0, 2)


@dataclass
class GlossConfig:
    enabled: bool = False
    specular_intensity: float = 0.4
    specular_size: float = 0.3
    highlight_direction_deg: float = 45.0


@dataclass
class LiquidEffectConfig:
    enabled: bool = False
    drip_density: str = "low"
    drip_length_px_range: Tuple[int, int] = (10, 60)
    drip_width_pct_of_stroke: Tuple[int, int] = (50, 90)
    gravity_direction_deg: float = 90.0
    gloss: GlossConfig = field(default_factory=GlossConfig)
    edge_softness: float = 0.1
    inner_shadow: InnerShadowConfig = field(default_factory=InnerShadowConfig)


@dataclass
class TypographyConfig:
    style: str = ""
    font_family_preferred: List[str] = field(default_factory=list)
    font_family_fallback: List[str] = field(default_factory=list)
    stroke_weight_pct: int = 100
    letter_spacing_pct: int = 0
    line_height_pct: int = 100
    cap_style: str = "round"
    join_style: str = "round"


@dataclass
class LayoutConfig:
    composition: str = "stacked"
    align: str = "center"
    max_width_pct: int = 90
    line_break_rules: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExportConfig:
    format: str = "png"
    transparent_background: bool = True
    optimize_for: List[str] = field(default_factory=list)
    color_profile: str = "sRGB"


@dataclass
class CanvasConfig:
    width_px: int = 1024
    height_px: int = 1024
    background_color: Color = (0, 0, 0, 0)
    dpi: int = 300


@dataclass
class PresetConfig:
    name: str
    text_lines: List[str]
    colors_per_word: Optional[List[str]] = None
    fill_pattern_per_word: Optional[List[str]] = None
    glow: Optional[Dict[str, object]] = None
    ampersand_override: Optional[Dict[str, str]] = None


@dataclass
class GeneratorConfig:
    version: str
    task: str
    canvas: CanvasConfig
    typography: TypographyConfig
    liquid_effect: LiquidEffectConfig
    glow: GlowConfig
    stroke_outline: Dict[str, object]
    palettes: Dict[str, Dict[str, str]]
    patterns: Dict[str, Dict[str, object]]
    layout: LayoutConfig
    export: ExportConfig
    presets: List[PresetConfig]

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "GeneratorConfig":
        canvas_dict = data["canvas"]
        background_dict = canvas_dict.get("background", {})
        canvas = CanvasConfig(
            width_px=canvas_dict["width_px"],
            height_px=canvas_dict["height_px"],
            background_color=_hex_to_rgba(background_dict.get("color", "#00000000")),
            dpi=canvas_dict.get("dpi", 300),
        )
        typography = TypographyConfig(**data["typography"])
        liquid_dict = data["liquid_effect"]
        gloss = GlossConfig(**liquid_dict["gloss"])
        inner_shadow = InnerShadowConfig(**liquid_dict["inner_shadow"])
        liquid_effect = LiquidEffectConfig(
            enabled=liquid_dict["enabled"],
            drip_density=liquid_dict.get("drip_density", "medium"),
            drip_length_px_range=tuple(liquid_dict.get("drip_length_px_range", [18, 120])),
            drip_width_pct_of_stroke=tuple(liquid_dict.get("drip_width_pct_of_stroke", [60, 110])),
            gravity_direction_deg=liquid_dict.get("gravity_direction_deg", 90),
            gloss=gloss,
            edge_softness=liquid_dict.get("edge_softness", 0.12),
            inner_shadow=inner_shadow,
        )
        glow = GlowConfig(**data["glow"])
        layout = LayoutConfig(**data["layout"])
        export = ExportConfig(**data["export"])
        presets = [PresetConfig(**preset) for preset in data.get("presets", [])]
        return GeneratorConfig(
            version=data["version"],
            task=data["task"],
            canvas=canvas,
            typography=typography,
            liquid_effect=liquid_effect,
            glow=glow,
            stroke_outline=data.get("stroke_outline", {}),
            palettes=data.get("palettes", {}),
            patterns=data.get("patterns", {}),
            layout=layout,
            export=export,
            presets=presets,
        )


# ----------------------------- Utility helpers -----------------------------


def _load_font(font_names: List[str], size: int) -> ImageFont.FreeTypeFont:
    """Return the first available font from the provided list."""
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    # Fallback to default DejaVu font shipped with Pillow
    return ImageFont.truetype("DejaVuSans.ttf", size)


# ----------------------------- Rendering engine ----------------------------


class LiquidTextRenderer:
    """Render text with liquid-style drips and glow effects."""

    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config

    # Public API -------------------------------------------------------------

    def render_preset(self, preset_name: str, output_dir: Path) -> Path:
        preset = self._find_preset(preset_name)
        image = self._render_preset_to_image(preset)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{preset.name}.{self.config.export.format}"
        image.save(output_path, self.config.export.format.upper())
        return output_path

    def _find_preset(self, preset_name: str) -> PresetConfig:
        for preset in self.config.presets:
            if preset.name == preset_name:
                return preset
        raise KeyError(f"Preset {preset_name!r} not found")

    # Core rendering ---------------------------------------------------------

    def _render_preset_to_image(self, preset: PresetConfig) -> Image.Image:
        canvas_cfg = self.config.canvas
        background = Image.new(
            "RGBA",
            (canvas_cfg.width_px, canvas_cfg.height_px),
            canvas_cfg.background_color,
        )
        draw = ImageDraw.Draw(background)

        font_size = min(canvas_cfg.width_px, canvas_cfg.height_px) // 6
        font = _load_font(
            self.config.typography.font_family_preferred
            + self.config.typography.font_family_fallback,
            font_size,
        )
        lines = preset.text_lines
        spacing = int(font_size * (self.config.typography.line_height_pct / 100))

        total_height = len(lines) * font_size + (len(lines) - 1) * (spacing - font_size)
        y = (canvas_cfg.height_px - total_height) // 2

        for idx, line in enumerate(lines):
            words = line.split(" ")
            rendered_line = self._render_line(words, preset, idx, font)
            line_width, line_height = rendered_line.size
            x = (canvas_cfg.width_px - line_width) // 2
            background.alpha_composite(rendered_line, dest=(x, y))
            y += spacing

        return background

    def _render_line(
        self,
        words: List[str],
        preset: PresetConfig,
        line_index: int,
        font: ImageFont.FreeTypeFont,
    ) -> Image.Image:
        line_text = " ".join(words)
        bbox = font.getbbox(line_text)
        width = max(1, bbox[2] - bbox[0] + 20)
        height = max(1, bbox[3] - bbox[1] + 20)
        text_mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(text_mask)
        mask_draw.text((-bbox[0] + 10, -bbox[1] + 10), line_text, font=font, fill=255)

        # Convert mask to image filled with the target color/pattern
        fill_image = self._create_fill_image(
            text_mask.size, preset, line_index, line_text=line_text
        )

        text_image = Image.new("RGBA", text_mask.size, (0, 0, 0, 0))
        text_image.putalpha(text_mask)
        text_image = Image.composite(fill_image, text_image, text_mask)

        if self.config.liquid_effect.enabled:
            text_image = self._apply_drips(text_image, preset)

        if self.config.liquid_effect.inner_shadow.enabled:
            text_image = self._apply_inner_shadow(text_image)

        if self.config.glow.enabled or (preset.glow and preset.glow.get("enabled")):
            text_image = self._apply_glow(text_image, preset, line_index)

        if self.config.liquid_effect.gloss.enabled:
            text_image = self._apply_gloss(text_image)

        return text_image

    # Individual effect helpers --------------------------------------------

    def _create_fill_image(
        self,
        size: Tuple[int, int],
        preset: PresetConfig,
        line_index: int,
        line_text: str,
    ) -> Image.Image:
        fill = Image.new("RGBA", size, (255, 255, 255, 0))
        palette_key = None
        if preset.colors_per_word:
            palette_key = preset.colors_per_word[min(line_index, len(preset.colors_per_word) - 1)]
        if preset.fill_pattern_per_word:
            pattern_key = preset.fill_pattern_per_word[
                min(line_index, len(preset.fill_pattern_per_word) - 1)
            ]
            pattern = self.config.patterns.get(pattern_key)
            if pattern:
                return self._generate_pattern(size, pattern)

        if palette_key is None:
            palette_key = "white"
        if line_text == "&" and preset.ampersand_override:
            palette = {"fill": preset.ampersand_override.get("fill", "#ffffff")}
        else:
            palette = self.config.palettes.get(palette_key, {"fill": "#ffffff"})
        color = _hex_to_rgba(palette.get("fill", "#ffffff"))
        fill.paste(color, [0, 0, *size])
        return fill

    def _generate_pattern(self, size: Tuple[int, int], pattern: Dict[str, object]) -> Image.Image:
        pattern_img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(pattern_img)
        colors = pattern.get("colors", ["#ffffff", "#cccccc"])
        scale = pattern.get("scale_pct", 80) / 100
        block = int(40 * scale)
        rng = random.Random(42)
        for y in range(0, size[1], block):
            for x in range(0, size[0], block):
                color = _hex_to_rgba(rng.choice(colors))
                draw.rectangle([x, y, x + block, y + block], fill=color)
        return pattern_img

    def _apply_drips(self, text_image: Image.Image, preset: PresetConfig) -> Image.Image:
        width, height = text_image.size
        draw = ImageDraw.Draw(text_image)
        density_map = {"low": 3, "medium": 6, "high": 12}
        drip_count = density_map.get(self.config.liquid_effect.drip_density, 5)
        rng = random.Random(hash(preset.name) & 0xFFFFFFFF)
        for _ in range(drip_count):
            base_x = rng.randint(0, width - 1)
            drip_len = rng.randint(*self.config.liquid_effect.drip_length_px_range)
            drip_width = int(
                (self.config.liquid_effect.drip_width_pct_of_stroke[0]
                 + rng.random()
                 * (
                     self.config.liquid_effect.drip_width_pct_of_stroke[1]
                     - self.config.liquid_effect.drip_width_pct_of_stroke[0]
                 ))
                / 100
                * (height / 8)
            )
            drip_color = text_image.getpixel((base_x, height - 1))
            draw.ellipse(
                [
                    base_x - drip_width // 2,
                    height - drip_len,
                    base_x + drip_width // 2,
                    height,
                ],
                fill=drip_color,
            )
        return text_image

    def _apply_inner_shadow(self, text_image: Image.Image) -> Image.Image:
        mask = text_image.split()[3]
        shadow = mask.filter(ImageFilter.GaussianBlur(self.config.liquid_effect.inner_shadow.blur_px))
        shadow = ImageChops.offset(shadow, *self.config.liquid_effect.inner_shadow.offset_px)
        shadow = shadow.point(lambda p: int(p * self.config.liquid_effect.inner_shadow.opacity))
        shadow_img = Image.new("RGBA", text_image.size, (0, 0, 0, 0))
        shadow_img.putalpha(shadow)
        text_image = Image.alpha_composite(shadow_img, text_image)
        return text_image

    def _apply_glow(self, text_image: Image.Image, preset: PresetConfig, line_index: int) -> Image.Image:
        glow_img = Image.new("RGBA", text_image.size, (0, 0, 0, 0))
        mask = text_image.split()[3]
        radius = self.config.glow.radius_px
        if preset.glow and "radius_px" in preset.glow:
            radius = preset.glow["radius_px"]
        blur = mask.filter(ImageFilter.GaussianBlur(radius))
        palette_key = "white"
        if preset.colors_per_word and self.config.glow.per_word_color_glow:
            palette_key = preset.colors_per_word[min(line_index, len(preset.colors_per_word) - 1)]
        palette = self.config.palettes.get(palette_key, {"glow": "#ffffff"})
        color = _hex_to_rgba(palette.get("glow", palette.get("fill", "#ffffff")), alpha_override=180)
        colored = Image.new("RGBA", text_image.size, color)
        glow_img.putalpha(blur)
        glow_img = Image.composite(colored, glow_img, blur)
        base = Image.new("RGBA", text_image.size, (0, 0, 0, 0))
        base.alpha_composite(glow_img)
        base.alpha_composite(text_image)
        return base

    def _apply_gloss(self, text_image: Image.Image) -> Image.Image:
        width, height = text_image.size
        gloss_layer = Image.new("RGBA", text_image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(gloss_layer)
        gradient_height = int(height * self.config.liquid_effect.gloss.specular_size)
        for y in range(gradient_height):
            alpha = int(150 * (1 - y / max(gradient_height, 1)))
            draw.line([(0, y), (width, y)], fill=(255, 255, 255, alpha))
        gloss_layer = gloss_layer.filter(ImageFilter.GaussianBlur(radius=8))
        text_image.alpha_composite(gloss_layer)
        return text_image


# --------------------------- Configuration helpers -------------------------


def load_config(config_path: Optional[Path] = None) -> GeneratorConfig:
    """Load a generator configuration from disk."""
    if config_path is None:
        config_path = Path(__file__).with_name("liquid_config.json")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return GeneratorConfig.from_dict(data)


def load_default_config() -> GeneratorConfig:
    """Backward compatible helper that loads the bundled configuration."""
    return load_config()


def render_all_presets(output_dir: Path, config: Optional[GeneratorConfig] = None) -> Dict[str, Path]:
    cfg = config or load_default_config()
    renderer = LiquidTextRenderer(cfg)
    outputs: Dict[str, Path] = {}
    for preset in cfg.presets:
        outputs[preset.name] = renderer.render_preset(preset.name, output_dir)
    return outputs


def load_env_file(path: Path, *, override: bool = False) -> Dict[str, str]:
    """Parse a simple KEY=VALUE .env file and inject it into os.environ."""
    if not path.exists():
        return {}

    loaded: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        loaded[key] = value
    return loaded


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render liquid text presets to images.")
    parser.add_argument(
        "preset",
        nargs="?",
        help="Name of the preset to render. If omitted, renders every preset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Directory where rendered images will be saved.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to a custom liquid configuration JSON file.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Path to a .env file to load before rendering (defaults to ./.env).",
    )
    args = parser.parse_args()

    env_path = args.env_file or Path(".env")
    loaded_env = load_env_file(env_path)
    if loaded_env:
        print(f"Loaded environment variables from {env_path}")

    if args.config is not None:
        config_path: Optional[Path] = args.config
    else:
        config_env = os.environ.get("LIQUID_CONFIG_PATH")
        config_path = Path(config_env) if config_env else None

    config = load_config(config_path)
    renderer = LiquidTextRenderer(config)

    if args.output is not None:
        output_dir = args.output
    else:
        output_env = os.environ.get("LIQUID_OUTPUT_DIR")
        output_dir = Path(output_env) if output_env else Path("output")

    preset_name = args.preset or os.environ.get("LIQUID_PRESET")

    if preset_name:
        path = renderer.render_preset(preset_name, output_dir)
        print(f"Rendered {preset_name} -> {path}")
    else:
        outputs = render_all_presets(output_dir, config)
        for name, path in outputs.items():
            print(f"Rendered {name} -> {path}")
