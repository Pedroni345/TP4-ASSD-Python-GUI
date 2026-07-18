# TP4-ASSD — STM32 Power Analyzer

Power analyzer built on an STM32H755 Nucleo-144 (**CM7 core only**). Line voltage
and current are sensed, amplified by PGA281 differential gain stages, digitized by
two MCP33131D 16-bit SPI ADCs (galvanically isolated via optocouplers), processed
on-chip (RMS, power, harmonics), and streamed over the ST-Link VCP UART to a
Python/PyQt5 visualizer on a PC (Windows). Signal-chain diagrams live in `PA.ipynb`.

## Signal chain → code map

| Phase | Where |
|---|---|
| PGA281 gain set (74HC595 shift reg via PD14/PD15/PG9) | `main.c`: `SetPGA_Gains`, `OPTO_ShiftOut`; V code = upper nibble, I code = lower nibble **bit-reversed** (wiring) |
| ADC acquisition: TIM8 CH1 = CNVST pulse; CH2/CH3 DMA-pace dummy TX on SPI1 (V) / SPI3 (I); circular RX DMA into 5120-sample buffers | `main.c` (init + `V/I_RxHalf/FullDone` callbacks) |
| ADC codes → volts (±vref, 16-bit) | `dsp_pipeline.c` (entry: `dsp_pipeline_process_frame`, runs per half-buffer, interrupt-driven) |
| DC removal: 1 Hz high-pass biquad | `filters.c` |
| Cycle segmentation: zero-crossing detection, 10-cycle blocks | `zero_crossing.c` |
| Harmonics 1–23: Goertzel + Hann window | `goertzel.c` |
| P/Q/S (total & fundamental), PF, DPF, THD, block averaging | `power_calc.c` → `MeasurementOutput_t` |
| Constants (fs, block sizes, MAX_HARMONIC=23) | `dsp_config.h`; startup self-tests in `dsp_tests.c` |

All firmware sources in `STM32/CM7/Core/{Src,Inc}`.

## UART protocol (115200, USART3/COM1 VCP)

- **TX (1 Hz)**: little-endian binary frame, 260 B: header `0xAA55AA55` +
  `MeasurementOutput_t` (252 B: 14 floats, 24+24 harmonic floats indexed by order,
  n_blocks u16, active v_gain/i_gain u8) + footer `0x55AA55AA`.
- **RX**: ASCII `GAIN,<v>,<i>\n` (gains 1..128, powers of 2) → updates PGA281 via
  shift register. Byte-wise interrupt RX (`HAL_UART_RxCpltCallback` in `main.c`,
  `USART3_IRQHandler` in `stm32h7xx_it.c`).

## Visualizer (`STM32/*.py`, runs on Windows)

- `stm32_measurement_reader.py` — frame sync/parse (`FRAME_FORMAT` must mirror the
  C struct) and **gain rescaling**: divides Vrms/Irms by the firmware-echoed PGA
  gains and powers by their product, so displayed values are sensor-referred.
- `visualizer_main.py` — PyQt5 GUI: live measurements, harmonics bars, PGA gain
  selectors (sends `GAIN` command; panel shows echoed active gains).
- `test_visualizer_mock.py` — synthetic frame generator (no hardware).
- `PA_Monitor_2ch.py` — older standalone 2-channel monitor, reference only.

Note: DSP output is ADC-referred; only the Python side compensates PGA gain.
Sensor scale factors (V/V, A/V) are not yet applied anywhere.

## Where to work (context rules)

- **Do NOT read or explore:** `power_analyzer/` (legacy Python simulator; DSP
  already ported to C), `STM32/CM4/` (unused core), `STM32/CM7/Debug/` (build
  artifacts). Blocked via deny rules in `.claude/settings.json`.
- `STM32/**/Drivers/` is ST HAL/CMSIS vendor code — read only for a specific
  signature; never review or refactor it.
- Old status/summary markdowns were intentionally deleted; don't recreate them.
- Known issue: `filters.h`/`goertzel.h` use `arm_biquad_cascade_df1_f32_t` /
  `arm_rfft_fast_f32_t`, defined nowhere in this repo (build relies on the
  CubeIDE setup on the hardware laptop).

## Conventions

- Branch: `hardware-implementation-STM32`; PRs target `main`.
- Prefer one short summary doc over multiple status markdown files.
