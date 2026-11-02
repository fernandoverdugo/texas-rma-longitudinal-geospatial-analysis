from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(script):
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], check=True)


def main():
    run("analyze.py")
    run("build_map.py")
    print("Pipeline complete.")


if __name__ == "__main__":
    main()