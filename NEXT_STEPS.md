# TP4-ASSD: Integration & Testing Next Steps

**Date:** 2026-07-12  
**Status:** DSP modules complete; Main.c integration + Python GUI pending  
**Estimated Time:** 9–13 hours total (3–4 hours main.c + 2–3 hours Python + 4–6 hours testing)

---

## Part 1: Understanding the Current Architecture

### Where Are the DSP Files Right Now?

**Important Clarification:** I created the DSP files **directly in their final locations** in the STM32 project:

```
/home/pedro/Documents/TP4-ASSD/STM32/CM7/Core/
├── Inc/
│   ├── dsp_config.h         ← Already here
│   ├── filters.h            ← Already here
│   ├── zero_crossing.h      ← Already here
│   ├── goertzel.h           ← Already here
│   ├── power_calc.h         ← Already here
│   └── dsp_pipeline.h       ← Already here
│
└── Src/
    ├── filters.c            ← Already here
    ├── zero_crossing.c      ← Already here
    ├── goertzel.c           ← Already here
    ├── power_calc.c         ← Already here
    └── dsp_pipeline.c       ← Already here
```

**You do NOT need to copy them anywhere.** They are already in the correct directory structure expected by your STM32 project. You just need to:
1. Add them to your CubeMX IDE project (right-click "Core" → "Add Files")
2. Add the include path if not already added

### Current UART Data Flow

**Before Integration (Current State):**

```
ADC Hardware (5 kHz)
    ↓
DMA Circular Buffers (adc_V_buf[512], adc_I_buf[512])
    ↓ (every 102.4 ms)
DMA Callbacks (V_RxHalfDone, I_RxFullDone)
    ↓
Synchronization (wait for both V and I complete)
    ↓
Snapshot Buffers (snapshot_V_buf[512], snapshot_I_buf[512])
    ↓ (every 1000 ms)
Main Loop UART Transmission:
    • Header: 0xAA 0x55 0xAA 0x55 (4 bytes)
    • V raw samples: 512 × uint16 (1024 bytes)
    • I raw samples: 512 × uint16 (1024 bytes)
    ├─ Total: 2052 bytes
    └─ Transmission time @ 115200 baud: ~18 ms
    ↓
Python GUI (Receives raw samples → Performs DSP calculations)
```

**After Integration (New Architecture):**

```
ADC Hardware (5 kHz)
    ↓
DMA Circular Buffers (adc_V_buf[512], adc_I_buf[512])
    ↓ (every 102.4 ms)
DMA Callbacks (V_RxHalfDone, I_RxFullDone)
    ↓
Synchronization (wait for both V and I complete)
    ↓
Snapshot Buffers (snapshot_V_buf[512], snapshot_I_buf[512])
    ↓ (every 1000 ms - OR IMMEDIATELY if you want lower latency)
Main Loop Processing:
    • Call dsp_pipeline_process_frame()
    • Process: Filter → Zero-Crossing → FFT → Power Calc
    • Get: MeasurementOutput_t (struct with all results)
    ├─ Processing time: ~10 ms
    └─ Result size: ~200 bytes
    ↓
Main Loop UART Transmission:
    • Header: 0xAA 0x55 0xAA 0x55 (4 bytes)
    • Measurement results (196 bytes binary)
    • Transmission time @ 115200 baud: ~2 ms
    ↓
Python GUI (Receives processed results → Only visualizes, NO DSP)
```

---

## Part 2: Step-by-Step Main.c Integration

### Step 1: Add DSP Headers to Includes Section

**File:** `STM32/CM7/Core/Src/main.c`

**Find this section (around line 22-25):**
```c
/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "string.h"
/* USER CODE END Includes */
```

**Modify to:**
```c
/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "string.h"
#include "dsp_pipeline.h"    // ← ADD THIS LINE
/* USER CODE END Includes */
```

**Why?** This gives main.c access to all DSP pipeline functions and data structures.

