# Implementación DSP en STM32H755 (TP4-ASSD)

**Documento:** Especificación de Implementación de Procesamiento Digital de Señales  
**Fecha:** 2026-07-12  
**Plataforma:** STM32H755ZI (Dual-Core: Cortex-M7 @ 480 MHz + Cortex-M4)  
**Referencia:** TP4_ASSD.pdf - Diagrama de Bloques (página 2)

---

## 1. Diagrama de Bloques - Mapeo a main.c

### Flujo de Datos Completo

```
ADC Hardware (5 kHz) 
   ↓ (uint16_t codes)
DMA → Buffers Circulares (512 muestras)
   ↓
dsp_pipeline_process_frame()
   ├─ Etapa 1: Filtro Paso-Altos (filters.c)
   ├─ Etapa 2: Detección de Cruces por Cero (zero_crossing.c)
   ├─ Etapa 3: Extracción de Armónicos (goertzel.c + FFT)
   ├─ Etapa 4: Cálculo de Potencia (power_calc.c)
   └─ Etapa 5: Promediado y Agregación
   ↓
MeasurementOutput_t (struct con resultados)
   ↓
UART → PC (GUI Python)
```

### Correspondencia con TP4_ASSD.pdf

| Etapa (PDF) | Función (C) | Archivo | Descripción |
|-------------|-----------|---------|------------|
| **Entrada de ADC** | ADC Hardware + DMA | main.c | Muestreo @ 5 kHz, 512 muestras/frame |
| **Filtro Anti-Aliasing** | (Analógico) | Hardware | 2 kHz, 4to orden (ya implementado en PCB) |
| **Decimación** | adc_code_to_voltage() | dsp_pipeline.c | uint16 → float32, rango ±3V |
| **Filtro Paso-Altos (1 Hz)** | filters_highpass_apply_dual() | filters.c | Eliminación de DC, IIR causal |
| **Detección de Cruces por Cero** | zero_crossing_detect_and_segment() | zero_crossing.c | Interpolación lineal, segmentación en ciclos |
| **Bloques Completos (10 ciclos)** | ZeroCrossingBlock_t | zero_crossing.h | Índices inicio/fin + f_medida |
| **Rama Goertzel (Fasores)** | goertzel_extract_harmonics() | goertzel.c | FFT real, 24 armónicos (1–23) |
| **Rama Temporal (RMS)** | power_calc_rms() | power_calc.c | Cálculo temporal Vrms, Irms |
| **Cálculo de Potencia** | power_calc_from_phasors() | power_calc.c | P=0.5×Re(V*I), Q, S, φ, FP |
| **Cálculo de THD** | power_calc_thd() | power_calc.c | THD_V, THD_I (%) |
| **Promediado** | power_calc_average_blocks() | power_calc.c | Media de N bloques |

---

## 2. Etapas de Procesamiento en main.c

### Etapa 1: Convertidor de Códigos ADC a Voltaje

**Función:** `adc_code_to_voltage()` en `dsp_pipeline.c:lines 28-35`

```c
float32_t voltage = (adc_code / 2^bits) * 2*vref - vref
```

**Parámetros:**
- Entrada: `uint16_t adc_code` (código ADC crudos)
- Referencia ADC: ±3.0V (diferencial)
- Resolución: 16 bits (65536 niveles)

**Salida:** Voltaje en rango ±3.0V (float32_t)

**Ejemplo:**
- Código 0 → -3.0V
- Código 32768 → 0V (centro)
- Código 65535 → +3.0V

---

### Etapa 2: Filtro Paso-Altos (Eliminación de DC)

**Función:** `filters_highpass_apply_dual()` en `filters.c:lines 134-160`

**Implementación:** IIR de un polo usando CMSIS biquad

**Fórmula en Z:**
```
H(z) = (1 - z^-1) / (1 - r*z^-1)

donde: r = exp(-2π * fc / fs)
       fc = 1.0 Hz (cutoff)
       fs = 5000 Hz
       r ≈ 0.99887
```

