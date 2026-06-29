# TP4-ASSD — Power Analyzer Simulator

An oscilloscope-styled desktop simulator that gives the "first glance" of the
TP4-ASSD power-analysis instrument. You craft an analog voltage/current input,
push it through the real hardware signal chain (programmable-gain amplifier →
anti-alias filter → ADC → galvanic isolation → DSP), probe the signal at every
stage, and compare the DSP results against the analytic ideal.

The hardware counterpart and the validated DSP algorithm live in the repo root
(`TP4_ASSD (1).pdf`, `PA.ipynb`).

## Features

- **Full per-harmonic signal generator** — set the fundamental, DC offset,
  phase, noise and the amplitude of every harmonic for both V and I.
- **Programmable gain (PGA281A)** — pick the gain/range per channel and watch a
  live ADC-fill bar + clip indicator. The same 16-bit ADC serves a ±735 V or a
  ±46 V input simply by changing the gain.
- **Multi-stage oscilloscope** — overlay any of: raw analog, anti-alias filtered,
  ADC-quantized, digital high-pass. Adjustable anti-alias and high-pass cut-offs.
- **DSP vs Ideal** — RMS, P/Q/S (total & fundamental), TPF, DPF, φ, frequency and
  THD, each shown against the analytic reference with a colour-coded % error,
  plus a normalized harmonic spectrum.
- **Live animated display** at ~40 FPS.

## Run

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

(From this `power_analyzer/` directory. A shared `../.venv` created during
development also works.)

## Test

```bash
.venv/bin/python -m pytest -q
```

The suite validates the Goertzel phasor, zero-crossing detection, ADC
quantization/clipping, the power formulas against analytic values, and the
full pipeline against the ideal reference (all within ~1% on a clean signal).

## Architecture

```
core/    config (constants, PGA gain tables, ADC) + immutable data models
dsp/     signal_gen, analog_frontend, filters, goertzel, zero_crossing,
         power_calc, ideal, pipeline   (the DSP chain, ported from PA.ipynb)
ui/      theme, scope_widget, harmonic_editor, frontend_panel,
         results_panel, main_window    (PyQt6 + pyqtgraph)
main.py  entry point
```

Data flows one way: the UI builds immutable `SignalSpec` / `FrontEndConfig`
objects, `dsp.pipeline` turns them into `StageTraces` (for the scope) and
`Measurements` (for the table). Two timers in `main_window` drive a fast scope
refresh and a slower DSP refresh (only recomputed when an input changes).

### Extending (PDF "Trabajo Futuro")

The modular DSP makes the documented next steps localized changes:

- **Energy (Wh)** — integrate `Measurements.p_total` over time in a new accumulator.
- **3-phase / sequence & imbalance** — run three `pipeline` instances and add a
  sequence-analysis module.
- **Phase-lag compensation** — adjust per-channel sample timing in
  `analog_frontend` / `signal_gen`.
- **Crest factor** — add `peak/rms` per channel in `power_calc`.
```
