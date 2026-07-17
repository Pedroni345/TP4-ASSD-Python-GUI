# TP4-ASSD — STM32 Power Analyzer

STM32H755 (Nucleo) power analyzer: DSP firmware on the CM7 core + Python/PyQt5 USB-serial visualizer.

## Where to work (context rules)

- **Active code:** `STM32/CM7/Core/{Src,Inc}` (DSP pipeline, main.c) and the Python visualizer scripts in `STM32/`.
- **Do NOT read or explore:**
  - `power_analyzer/` — legacy Python simulator, kept only as reference. Its DSP logic was already ported to C in `STM32/CM7/Core`.
  - `STM32/CM4/` — the CM4 core is unused; only CM7 runs our code.
  - `STM32/CM7/Debug/` — build artifacts.
  - These are also blocked via deny rules in `.claude/settings.json`.
- `STM32/**/Drivers/` is ST HAL vendor code — read only when you need a specific HAL signature; never review or refactor it.
- Several status/summary markdown files from earlier sessions were intentionally deleted. Don't recreate them or treat them as missing.

## Conventions

- Branch: `hardware-implementation-STM32`; PRs target `main`.
- Prefer one short summary doc over multiple status markdown files when documenting work.