---

### Step 2: Create Global DSP Pipeline Instance

**File:** `STM32/CM7/Core/Src/main.c`

**Find this section (around line 73-96 where other global buffers are defined):**
```c
/* USER CODE BEGIN PV */

const uint16_t sine_lut_48[48] = {
    2048, 2288, ...
};

#define N_SAMPLES 512
#define HALF_SAMPLES (N_SAMPLES / 2)
static uint16_t adc_V_buf[N_SAMPLES];
static uint16_t adc_I_buf[N_SAMPLES];
// ... other buffers ...
```

**Add after the buffer definitions (around line 96):**
```c
/* DSP Pipeline Instance */
static DSPPipeline_t dsp_pipeline;                    // ← ADD THIS
```

**Full example of what the section should look like:**
```c
/* USER CODE BEGIN PV */

const uint16_t sine_lut_48[48] = {
    // ... existing code ...
};

#define N_SAMPLES 512
#define HALF_SAMPLES (N_SAMPLES / 2)
static uint16_t adc_V_buf[N_SAMPLES];
static uint16_t adc_I_buf[N_SAMPLES];
static uint16_t spi_tx_V_dummy = 0x0000;
static uint16_t spi_tx_I_dummy = 0x0000;
static uint16_t snapshot_V_buf[N_SAMPLES];
static uint16_t snapshot_I_buf[N_SAMPLES];
static volatile uint8_t snapshot_ready = 0;
static volatile uint8_t v_half_flag = 0, i_half_flag = 0;
static volatile uint8_t v_full_flag = 0, i_full_flag = 0;
static const uint8_t frame_header[4] = {0xAA, 0x55, 0xAA, 0x55};

/* DSP Pipeline Instance */
static DSPPipeline_t dsp_pipeline;                    // ← NEW

extern UART_HandleTypeDef hcom_uart[];
```

**Why?** This creates a single persistent DSP pipeline object that maintains filter state, FFT tables, and measurement results across frames.

---

### Step 3: Initialize DSP Pipeline in main()

**File:** `STM32/CM7/Core/Src/main.c`

**Find the initialization section (around line 200-246) - after all MX_*_Init() calls:**
```c
  MX_TIM8_Init();
  MX_SPI3_Init();
  /* USER CODE BEGIN 2 */



  /* USER CODE END 2 */

  /* Initialize leds */
  BSP_LED_Init(LED_GREEN);
```

**Add inside "USER CODE BEGIN 2" section (lines 202-206):**
```c
  /* USER CODE BEGIN 2 */

  /* Initialize DSP Pipeline */
  if (dsp_pipeline_init(&dsp_pipeline) < 0) {
      Error_Handler();
  }

  /* USER CODE END 2 */
```

**Full context example:**
```c
  MX_TIM8_Init();
  MX_SPI3_Init();
  /* USER CODE BEGIN 2 */

  /* Initialize DSP Pipeline */
  if (dsp_pipeline_init(&dsp_pipeline) < 0) {
      Error_Handler();
  }

  /* USER CODE END 2 */

  /* Initialize leds */
  BSP_LED_Init(LED_GREEN);
```

**Why?** This sets up all filter states, FFT tables, and detector state once at startup, so they're ready to process frames.

---

### Step 4: Add Measurement Struct to UART Transmission

**File:** `STM32/CM7/Core/Src/main.c`

**Option A: Modify the existing transmission (Recommended for speed)**

**Find the main loop UART transmission (around line 292-305):**
```c
  while (1)
  {
    if ((snapshot_ready == 2) && (HAL_GetTick() - last_send_tick >= 1000)) {
        last_send_tick = HAL_GetTick();
        HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t*)frame_header,   sizeof(frame_header),   100);
        HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t*)snapshot_V_buf, sizeof(snapshot_V_buf), 200);
        HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t*)snapshot_I_buf, sizeof(snapshot_I_buf), 200);

        __disable_irq();
        snapshot_ready = 0;
        v_half_flag = 0;
        i_half_flag = 0;
        v_full_flag = 0;
        i_full_flag = 0;
        __enable_irq();
    }
```