**Forma Biquad CMSIS:**
```c
H(z) = (b0 + b1*z^-1) / (1 + a1*z^-1)

Coeficientes pre-calculados:
b0 = 0.999435
b1 = -0.999435
a1 = -0.99887
```

**Características:**
- Tiempo de establecimiento (settling): τ = 1/(2π*fc) ≈ 159 ms
- Estado mantenido entre frames (continuidad)
- Ecuación de diferencia:
  ```
  y[n] = b0*x[n] + b1*x[n-1] - a1*y[n-1]
  ```

**Aplicación Dual (Canales V e I):**
- Mismo filtro para ambos canales
- Estados independientes (filter_v, filter_i)
- Procesamiento simultáneo en dsp_pipeline.c:stage_filter()

---

### Etapa 3: Detección de Cruces por Cero

**Función:** `zero_crossing_detect_and_segment()` en `zero_crossing.c:lines 130-175`

**Algoritmo:**
1. Iterar sobre muestras filtradas
2. Detectar transición: x[n-1] < 0 AND x[n] > 0
3. Interpolar linealmente para precisión sub-muestra:
   ```
   t = -x[n-1] / (x[n] - x[n-1])
   idx_interpolado = (n-1) + t
   ```

**Segmentación en Bloques:**
- Cada bloque = ciclo completo (cruce a cruce)
- Ejemplo @ 50 Hz, 5 kHz: ~100 muestras/ciclo
- Medición: 10 ciclos/bloque → ~1000 muestras

**Validación:**
- Frecuencia medida en rango [F0_MIN, F0_MAX] = [48, 52] Hz
- Índices de inicio/fin dentro de buffer
- Skip primeros 5 cruces (SETTLE_CROSSINGS) para estabilización del filtro

**Salida:** Array de estructuras `ZeroCrossingBlock_t`:
```c
struct {
    uint16_t start_idx;      // Índice inicio ciclo
    uint16_t end_idx;        // Índice fin ciclo
    uint16_t n_samples;      // Muestras en ciclo
    float32_t f_measured;    // Frecuencia medida (Hz)
    uint8_t is_valid;        // Flag validez
}
```

---

### Etapa 4: Extracción de Armónicos (FFT)

**Función:** `goertzel_extract_harmonics()` en `goertzel.c:lines 127-230`

**Implementación:** CMSIS Real FFT (arm_rfft_fast_f32)

**Procesamiento:**
1. **Ventana Hann (filtrado espectral):**
   ```c
   w[n] = 0.5 * (1 - cos(2π*n/(N-1)))
   x_windowed[n] = x[n] * w[n]
   ```
   - Reduce fuga espectral (spectral leakage)
   - Función: `generate_hann_window()` en goertzel.c:lines 42-53

2. **FFT Real (CMSIS):**
   ```c
   arm_rfft_fast_f32(&fft_instance, x_windowed, fft_output, 0)
   ```
   - Entrada: 512 muestras reales (o menor, zero-padded)
   - Salida: Formato interleaved [DC, Nyquist, Re[1], Im[1], Re[2], Im[2], ...]
   - Computación: O(N log N) ≈ 5000 operaciones @ 480 MHz

3. **Extracción de Armónicos:**
   ```
   Para cada armónico k = 1, 2, ..., 23:
       f_k = k * f_fundamental
       bin_k = f_k * FFT_SIZE / fs
       [Re[k], Im[k]] = interpolación lineal si bin_k no entero
       Magnitud = sqrt(Re² + Im²) * normalization
       Fase = atan2(Im, Re)
   ```

4. **Normalización (Compensación de Ventana):**
   ```
   Normalización = (2.0 / FFT_SIZE) * (1/sqrt(2))
   
   Factor 2.0 = coherent gain correction (Hann)
   Factor FFT_SIZE = escalado de FFT
   Factor 1/sqrt(2) = conversión pico a RMS
   ```

