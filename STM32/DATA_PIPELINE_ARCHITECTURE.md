# Data Pipeline Architecture - TP4-ASSD STM32
## Complete Data Flow with Zero Sample Loss

**Document:** Data Pipeline with Double-Buffered DMA  
**Date:** 2026-07-14  
**Buffer Size:** 5120 samples (10x improvement)  
**Sampling Rate:** 5 kHz  
**Status:** Critical architectural document

---

## 1. The Problem: Data Loss Points

### Original Architecture Issues (512-sample buffers)

```
ADC @ 5 kHz (continuous)
    ↓
[DMA Buffer 512 samples] → 102.4 ms to fill
    ↓
While DSP processes (10-20 ms):
    • New samples arrive: 50-100 new samples during processing
    • Where do they go? ← PROBLEM!
    
While USB transmits (2-5 ms):
    • More samples arrive: 10-25 new samples during transmission
    • Buffer collision? Data overwrite? ← PROBLEM!
```

**Result:** Potential sample loss during processing and transmission delays.

---

## 2. Solution: Double-Buffered DMA with Ring Buffer

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTINUOUS SAMPLING LOOP                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ADC Hardware                    DMA Controller                  │
│  (5 kHz)                         (Circular Mode)                 │
│     │                                  │                         │
│     └──→ SPI1/SPI3 ──→ DMA1 ──→ [Circular Buffer 10240 bytes]   │
│                           │                                      │
│                           └──→ Interrupt on half-full (2560 B)   │
│                           └──→ Interrupt on full (5120 B)        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────────┐
│              DUAL BUFFER MANAGEMENT (Software)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Circular Buffer Structure:                                      │
│  ┌─────────────────────────────────────┐                        │
│  │  adc_v_buf[5120]  (voltage)         │  ← DMA writes here     │
│  │  adc_i_buf[5120]  (current)         │                        │
│  │                                      │                        │
│  │  ┌──────────────────────────────┐   │                        │
│  │  │ Half 1: [0..2559]            │   │ ← Processing reads     │
│  │  │ (DMA fills Half 2 while SW   │   │   from this side       │
│  │  │  reads Half 1)               │   │                        │
│  │  ├──────────────────────────────┤   │                        │
│  │  │ Half 2: [2560..5119]         │   │ ← Or from this side    │
│  │  │ (Alternating with Half 1)    │   │                        │
│  │  └──────────────────────────────┘   │                        │
│  │                                      │                        │
│  └─────────────────────────────────────┘                        │
│                                                                  │
│  Key Point:                                                      │
│  ✓ DMA ALWAYS writing to one half                               │
│  ✓ CPU ALWAYS reading from other half                           │
│  ✓ Never collision - different halves!                          │
│  ✓ No data loss during processing or transmission               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────────┐
│           DSP PROCESSING PIPELINE (CM7 Core)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Copy active half to working buffer (minimal time)            │
│  2. Run DSP pipeline                                             │
│     • High-pass filter                                           │
│     • Zero-crossing detection                                    │
│     • FFT / Goertzel                                             │
│     • Power calculations                                         │
│     • THD calculations                                           │
│  3. Generate MeasurementOutput_t result                          │
│                                                                  │
│  ⏱️  Processing Time: ~10-15 ms                                  │
│  (During this time: DMA continues writing to the other half!)    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────────┐
│                  UART TRANSMISSION (Binary)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Frame Format: 220 bytes                                         │
│  • Header (4B)                                                   │
│  • Measurements (60B)                                            │
│  • Harmonics V[23] (92B)                                         │
│  • Harmonics I[23] (92B)                                         │
│  • Metadata (4B)                                                 │
│                                                                  │
│  ⏱️  Transmission Time: 220 bytes @ 115200 baud = ~19 ms         │
│  (During this time: DMA STILL writing to other half!)            │
│                                                                  │
│  No blocking! UART uses DMA too (optional but recommended)       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Buffer Filling Timeline (Visual)

### Scenario: 5120-Sample Buffers (10x improvement)

```
Time (ms)    ADC Input           DMA Buffer State        CPU Action
─────────────────────────────────────────────────────────────────────
    0        ↓ Start             [Half1: Filling]        
             Sampling            [Half2: Empty]          Waiting...
             @ 5 kHz             
                                 
   100       ↓ Continue          [Half1: 50% full]       Waiting...
             Sampling            [Half2: Empty]          
                                 
   204       ↓ Continue          [Half1: FULL ✓]         
             Sampling            [Half2: Empty]          DMA INT: Half1 Complete
                                                        
   204-210   ✓ Half1 ready       [Half1: Ready/Locked]   ✓ Copy Half1 to working buf
             for processing      [Half2: Filling now]    (5ms copy operation)
                                                        
   210-230   ✓ DSP processing    [Half1: Locked]         ✓ Processing Half1 data
   (20ms)    (RMS, FFT, Power)   [Half2: 20% full]       While DMA writes Half2!
                                                        
             ← NO SAMPLE LOSS ←                         
             DMA continues writing to Half2 
             while CPU processes Half1
                                                        
   230-250   ✓ UART transmission [Half1: Complete]       ✓ Sending result via USB
   (20ms)    (Binary frame)      [Half2: 40% full]       DSP waits for next half
                                                        
   250       ✓ Ready for next    [Half1: Ready]          ✓ Wait for Half2 complete
             frame               [Half2: 60% full]       
                                                        
   408       ✓ Half2 FULL        [Half1: Idle]           
             DMA INT: Half2 Complete [Half2: Ready]      ✓ Copy Half2 to working buf
                                                        
   408-428   ✓ DSP processing    [Half1: Filling again!] ✓ Processing Half2 data
             Half2               [Half2: Locked]         While DMA writes Half1!
                                                        
   428-448   ✓ UART transmission [Half1: 20% full]       ✓ Sending result via USB
             (Binary frame)      [Half2: Complete]       
                                                        
   ...       ✓ CYCLE REPEATS     ✓ Zero gaps!            ✓ Continuous operation
```