**Replace with:**
```c
  while (1)
  {
    if ((snapshot_ready == 2) && (HAL_GetTick() - last_send_tick >= 1000)) {
        last_send_tick = HAL_GetTick();
        
        /* Process frame with DSP pipeline */
        MeasurementOutput_t measurement_result;
        int n_blocks = dsp_pipeline_process_frame(
            &dsp_pipeline,
            snapshot_V_buf,    // uint16_t[512] ADC codes
            snapshot_I_buf,    // uint16_t[512] ADC codes
            3.0f,              // ADC reference voltage (±3V differential)
            16,                // ADC resolution (16 bits)
            &measurement_result
        );
        
        /* Transmit measurement results (NEW BINARY FORMAT) */
        if (n_blocks > 0) {
            // Send measurement frame header
            uint32_t header = 0xAA55AA55;
            HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t*)&header, sizeof(header), 50);
            
            // Send measurement struct (200 bytes)
            HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t*)&measurement_result, sizeof(measurement_result), 100);
            
            // Optional: send footer/checksum
            uint32_t footer = 0x55AA55AA;
            HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t*)&footer, sizeof(footer), 50);
        }

        __disable_irq();
        snapshot_ready = 0;
        v_half_flag = 0;
        i_half_flag = 0;
        v_full_flag = 0;
        i_full_flag = 0;
        __enable_irq();
    }
  }
```

**Changes Summary:**
- **Removed:** Transmission of raw ADC snapshot buffers (2048 bytes)
- **Added:** Call to `dsp_pipeline_process_frame()` (processes filters, FFT, power calculations)
- **Added:** Transmission of `measurement_result` struct (200 bytes binary)
- **Result:** 10× data reduction, processing now on STM32, Python only visualizes

**Optional: Lower Latency Variant**

If you want results ASAP (not waiting for next 1000ms interval), change the if-condition:

```c
    if (snapshot_ready == 2) {  // Process immediately, not every 1000ms
        // ... rest of code ...
    }
```

---

### Step 5: Verify CubeMX Project Includes DSP Files

**In STM32CubeIDE:**

1. Right-click on **Core** folder → **Properties**
2. Go to **C/C++ Build** → **Settings** → **Tool Settings**
3. Verify **Include Paths** contains `Core/Inc`
4. Add files to project:
   - Right-click `Core/Src` → **Add Files**
   - Select: `filters.c`, `zero_crossing.c`, `goertzel.c`, `power_calc.c`, `dsp_pipeline.c`
   - Right-click `Core/Inc` → **Add Files**
   - Select: `dsp_config.h`, `filters.h`, `zero_crossing.h`, `goertzel.h`, `power_calc.h`, `dsp_pipeline.h`

5. **Rebuild** the project (Project → Clean → Build All)

---

## Part 3: Python GUI Refactoring

### Current Situation

**Existing Python GUI (power_analyzer/live_main.py):**
- Receives 512 raw ADC samples every ~1 second
- Performs all DSP calculations (filters, FFT, power)
- Displays results in real-time

**New Situation:**
- STM32 performs all DSP calculations
- Python receives processed `MeasurementOutput_t` struct (200 bytes)
- Python only visualizes results

### Step 1: Create New Binary Protocol Reader

**Create File:** `power_analyzer/acquisition/stm32_reader.py`