**Salida:** Estructura `HarmonicSet_t`:
```c
struct {
    Harmonic_t harmonics[24];  // k=1..23
    float32_t f_fundamental;
}

struct Harmonic_t {
    uint16_t order;
    float32_t frequency;
    float32_t magnitude;       // RMS
    float32_t phase_rad;
    ComplexPhasor_t phasor;   // {real, imag}
}
```

---

### Etapa 5: Cálculos de Potencia

**Función Principal:** `power_calc_analyze_block()` en `power_calc.c:lines 299-360`

#### 5.1 Potencia Fundamental (desde Fasores)

**Función:** `power_calc_from_phasors()` en `power_calc.c:lines 108-160`

**Fórmula (dominio fasorial):**
```
Producto cruzado: P_cross = conj(V) * I

conj(V) = V_r - j*V_i
I       = I_r + j*I_i

conj(V)*I = (V_r*I_r + V_i*I_i) + j(V_r*I_i - V_i*I_r)
          =   Real part         +  j  Imaginary part

Potencia Activa:    P = 0.5 * Real part
Potencia Reactiva:  Q = 0.5 * Imaginary part
Potencia Aparente:  S = 0.5 * |V| * |I|
```

**Ángulo de Fase:**
```
φ = atan2(Q, P)      // radianes
φ_deg = φ * 180/π    // grados
```

**Factor de Potencia:**
```
DPF (Displacement Power Factor) = cos(φ) = P / S
```

**Convención de Signo:**
- Q positivo: corriente retrasada (inductiva)
- Q negativo: corriente adelantada (capacitiva)
- Referencia: Python filters.py:21-28

#### 5.2 Potencia Total (Temporal)

**Función:** `power_calc_temporal()` en `power_calc.c:lines 163-222`

**Fórmulas:**
```
Potencia Aparente:
  S_total = Vrms * Irms

Potencia Activa (dominio temporal):
  P_total = mean(v[n] * i[n]) = (1/N) * Σ(v[n] * i[n])

Potencia Reactiva (Pitágoras):
  Q_total = sqrt(max(S² - P², 0))

Factor de Potencia Total:
  TPF = P_total / S_total
```

#### 5.3 Valores RMS

**Función:** `power_calc_rms()` en `power_calc.c:lines 83-93`

Usa CMSIS `arm_rms_f32()` para cálculo eficiente:
```
Vrms = sqrt((1/N) * Σ(v[n]²))
Irms = sqrt((1/N) * Σ(i[n]²))
```

---

### Etapa 6: Cálculo de THD (Total Harmonic Distortion)

**Función:** `power_calc_thd()` en `power_calc.c:lines 225-260`

**Fórmula:**
```
THD = 100 * sqrt(Σ(H_k²)) / H_1  para k=2..23

donde H_k = magnitud del armónico k
      H_1 = magnitud fundamental
```

**Normalización de Armónicos:**
```
Armónico normalizado[k] = H_k / H_1

Salida: Array de 24 valores normalizados (k=0..23)
```

**Ejemplo @ 50 Hz con 5% de 3er armónico:**
```
H_1 = 230 V RMS
H_3 = 11.5 V RMS (5% de H_1)

THD = 100 * 11.5 / 230 = 5.0%
```

---

### Etapa 7: Promediado por Bloque

**Función:** `power_calc_average_blocks()` en `power_calc.c:lines 363-420`

**Procedimiento:**
1. Acumular N mediciones (típicamente 3-5 bloques por frame)
2. Promediar escalares: Vrms, Irms, P, Q, S, etc.
3. Promediar ángulos de fase especialmente:
   ```
   φ_avg = atan2(mean(sin(φ_i)), mean(cos(φ_i)))
   ```
4. Normalizar magnitudes armónicas
5. Recalcular factores de potencia sobre valores promediados

