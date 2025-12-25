import subprocess
from pathlib import Path

# -------- SETTINGS --------
IN_DIR = Path(r"C:\clipper_mvp\input")
OUT_DIR = Path(r"C:\clipper_mvp\output")

CLIP_LENGTH_SEC = 30
CLIPS_TO_EXPORT = 5
START_OFFSET_SEC = 5

# -------------------------

def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed:\n{' '.join(cmd)}\n\n{p.stderr}")

def pick_first_video(input_dir: Path) -> Path:
    for ext in ("*.mp4", "*.mkv", "*.mov", "*.webm"):
        vids = sorted(input_dir.glob(ext))
        if vids:
            return vids[0]
    raise FileNotFoundError(f"No video found in: {input_dir}")

def get_duration_sec(video_path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return float(p.stdout.strip())

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    video = pick_first_video(IN_DIR)
    print("Input video:", video)

    # Quick ffmpeg check
    run(["ffmpeg", "-version"])
    run(["ffprobe", "-version"])

    duration = get_duration_sec(video)
    print(f"Duration: {duration:.2f}s")

    usable = max(0, duration - CLIP_LENGTH_SEC - START_OFFSET_SEC)
    step = usable / max(1, CLIPS_TO_EXPORT)

    for i in range(CLIPS_TO_EXPORT):
        start = START_OFFSET_SEC + i * step
        if start + CLIP_LENGTH_SEC > duration - 0.5:
            break

        out = OUT_DIR / f"clip_{i+1:02d}_9x16.mp4"

        # vertical (simple center crop)
        vf = "scale=-2:1920,crop=1080:1920"

        print(f"Exporting clip {i+1}: start={start:.2f}s -> {out.name}")

        run([
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}", "-t", str(CLIP_LENGTH_SEC),
            "-i", str(video),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            str(out)
        ])

    print("Done. Check:", OUT_DIR)

if __name__ == "__main__":
    main()