```python
"""
STM32 Measurement Frame Reader

Binary protocol for receiving processed power measurements from STM32.
New compact format (200 bytes) vs. old raw frames (2052 bytes).
"""

import struct
import serial
from typing import Optional, NamedTuple

class PowerMeasurement(NamedTuple):
    """Processed power measurement from STM32"""
    vrms: float                    # Voltage RMS (V)
    irms: float                    # Current RMS (A)
    frequency: float               # Fundamental frequency (Hz)
    p_total: float                 # Total active power (W)
    q_total: float                 # Total reactive power (VAR)
    s_total: float                 # Total apparent power (VA)
    tpf: float                     # Total power factor
    p_fund: float                  # Fundamental active power (W)
    q_fund: float                  # Fundamental reactive power (VAR)
    s_fund: float                  # Fundamental apparent power (VA)
    phi_deg: float                 # Fundamental phase angle (degrees)
    dpf: float                     # Displacement power factor
    thd_v: float                   # Voltage THD (%)
    thd_i: float                   # Current THD (%)
    v_harmonics: tuple             # V_k/V_1 normalized magnitudes
    i_harmonics: tuple             # I_k/I_1 normalized magnitudes
    n_blocks: int                  # Number of blocks averaged


class STM32MeasurementReader:
    """
    Reads processed measurement frames from STM32 over UART.
    
    Frame Format (Binary):
    ┌─────────────────────────────────────────────────┐
    │ Header:  0xAA55AA55                    (4 bytes) │
    │ Vrms, Irms, Frequency                  (12 bytes)│
    │ P_total, Q_total, S_total              (12 bytes)│
    │ TPF, P_fund, Q_fund, S_fund            (16 bytes)│
    │ Phi_deg, DPF, THD_V, THD_I             (16 bytes)│
    │ V_harmonics[24]                        (96 bytes)│
    │ I_harmonics[24]                        (96 bytes)│
    │ N_blocks, Reserved                     (4 bytes) │
    │ Footer:  0x55AA55AA                    (4 bytes) │
    ├─────────────────────────────────────────────────┤
    │ Total:                                 (200 bytes)│
    └─────────────────────────────────────────────────┘
    """
    
    # Struct format: 24 float32 + 24 float32 + scalar fields
    FRAME_FORMAT = '!I 24f 24f HHHH I'  # Adjust based on actual C struct layout
    FRAME_SIZE = 200  # bytes
    
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 115200):
        """
        Initialize STM32 measurement reader.
        
        Args:
            port: Serial port (e.g., '/dev/ttyUSB0' on Linux, 'COM3' on Windows)
            baudrate: UART baud rate (default 115200)
        """
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        
    def connect(self) -> bool:
        """Open serial connection to STM32"""
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=2)
            return True
        except serial.SerialException as e:
            print(f"Failed to open {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial:
            self.serial.close()
            self.serial = None
    
    def read_frame(self) -> Optional[PowerMeasurement]:
        """
        Read and parse one measurement frame from STM32.
        
        Returns:
            PowerMeasurement named tuple, or None if read failed
        """
        if not self.serial or not self.serial.is_open:
            return None
        
        try:
            # Read frame size
            frame_data = self.serial.read(self.FRAME_SIZE)
            
            if len(frame_data) < self.FRAME_SIZE:
                print(f"Incomplete frame: got {len(frame_data)}/{self.FRAME_SIZE} bytes")
                return None
            
            # Parse binary struct (adjust format based on exact C struct layout)
            # Header (skip), all floats, then shorts/ints
            (header,
             vrms, irms, frequency,
             p_total, q_total, s_total, tpf,
             p_fund, q_fund, s_fund,
             phi_deg, dpf, thd_v, thd_i,
             *v_harmonics,
             *i_harmonics,
             n_blocks, reserved,
             footer) = struct.unpack(self.FRAME_FORMAT, frame_data)
            
            # Verify frame boundaries
            if header != 0xAA55AA55 or footer != 0x55AA55AA:
                print(f"Frame sync error: header={hex(header)}, footer={hex(footer)}")
                return None
            
            # Create measurement object
            return PowerMeasurement(
                vrms=vrms,
                irms=irms,
                frequency=frequency,
                p_total=p_total,
                q_total=q_total,
                s_total=s_total,
                tpf=tpf,
                p_fund=p_fund,
                q_fund=q_fund,
                s_fund=s_fund,
                phi_deg=phi_deg,
                dpf=dpf,
                thd_v=thd_v,
                thd_i=thd_i,
                v_harmonics=tuple(v_harmonics),
                i_harmonics=tuple(i_harmonics),
                n_blocks=n_blocks
            )
        
        except struct.error as e:
            print(f"Struct unpack failed: {e}")
            return None
        except Exception as e:
            print(f"Frame read error: {e}")
            return None


def main():
    """Example usage"""
    reader = STM32MeasurementReader('/dev/ttyUSB0')
    
    if not reader.connect():
        return
    
    try:
        while True:
            measurement = reader.read_frame()
            if measurement:
                print(f"Vrms={measurement.vrms:.1f}V  "
                      f"Irms={measurement.irms:.2f}A  "
                      f"P={measurement.p_total:.1f}W  "
                      f"Q={measurement.q_total:.1f}VAR  "
                      f"S={measurement.s_total:.1f}VA  "
                      f"PF={measurement.tpf:.3f}  "
                      f"THD_V={measurement.thd_v:.1f}%")
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        reader.disconnect()


if __name__ == "__main__":
    main()
```