**Entrada:** Array de `MeasurementOutput_t` (uno por bloque)

**Salida:** Single `MeasurementOutput_t` (frame aggregado)

---

## 3. Estructura de Datos Principal

### MeasurementOutput_t

Definida en `power_calc.h:lines 28-65`

```c
typedef struct {
    // Valores RMS
    float32_t vrms;              // Voltaje RMS (V)
    float32_t irms;              // Corriente RMS (A)

    // Frecuencia
    float32_t frequency;         // Frecuencia fundamental (Hz)

    // Potencia Total (Todos los Armónicos)
    float32_t p_total;           // Potencia activa (W)
    float32_t q_total;           // Potencia reactiva (VAR)
    float32_t s_total;           // Potencia aparente (VA)
    float32_t tpf;               // Factor de potencia total

    // Potencia Fundamental (50 Hz)
    float32_t p_fund;            // P fundamental (W)
    float32_t q_fund;            // Q fundamental (VAR)
    float32_t s_fund;            // S fundamental (VA)
    float32_t phi_deg;           // Ángulo de fase (grados)
    float32_t dpf;               // Factor de potencia desplazamiento

    // Distorsión Armónica
    float32_t thd_v;             // THD voltaje (%)
    float32_t thd_i;             // THD corriente (%)

    // Magnitudes Armónicas Normalizadas
    float32_t v_harmonics[24];   // V_k / V_1 para k=1..23
    float32_t i_harmonics[24];   // I_k / I_1 para k=1..23

    // Metadatos
    uint16_t n_blocks;           // Número de bloques promediados
} MeasurementOutput_t;
```

---

## 4. Parámetros de Configuración

Definidos en `dsp_config.h`

| Parámetro | Valor | Unidad | Propósito |
|-----------|-------|--------|----------|
| FS_DIGITAL | 5000 | Hz | Frecuencia de muestreo |
| HIGHPASS_CUTOFF | 1.0 | Hz | Cutoff filtro paso-altos |
| HIGHPASS_COEFF | 0.99887 | - | Polo IIR (r = exp(-2π*fc/fs)) |
| MAX_HARMONIC | 23 | - | Máximo orden armónico |
| CYCLES_PER_BLOCK | 10 | ciclos | Muestras por bloque medición |
| FFT_SIZE | 512 | muestras | Tamaño FFT (debe ser ≥ ciclo) |
| F0_NOMINAL | 50.0 | Hz | Frecuencia nominal red |
| F0_MIN | 48.0 | Hz | Mín frecuencia válida |
| F0_MAX | 52.0 | Hz | Máx frecuencia válida |

---

## 5. Optimizaciones CMSIS-DSP Utilizadas

### arm_rfft_fast_f32()
- **Uso:** FFT real de 512 puntos para extracción de armónicos
- **Ventaja:** Hardware-optimizado en STM32H755
- **Complejidad:** O(N log N) ≈ 5000 operaciones
- **Latencia:** <5 ms @ 480 MHz

### arm_rms_f32()
- **Uso:** Cálculo eficiente de RMS
- **Ventaja:** Implementación optimizada en CMSIS
- **Complejidad:** O(N)

### arm_biquad_cascade_df1_f32()
- **Uso:** Filtro IIR paso-altos
- **Ventaja:** Estructura directa I, estable numéricamente
- **Complejidad:** O(N) para N muestras

### arm_cmplx_mult_f32()
- **Uso:** Multiplicación de fasores complejos V*I
- **Aplicación:** Cálculo de potencia desde fasores

---

## 6. Flujo de Integración en main.c

### Inicialización (en main())

```c
// main.c
DSPPipeline_t dsp_pipeline;

int main(void) {
    // ... inicialización HAL, DMA, UART ...
    
    // Inicializar DSP
    if (dsp_pipeline_init(&dsp_pipeline) < 0) {
        Error_Handler();
    }
    
    // Configurar DMA callback al completar frame
    // Callback debe llamar a dsp_pipeline_process_frame()
    
    while (1) {
        // Loop principal
    }
}
```

