"""CI local: lint, formato y pruebas, en ese orden.

Uso:
    python -m scripts.check          # solo comprueba (lo que correría un CI)
    python -m scripts.check --fix    # arregla lo automático y vuelve a comprobar
    python -m scripts.check --network   # incluye las pruebas que usan la red real

Sale con código distinto de 0 si algo falla, así que sirve igual como paso de
un CI remoto o de un hook de git (ver README, sección "Calidad").
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(label: str, *args: str) -> bool:
    print(f"\n==> {label}: {' '.join(args)}", flush=True)
    return subprocess.run([sys.executable, "-m", *args], cwd=ROOT).returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint, formato y pruebas de Lemario.")
    parser.add_argument("--fix", action="store_true", help="Aplica los arreglos de ruff.")
    parser.add_argument("--network", action="store_true", help="Incluye las pruebas de red.")
    args = parser.parse_args(argv)

    if args.fix:
        run("arreglar", "ruff", "check", "--fix", ".")
        run("formatear", "ruff", "format", ".")

    pytest_args = ["pytest", "-q"] + (["--run-network"] if args.network else [])
    steps = [
        ("lint", ["ruff", "check", "."]),
        ("formato", ["ruff", "format", "--check", "."]),
        ("pruebas", pytest_args),
    ]
    # Se ejecutan todos aunque uno falle: mejor ver todo lo roto de una vez.
    results = {label: run(label, *cmd) for label, cmd in steps}

    print("\n" + "-" * 40)
    for label, ok in results.items():
        print(f"{'OK  ' if ok else 'FALLA'} {label}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