### Step 2: Create Visualization-Only Main Script

**Create File:** `power_analyzer/live_main_stm32.py`

```python
"""
TP4-ASSD GUI - Visualization Only (No DSP)

Receives processed power measurements from STM32 and displays them.
DSP processing happens on the embedded system, not on the PC.
"""

import sys
import struct
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtCore import QTimer, pyqtSignal, QThread

from acquisition.stm32_reader import STM32MeasurementReader, PowerMeasurement
from ui.live_results_panel import LiveResultsPanel
from ui.block_diagram import BlockDiagram


class ReaderThread(QThread):
    """Background thread that reads from STM32 and emits measurement signals"""
    
    measurement_received = pyqtSignal(PowerMeasurement)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.reader = STM32MeasurementReader(port, baudrate)
        self.running = True
    
    def run(self):
        """Thread main loop"""
        if not self.reader.connect():
            self.error_occurred.emit(f"Failed to connect to {self.reader.port}")
            return
        
        while self.running:
            measurement = self.reader.read_frame()
            if measurement:
                self.measurement_received.emit(measurement)
            else:
                # Optional: small delay to prevent CPU spinning
                self.msleep(10)
    
    def stop(self):
        """Stop the reader thread"""
        self.running = False
        self.reader.disconnect()


class LiveVisualizerWindow(QMainWindow):
    """Main window for power analyzer visualization"""
    
    def __init__(self, serial_port: str = '/dev/ttyUSB0'):
        super().__init__()
        self.setWindowTitle("TP4-ASSD Power Analyzer - Live Visualization")
        self.setGeometry(100, 100, 1400, 800)
        
        # Create UI components
        central_widget = QWidget()
        layout = QVBoxLayout()
        
        # Results panel (displays Vrms, Irms, P, Q, S, PF, THD, etc.)
        self.results_panel = LiveResultsPanel()
        layout.addWidget(self.results_panel)
        
        # Block diagram (static, shows processing stages)
        self.block_diagram = BlockDiagram()
        layout.addWidget(self.block_diagram)
        
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        # Start reader thread
        self.reader_thread = ReaderThread(serial_port)
        self.reader_thread.measurement_received.connect(self.on_measurement_received)
        self.reader_thread.error_occurred.connect(self.on_error)
        self.reader_thread.start()
    
    def on_measurement_received(self, measurement: PowerMeasurement):
        """Handle new measurement from STM32"""
        # Update results panel with received data
        self.results_panel.update_results(
            vrms=measurement.vrms,
            irms=measurement.irms,
            frequency=measurement.frequency,
            p_total=measurement.p_total,
            q_total=measurement.q_total,
            s_total=measurement.s_total,
            tpf=measurement.tpf,
            p_fund=measurement.p_fund,
            q_fund=measurement.q_fund,
            s_fund=measurement.s_fund,
            phi_deg=measurement.phi_deg,
            dpf=measurement.dpf,
            thd_v=measurement.thd_v,
            thd_i=measurement.thd_i,
            v_harmonics=measurement.v_harmonics,
            i_harmonics=measurement.i_harmonics
        )
    
    def on_error(self, error_msg: str):
        """Handle reader errors"""
        print(f"ERROR: {error_msg}")
        # Could show error dialog, try reconnect, etc.
    
    def closeEvent(self, event):
        """Clean up on window close"""
        self.reader_thread.stop()
        self.reader_thread.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Connect to STM32 on specified port
    window = LiveVisualizerWindow(serial_port='/dev/ttyUSB0')
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```