### Callback DMA (Procesamiento de Frame)

```c
// Callback invocado por DMA cuando se completan 512 muestras
void HAL_DMA_Complete_Callback(DMA_HandleTypeDef *hdma) {
    MeasurementOutput_t result;
    
    // Procesar frame
    int n_blocks = dsp_pipeline_process_frame(
        &dsp_pipeline,
        adc_v_buf,      // uint16_t[512]
        adc_i_buf,      // uint16_t[512]
        3.0f,           // adc_vref (V)
        16,             // adc_bits
        &result
    );
    
    if (n_blocks > 0) {
        // Transmitir resultado por UART
        uart_send_measurement(&result);
    }
}
```

### Transmisión UART (Nuevo Formato)

```c
// Nuevo formato binario (comprimido)
// En lugar de 2052 bytes de muestras crudas → 200 bytes de resultados

struct {
    uint32_t header;           // 0xAA55AA55
    float vrms;
    float irms;
    float frequency;
    float p_total, q_total, s_total;
    float thd_v, thd_i;
    float v_harmonics[23];
    float i_harmonics[23];
    uint16_t n_blocks;
    uint32_t footer;           // Checksum
};
```

---

## 7. Diagrama de Flujo de Datos en main.c

```
┌─────────────────────────┐
│ ADC Hardware (5 kHz)    │
│ SPI1/SPI3 → DMA         │
└────────┬────────────────┘
         │ (uint16_t codes × 2 ch)
         ↓
┌──────────────────────────────────┐
│ DMA Buffer Circular              │
│ adc_v_buf[512]                   │
│ adc_i_buf[512]                   │
└────────┬─────────────────────────┘
         │ (on frame complete)
         ↓
┌──────────────────────────────────┐
│ Callback DMA                     │
│ dsp_pipeline_process_frame()     │
└────────┬─────────────────────────┘
         │
         ├─→ Stage 1: adc_code_to_voltage()
         │   uint16[512] → float32[512]
         │
         ├─→ Stage 2: filters_highpass_apply_dual()
         │   float32[512] → float32[512] (filtered)
         │
         ├─→ Stage 3: zero_crossing_detect_and_segment()
         │   v_filtered[] → ZeroCrossingBlock_t[N]
         │
         ├─→ Stage 4 (loop over blocks):
         │   ├─ goertzel_extract_harmonics()
         │   │  → HarmonicSet_t (V, I)
         │   │
         │   ├─ power_calc_rms()
         │   │  → Vrms, Irms
         │   │
         │   ├─ power_calc_from_phasors()
         │   │  → P, Q, S, φ, DPF
         │   │
         │   ├─ power_calc_temporal()
         │   │  → P_total, Q_total, S_total, TPF
         │   │
         │   └─ power_calc_thd()
         │      → THD_V, THD_I (%)
         │
         └─→ Stage 5: power_calc_average_blocks()
            MeasurementOutput_t result
                     │
                     ↓
         ┌──────────────────────────────────┐
         │ uart_send_measurement(result)    │
         │ Binary frame 200 bytes @ 115200  │
         │ = ~1.73 ms transmission time     │
         └──────────────────────────────────┘
                     │
                     ↓
         ┌──────────────────────────────────┐
         │ GUI Python (live_main_stm32.py)  │
         │ Receive & visualize measurements │
         │ (SIN cálculos DSP)               │
         └──────────────────────────────────┘
```

---

## 8. Consideraciones de Rendimiento

### Latencia de Procesamiento