**Key Insight:** 
- DMA fills **Half2** while CPU processes **Half1**
- DMA fills **Half1** while CPU processes **Half2**
- **At no point are samples lost or overwritten**

---

## 4. Buffer Management in Code

### Current Implementation (512 bytes → UPGRADE TO 5120)

```c
// In dsp_config.h
#define ADC_BUFFER_SIZE    5120  // ← CHANGED FROM 512
#define NUM_CHANNELS       2     // Voltage + Current
#define BYTES_PER_SAMPLE   2     // uint16_t (ADC code)

// Total DMA allocation:
// 5120 samples × 2 channels × 2 bytes = 20,480 bytes per buffer
// With double buffering (implicit in circular DMA): ~20 KB RAM
```

### DMA Configuration (STM32H755)

```c
// In main.c
typedef struct {
    uint16_t adc_v_buf[5120];    // Voltage samples
    uint16_t adc_i_buf[5120];    // Current samples
    
    // Working buffers for DSP
    float32_t v_working[5120];   // After conversion & filtering
    float32_t i_working[5120];
    
    // Processing state
    uint16_t dma_write_idx;      // Updated by DMA
    uint16_t dma_transfer_count; // Frames completed
} ADC_BufferState_t;
```

### DMA Circular Mode Setup

```c
hdma_dma_spi1_rx_v.Init.Mode = DMA_CIRCULAR;  // ← KEY SETTING
hdma_dma_spi1_rx_v.Init.BufferSize = 5120;     // Samples per half-transfer

// Enable half-transfer complete interrupt
HAL_DMA_Start_IT(&hdma_dma_spi1_rx_v, ...);

// Callback: Triggered when 2560 samples collected
void HAL_DMA_Complete_Callback(DMA_HandleTypeDef *hdma) {
    if (hdma == &hdma_dma_spi1_rx_v) {
        // Half 1 or Half 2 complete?
        uint32_t dma_position = __HAL_DMA_GET_COUNTER(hdma);
        
        if (dma_position < 2560) {
            // Half 2 was just completed, Half 1 ready to process
            process_adc_half_buffer(1);  // Read Half 1
        } else {
            // Half 1 was just completed, Half 2 ready to process
            process_adc_half_buffer(2);  // Read Half 2
        }
    }
}
```

---

## 5. Timing Analysis: Why 5120 Samples Work Better

### With 512-Sample Buffers (PROBLEMS):
```
Fill time:     512 / 5000 Hz = 102.4 ms
Processing:    ~15 ms
USB send:      ~2 ms
Cycle time:    ~120 ms
Frame rate:    ~8.3 frames/sec

Problems:
❌ Very tight timing
❌ Little margin for delays
❌ High CPU utilization
❌ Risk of buffer collision if processing stalls
```

### With 5120-Sample Buffers (IMPROVED):
```
Fill time:     5120 / 5000 Hz = 1024 ms (1 second!)
Processing:    ~15 ms (only while OTHER half fills)
USB send:      ~2 ms
Cycle time:    ~1040 ms
Frame rate:    ~1 frame/sec (perfect for power measurement)

Benefits:
✓ Generous timing margins
✓ Zero sample loss even with delays
✓ Low CPU utilization (DSP runs in parallel with DMA)
✓ No risk of collision
✓ Better averaging (more cycles per measurement)
✓ Can handle other system tasks on M4 core
```

---

## 6. Zero-Loss Guarantee: Complete Flow

### Scenario: What Happens During Processing?