### Step 3: Update Live Results Panel (Minimal Changes)

**File:** `power_analyzer/ui/live_results_panel.py`

The existing `LiveResultsPanel` only needs one method added to accept measurement data:

```python
def update_results(self, vrms, irms, frequency, p_total, q_total, s_total, tpf,
                   p_fund, q_fund, s_fund, phi_deg, dpf, thd_v, thd_i,
                   v_harmonics, i_harmonics):
    """Update all display fields with new measurement data"""
    # These methods should already exist in the panel
    self.label_vrms.setText(f"{vrms:.2f} V")
    self.label_irms.setText(f"{irms:.3f} A")
    self.label_frequency.setText(f"{frequency:.2f} Hz")
    
    self.label_p_total.setText(f"{p_total:.1f} W")
    self.label_q_total.setText(f"{q_total:.1f} VAR")
    self.label_s_total.setText(f"{s_total:.1f} VA")
    self.label_tpf.setText(f"{tpf:.3f}")
    
    self.label_p_fund.setText(f"{p_fund:.1f} W")
    self.label_phi.setText(f"{phi_deg:.1f}°")
    self.label_dpf.setText(f"{dpf:.3f}")
    
    self.label_thd_v.setText(f"{thd_v:.2f}%")
    self.label_thd_i.setText(f"{thd_i:.2f}%")
    
    # Update harmonic displays if they exist
    if hasattr(self, 'harmonics_plot'):
        self.harmonics_plot.update_data(v_harmonics, i_harmonics)
```

---

## Part 4: Testing & Validation

### Checklist Before Testing

- [ ] DSP .h/.c files added to STM32 CubeIDE project
- [ ] main.c includes `#include "dsp_pipeline.h"`
- [ ] Global `dsp_pipeline` instance declared
- [ ] `dsp_pipeline_init()` called in main()
- [ ] UART transmission modified to call `dsp_pipeline_process_frame()`
- [ ] Project builds without errors
- [ ] Python reader script created (stm32_reader.py)
- [ ] Python GUI script created (live_main_stm32.py)

### Unit Tests (C Side)

**Test 1: Filter Impulse Response**
```c
// In main() or separate test file
{
    HighPassFilterState_t filter;
    filters_highpass_init(&filter);
    
    float32_t impulse[100] = {0};
    impulse[0] = 1.0f;
    float32_t output[100];
    
    filters_highpass_apply(&filter, impulse, output, 100);
    
    // Verify impulse response shape (should be high-pass: 0 at DC)
    printf("HP filter DC response: %f (should be ~0)\n", output[0]);
}
```

**Test 2: Zero-Crossing Detection**
```c
{
    // Create synthetic 50 Hz sine wave
    float32_t sine[500];
    for (int i = 0; i < 500; i++) {
        sine[i] = sinf(2.0f * 3.14159f * 50.0f * i / 5000.0f);
    }
    
    // Detect crossings
    ZeroCrossingState_t zc_state;
    zero_crossing_init(&zc_state);
    ZeroCrossingBlock_t blocks[50];
    
    int n_blocks = zero_crossing_detect_and_segment(
        &zc_state, sine, 500, blocks, 50
    );
    
    printf("Found %d zero-crossing blocks\n", n_blocks);
    for (int i = 0; i < n_blocks; i++) {
        printf("Block %d: %d samples, f=%.1f Hz\n",
               i, blocks[i].n_samples, (double)blocks[i].f_measured);
    }
}
```