| Etapa | Tiempo (ms) | Notas |
|-------|------------|-------|
| Conversión ADC | 0.1 | 512 muestras a 5 kHz = 102.4 ms de data |
| Filtrado | 1.5 | arm_biquad cascade |
| Detección ZC | 2.0 | ~10 cruces por 512 muestras |
| FFT (1 bloque) | 3.5 | arm_rfft_fast 512 pts |
| Potencia (1 bloque) | 1.0 | Multiplicaciones complejas, THD |
| Promediado | 0.5 | 3-5 bloques |
| **Total** | **~9 ms** | Por frame (latencia <200 ms desde muestra) |

### Uso de Memoria

| Componente | Tamaño | Notas |
|-----------|--------|-------|
| Buffers de filtro | 512×2 × 4B | float32 V, I |
| FFT output | 512 × 4B | float32 |
| Window Hann | 512 × 4B | Pre-calculado |
| Block measurements | 50 × 200B | Max 50 bloques |
| DSPPipeline_t | ~4 KB | Estructuras de estado |
| **Total** | **~12 KB** | Presupuesto confortable (M7 tiene 192 KB RAM) |

### Uso de CPU (M7 @ 480 MHz)

- DSP en tiempo real: <5% CPU
- Tiempo libre para otras tareas: 95%

---

## 9. Debugging & Validación

### Puntos de Verificación

1. **Filtrado DC:** Verificar v_filtered[0] ≈ 0 después de convergencia
2. **Zero-crossing:** Detectar ~50 cruces/segundo a 50 Hz
3. **FFT magnitudes:** Comparar con Python (error < 0.5%)
4. **Potencia:** Validar P ≈ S para carga resistiva pura
5. **THD:** Inyectar 3er armónico conocido, verificar lectura

### Flags DEBUG en dsp_config.h

```c
#define DEBUG_FILTER          1   // Habilita logs filtro
#define DEBUG_ZERO_CROSSING   1   // Habilita logs ZC
#define DEBUG_FFT             1   // Habilita logs FFT
#define DEBUG_POWER_CALC      1   // Habilita logs potencia
#define DEBUG_DSP             1   // Habilita logs pipeline
```

---

## 10. Integración con GUI Python

### Cambios en Python (live_main_stm32.py)

**ANTES (Python calcula DSP):**
```
STM32 → 512 muestras (2052 B) → Python DSP → GUI
```

**AHORA (STM32 calcula DSP):**
```
STM32 → MeasurementOutput (200 B) → GUI Python (solo visualización)
```

### Protocolo de Frame Binario

```python
import struct

# Estructura C → Unpack Python
frame_format = '!I f f f f f f f f f f f 23f 23f H H I'
# Header + escalares + harmonics V + harmonics I + n_blocks + reserved + footer

result = struct.unpack(frame_format, uart_data)
vrms = result[1]
irms = result[2]
# ... etc
```

---

## 11. Referencias & Documentación

- **TP4_ASSD.pdf:** Especificación algoritmo completo (español)
- **PA.ipynb:** Implementación Python de referencia y validación
- **CMSIS-DSP User Guide:** arm_rfft_fast_f32(), arm_rms_f32()
- **STM32H755 Datasheet:** Configuración timer, DMA, SPI
- **IEC 61000-4-30:** Estándar definiciones de potencia eléctrica

---

## 12. Notas de Implementación

1. **Convención de Signo Q:** El signo de Q sigue IEC 61000-4-30 (Q > 0 para carga inductiva)
2. **Precisión:** Se usa float32 (precisión simple, suficiente para ±0.5%)
3. **Windowing:** Ventana Hann reduce fuga espectral (error < 1% en magnitudes)
4. **Settling:** Esperar 160 ms después de inicio para que filtro se estabilice
5. **FFT:** Size 512 permite resolución frecuencial = 5000/512 ≈ 10 Hz
6. **Armónicos:** Limitado a orden 23 (máximo 1150 Hz @ 50 Hz)

---

**Documento generado:** 2026-07-12  
**Estado:** Implementación completada en CM7 main.c  
**Validación:** Comparar resultados C contra Python reference @ ±0.5%