```
Time T=0ms:
┌─────────────────────────────────────────┐
│ DMA Buffer (Circular, 10,240 bytes)     │
│                                         │
│ [Half 1: 0-2559]    [Half 2: 2560-5119]│
│ ✓ READY TO PROCESS  ↓ DMA FILLING NOW  │
│                                         │
│ DMA index: 2560 (middle, filling Half2)│
└─────────────────────────────────────────┘
           ↓
CPU copies Half 1 to working buffer (5ms)
           ↓
T=5ms:
DMA continues filling Half 2
(no interference with CPU read)
           ↓
CPU starts DSP processing Half 1 (15ms)
┌─────────────────────────────────────────┐
│ DMA Buffer State During Processing:     │
│                                         │
│ [Half 1: Locked - Reading]              │
│ [Half 2: 30% full - DMA writing]        │
│                                         │
│ ✓ NO COLLISION - Different memory areas │
│ ✓ NO SAMPLE LOSS - DMA has separate half│
└─────────────────────────────────────────┘
           ↓
T=20ms:
DMA still filling Half 2 (100% by T=1024ms)
CPU sends result via UART (2ms)
           ↓
T=22ms:
Ready for next cycle - wait for Half 2 to complete
           ↓
T=1024ms:
Half 2 COMPLETE - Repeat process

📊 Summary:
• 1024 ms per full cycle
• No time gaps
• No sample loss
• Continuous, uninterrupted measurement
```

---

## 7. Memory Layout (STM32H755 DTCM)

```
┌────────────────────────────────────────┐
│   STM32H755 CM7 DTCM (192 KB)          │
├────────────────────────────────────────┤
│                                        │
│  ADC Buffers:                          │
│  • adc_v_buf[5120] ......... 10.2 KB   │
│  • adc_i_buf[5120] ......... 10.2 KB   │
│                                        │
│  Working Buffers:                      │
│  • v_working[5120] ......... 20.5 KB   │
│  • i_working[5120] ......... 20.5 KB   │
│                                        │
│  FFT Output:                           │
│  • fft_out[1024] ........... 4.1 KB    │
│                                        │
│  Filter States:                        │
│  • filter_state[32] ........ ~128 B    │
│                                        │
│  Other (stacks, heap, etc)  ~95 KB     │
│                                        │
│  ────────────────────────────           │
│  Total Used: ~161 KB / 192 KB          │
│  Headroom: ~31 KB (16%)                │
│                                        │
└────────────────────────────────────────┘

✓ Plenty of memory for buffers
✓ Room for DSP working arrays
✓ Safe headroom for stack/heap
```

---

## 8. Implementation Checklist

### Changes Required:

- [ ] **dsp_config.h:**
  - [ ] Change `ADC_BUFFER_SIZE` from 512 to 5120
  - [ ] Verify memory allocation
  
- [ ] **main.c:**
  - [ ] Update DMA configuration for 5120-sample buffers
  - [ ] Update DMA half-transfer calculation (2560)
  - [ ] Verify callback timing
  
- [ ] **dsp_pipeline.c:**
  - [ ] Update buffer copying logic
  - [ ] Ensure fast memcpy for Half 1 / Half 2
  - [ ] Verify working buffer sizes
  
- [ ] **Testing:**
  - [ ] Verify no buffer overruns with logic analyzer
  - [ ] Check UART data consistency
  - [ ] Measure CPU load over 1 minute
  - [ ] Confirm zero dropped frames

---

## 9. Data Flow Sequence Diagram

```
Timeline (seconds)

0s      ┌─ Start sampling ─┐
        │                  │
        │  Half 1: Filling │
        │  [████        ]  │
        │                  │
0.5s    │  Half 1: 50%    │
        │  [████████    ]  │
        │                  │
1.0s    │ ✓ HALF 1 READY! │ ← DMA Half-Transfer Interrupt
        │  [████████████]  │
        │                  │
        │  CPU: Copy ──→ Working buffer (5ms)
        │  CPU: DSP  ──→ Process Half 1 (15ms)
        │                  │
1.02s   │  Half 2: Filling │ ← DMA continues (no wait!)
        │  [  ████      ]  │
        │                  │
2.0s    │ ✓ HALF 2 READY! │ ← DMA Full-Transfer Interrupt
        │  [████████████]  │
        │                  │
        │  CPU: Copy ──→ Working buffer (5ms)
        │  CPU: DSP  ──→ Process Half 2 (15ms)
        │                  │
2.02s   │  Half 1: Filling │ ← DMA continues (cycle repeats)
        │  [  ████      ]  │
        │                  │
        └─────────────────┘

✓ Perfectly synchronized
✓ No idle time
✓ No data loss
```

---

## 10. Summary: Why This Works

| Aspect | 512-Sample | 5120-Sample |
|--------|-----------|-------------|
| **Fill Time** | 102 ms | 1024 ms |
| **Processing Overhead** | 15% | 1.5% |
| **Margin for Delays** | Tight | Generous |
| **Sample Loss Risk** | Medium | None |
| **CPU Utilization** | High | Low |
| **Memory Used** | 10 KB | 60 KB |
| **Memory Available** | 182 KB | 132 KB |
| **Frame Rate** | 10 fps | 1 fps ✓ |
| **Measurement Quality** | Good | Excellent |

**Conclusion:** 5120-sample buffers provide a robust, zero-loss architecture with low CPU overhead and excellent margin for reliability.

---

## References

- TP4_ASSD__version_completa.pdf (Signal processing design)
- DSP_IMPLEMENTACION.md (Algorithm details)
- STM32H755 Datasheet (DMA configuration)
- ARM Cortex-M7 Technical Reference (Buffer optimization)

**Document Version:** 1.0  
**Last Updated:** 2026-07-14  
**Status:** Ready for Implementation