### Integration Test (End-to-End)

1. **Connect hardware:**
   - STM32 running with DSP integrated
   - USB-to-UART adapter connected
   - Power supply connected

2. **Monitor serial output:**
   ```bash
   # Linux
   miniterm.py /dev/ttyUSB0 115200
   
   # Or use Python reader
   python3 power_analyzer/acquisition/stm32_reader.py
   ```

3. **Verify output:**
   - Header 0xAA55AA55 appears periodically
   - Binary data follows (200 bytes)
   - Footer 0x55AA55AA closes frame

4. **Launch GUI:**
   ```bash
   python3 power_analyzer/live_main_stm32.py
   ```

5. **Check measurements:**
   - Vrms, Irms, frequency should match actual signals
   - Power values should match simple calculations (P ≈ V×I for resistive loads)
   - THD should be low for pure sine (< 1%)

### Validation Against Python Reference

**Compare results:**
```python
# Run old Python DSP on same frame
python3 power_analyzer/live_main.py  # old (with DSP)

# Run new STM32 DSP + visualization
python3 power_analyzer/live_main_stm32.py  # new (no DSP)
```

**Acceptance criteria:**
- RMS values within ±0.5%
- Power (P, Q, S) within ±0.5%
- THD within ±1%
- Phase angle within ±1°

### Troubleshooting Guide

| Symptom | Cause | Fix |
|---------|-------|-----|
| "dsp_pipeline.h not found" | Include path incorrect | Add `Core/Inc` to project include paths |
| Build fails with "undefined reference to filters_highpass_init" | .c files not added | Add all 5 .c files to project |
| No serial output | DSP initialization failed | Check `dsp_pipeline_init()` return value |
| Binary garbage on serial | Frame boundaries misaligned | Verify struct packing (__attribute__((packed))) |
| Measurements all zero | ADC codes not converting | Check ADC reference voltage (3.0V) |
| FFT harmonics wrong | Window normalization error | Verify HANN_COHERENT_GAIN_CORRECTION = 2.0 |
| Python GUI crashes | Struct format mismatch | Verify struct.unpack format matches C struct size |

---

## Summary: What Gets Done When

| Phase | What Changes | Approx Time |
|-------|-------------|-------------|
| **Phase 1: Main.c Integration** | Add includes, init, UART transmission | 3–4 hours |
| **Phase 2: Python GUI** | New reader + visualization script | 2–3 hours |
| **Phase 3: Testing** | Unit tests, integration tests, validation | 4–6 hours |
| **Total** | Full migration complete | 9–13 hours |

---

## Key Differences: Before vs. After

### Data Flow

| Aspect | Before | After |
|--------|--------|-------|
| **Processing** | Python (PC) | STM32 (embedded) |
| **Latency** | ~1 second + transmission | ~10 ms + 2 ms transmission |
| **Bandwidth** | 2052 bytes/frame | 200 bytes/frame |
| **Python Role** | Calculate DSP | Visualize only |
| **Scalability** | Limited by PC CPU | Independent of PC |

### Performance Impact

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **UART Traffic** | 2052 B/frame | 200 B/frame | 10× reduction |
| **Transmission Time** | ~18 ms | ~2 ms | 9× faster |
| **Processing Latency** | On PC (~100 ms) | On STM32 (~10 ms) | 10× faster |
| **PC CPU Usage** | DSP heavy | Minimal (UI only) | Significant relief |

---

**Ready to start? Begin with [Part 2: Step-by-Step Main.c Integration](#part-2-step-by-step-mainc-integration)**
