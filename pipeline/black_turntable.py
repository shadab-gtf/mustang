"""Render a camera orbit around the finished Mustang and encode it as H.264."""

from __future__ import annotations

import argparse
from math import cos, pi, radians, sin
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy

DIRECTORY = Path(__file__).resolve().parent
if str(DIRECTORY) not in sys.path:
    sys.path.insert(0, str(DIRECTORY))

from black_studio import VIEWS, configure_cycles_device
from studio import aim, camera


def orbit_frames(scene: bpy.types.Scene, frames: Path, count: int) -> None:
    scene.frame_set(1)
    scene.camera = camera("Jet black | orbit", (0, 0, 0), (0, 1, 0), 55)
    scene.render.use_persistent_data = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 12
    for index in range(count):
        progress = index / (count - 1)
        eased = progress - 0.38 * sin(2 * pi * progress) / (2 * pi)
        angle = radians(-36 - 119 * eased)
        distance = 7.36 + 1.06 * sin(angle) ** 2
        height = 2.27 + 0.26 * sin(pi * progress)
        scene.camera.location = (distance * sin(angle), distance * cos(angle), height)
        aim(scene.camera, (0, 0.10 * cos(angle), 0.56))
        scene.render.filepath = str(frames / f"frame-{index:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"Mustang orbit frame {index + 1}/{count}", flush=True)


def encode_video(ffmpeg: str, frames: Path, output: Path, fps: int, encoded_fps: int, count: int) -> None:
    partial = output.with_name(f".{output.stem}.partial.mp4")
    filters = ["scale=out_color_matrix=bt709", "median=radius=1:radiusV=1:planes=1", "hqdn3d=1.4:1.1:2:1.6"]
    if encoded_fps > fps:
        filters.extend((
            f"tpad=stop_mode=clone:stop_duration={3 / fps}",
            f"minterpolate=fps={encoded_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bilat:search_param=16",
        ))
    try:
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-xerror", "-y", "-framerate", str(fps),
                "-i", str(frames / "frame-%04d.png"), "-vf", ",".join(filters), "-t", str(count / fps),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-movflags", "+faststart", str(partial),
            ],
            check=True,
        )
        partial.replace(output)
    finally:
        partial.unlink(missing_ok=True)


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", type=Path, default=DIRECTORY.parent / "renders" / "mustang-jet-black-turntable.mp4")
    cli.add_argument("--device", choices=("cpu", "cuda", "optix"), default="cpu")
    cli.add_argument("--fps", type=int, default=18)
    cli.add_argument("--encoded-fps", type=int, help="Interpolate between rendered frames to this rate.")
    cli.add_argument("--seconds", type=float, default=6.6)
    cli.add_argument("--width", type=int, default=1280)
    cli.add_argument("--height", type=int, default=720)
    cli.add_argument("--samples", type=int, default=12)
    args = cli.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    frame_count = round(args.seconds * args.fps)
    encoded_fps = args.encoded_fps if args.encoded_fps is not None else args.fps
    if frame_count < 2 or args.fps < 1 or args.samples < 1:
        cli.error("Frame rate, duration, and samples must produce at least two rendered frames.")
    if min(args.width, args.height) < 2 or args.width % 2 or args.height % 2:
        cli.error("Use positive even pixel dimensions for H.264.")
    if encoded_fps < args.fps:
        cli.error("The encoded frame rate must be at least the render frame rate.")
    if VIEWS["front"] not in bpy.data.objects:
        cli.error("Open assets/mustang-jet-black.blend before rendering the orbit.")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        cli.error("FFmpeg must be available on PATH.")

    scene = bpy.context.scene
    configure_cycles_device(scene, args.device)
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    if args.device != "cpu":
        scene.cycles.denoising_use_gpu = True
    if args.device == "optix":
        scene.cycles.denoiser = "OPTIX"
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 3
    scene.cycles.transparent_max_bounces = 4
    scene.cycles.sample_clamp_indirect = 4.0
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="mustang-black-orbit-") as directory:
        frames = Path(directory)
        orbit_frames(scene, frames, frame_count)
        encode_video(ffmpeg, frames, output, args.fps, encoded_fps, frame_count)


if __name__ == "__main__":
    main()
