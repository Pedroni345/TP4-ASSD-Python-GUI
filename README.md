# TP4-ASSD — Simulador de Analizador de Potencia


Simulador de escritorio con estética de osciloscopio que da el "primer vistazo"
del instrumento del TP4: un **analizador de potencia** que mide valor RMS de
tensión y corriente, las componentes de potencia P/Q/S, el TPF, el DPF, la fase
φ, la frecuencia fundamental y la THD.

El instrumento real (contraparte de hardware) y el algoritmo de DSP ya validado
están documentados en la raíz del repositorio: `TP4_ASSD (1).pdf` y `PA.ipynb`.

El simulador permite:

1. **Generar manualmente** las señales analógicas `v(t)` e `i(t)` (fundamental,
   continua, fase, ruido y la amplitud de **cada armónico**).
2. Elegir la **ganancia del amplificador diferencial** (PGA) por canal para
   aprovechar todo el rango del ADC, con una barra de llenado y aviso de
   recorte (clipping) en vivo.
3. **Sondear la señal en cada etapa** de la cadena (analógica cruda → filtrada
   anti-alias → cuantizada por el ADC → con la continua removida) y **cambiar las
   frecuencias de corte** del filtro anti-alias y del pasa-altos.
4. Comparar los **resultados ideales (analíticos) contra el DSP "manual"**, con
   el error porcentual de cada parámetro.

---

## El diagrama de bloques y cómo se implementa

El simulador reproduce, etapa por etapa, el diagrama de bloques de la página 2
del PDF. Ese mismo diagrama se dibuja en vivo en la esquina **inferior izquierda**
de la interfaz (`ui/block_diagram.py`) para que el usuario sepa siempre en qué
punto de la cadena está mirando.

```
        Señales analógicas v(t), i(t)
                    │
        ┌───────────▼───────────┐
        │   Filtro Anti-Alias   │   Pasa-bajos 2 kHz   → dsp/filters.py: anti_alias_filter
        └───────────┬───────────┘
        ┌───────────▼───────────┐
        │   ADC / Decimación    │   fs = 5 kHz, 16 bit → dsp/analog_frontend.py: quantize
        └───────────┬───────────┘
        ┌───────────▼───────────┐
        │   Filtro Pasa-altos   │   Digital 1 Hz, DC   → dsp/filters.py: dc_blocker
        └───────────┬───────────┘
        ┌───────────▼───────────┐
        │     Cruce por Cero    │   bloques de 10 ciclos, f_est → dsp/zero_crossing.py
        └─────┬───────────┬─────┘
   ┌──────────▼──┐     ┌──▼──────────────┐
   │  Goertzel   │     │ Cálculo Temporal│   → dsp/goertzel.py + dsp/power_calc.py
   │ (Hann)      │     │ Vrms,Irms,P,S   │
   │ Vf,If,φ,THD │     └──┬──────────────┘
   └──────────┬──┘        │
              └─────┬──────┘
        ┌───────────▼───────────┐
        │  Promediado y Salida  │   promedia N bloques → ui/results_panel.py
        └───────────────────────┘
```

### Mapeo bloque → código

Cada bloque del diagrama corresponde a una función concreta del paquete `dsp/`.
El orquestador es `dsp/pipeline.py`, que toma un `SignalSpec` (lo que define el
usuario en el generador) y un `FrontEndConfig` (ganancias, bits, cortes) y los
hace pasar por toda la cadena.

| Bloque del diagrama | Archivo / función | Qué hace |
|---|---|---|
| **Señales analógicas** | `dsp/signal_gen.py: generate` | Construye `v(t)`, `i(t)` a `fs_analog = 100 kHz` sumando fundamental + DC + armónicos + ruido gaussiano. |
| **Filtro Anti-Alias** | `dsp/filters.py: anti_alias_filter` | Butterworth pasa-bajos (2 kHz por defecto) sobre la señal de alta tasa, antes de muestrear. |
| **ADC / Decimación** | `dsp/analog_frontend.py: process_channel` + `quantize` | Aplica la ganancia del PGA, decima a `fs_digital = 5 kHz` y cuantiza a N bits dentro de ±Vref, con recorte. Acá nace el "escalón" visible en el sondeo del ADC. |
| **Filtro Pasa-altos** | `dsp/filters.py: dc_blocker` / `high_pass_filter` | Quita la continua que introduce el ADC y el offset del frente analógico (ver más abajo). |
| **Cruce por Cero** | `dsp/zero_crossing.py: find_positive_crossings` + `make_blocks` | Detecta cruces positivos con **interpolación** entre muestras, corta en bloques de 10 ciclos y estima `f_est = 10 / (t_fin − t_ini)`. |
| **Goertzel (Hann)** | `dsp/goertzel.py: goertzel_windowed` | Evalúa el fasor de la fundamental y de cada armónico con ventana Hann. De ahí salen Vf, If, Pf, Qf, Sf, φ, DPF y THD. |
| **Cálculo Temporal** | `dsp/power_calc.py: analyze` | Calcula por bloque Vrms, Irms, P_total = mean(v·i), S = Vrms·Irms, Q = √(S²−P²) y TPF = P/S. |
| **Promediado y Salida** | `dsp/power_calc.py` + `ui/results_panel.py` | Promedia los resultados de N bloques y los muestra junto a la referencia ideal. |
| **Referencia ideal** | `dsp/ideal.py: compute` | Valores analíticos exactos desde el `SignalSpec` (sin ruido, filtros ni cuantización), para la columna "Ideal". |

### Fórmulas (PDF, sección 1)

**Cálculo temporal**

```
Vrms = √( (1/N) Σ v[n]² )      Irms = √( (1/N) Σ i[n]² )
P_total = (1/N) Σ v[n]·i[n]    S_total = Vrms·Irms
Q_total = √(S_total² − P_total²)    TPF = P_total / S_total
```

**Por Goertzel (fundamental y armónicos)**

```
P_fund = ½ Re{Vf · If*}    Q_fund = ½ Im{Vf · If*}    S_fund = ½ |Vf|·|If|
φ = ∠(Vf · If*)            DPF = P_fund / S_fund = cos(φ)
THD_V = √(Σ_{k≥2} |Vk|²) / |V1| · 100%   (ídem THD_I)
```

---

## Cómo correrlo

```bash
# desde la raíz del repo
python -m venv .venv
.venv/bin/pip install -r power_analyzer/requirements.txt
.venv/bin/python power_analyzer/main.py
```

(Durante el desarrollo se usó un `.venv` en la raíz. Dependencias:
PyQt6, pyqtgraph, numpy, scipy.)

## Tests

```bash
cd power_analyzer
../.venv/bin/python -m pytest -q
```

La suite valida el fasor de Goertzel, la detección de cruces por cero, el paso
de cuantización y el recorte del ADC, las fórmulas de potencia contra valores
analíticos, y la cadena completa contra la referencia ideal (todo dentro de ~1%
en señal limpia).

---

## Arquitectura

```
power_analyzer/
├── main.py                 punto de entrada (QApplication + MainWindow)
├── requirements.txt
├── core/
│   ├── config.py           constantes, tablas de ganancia del PGA, ADC, cortes
│   └── models.py           dataclasses inmutables: SignalSpec, FrontEndConfig,
│                           StageTraces, Measurements
├── dsp/
│   ├── signal_gen.py       genera v(t), i(t) desde el spec
│   ├── analog_frontend.py  ganancia PGA + anti-alias + ADC (cuantiza/recorta) + HP
│   ├── filters.py          Butterworth (anti-alias) y dc_blocker (pasa-altos)
│   ├── goertzel.py         goertzel_windowed
│   ├── zero_crossing.py    cruces interpolados + bloques de 10 ciclos
│   ├── power_calc.py       cálculo temporal + fundamental + THD
│   ├── ideal.py            referencia analítica
│   └── pipeline.py         orquesta toda la cadena
└── ui/
    ├── theme.py            paleta, hoja de estilo (QSS), pens de pyqtgraph
    ├── scope_widget.py     osciloscopio: trazas V/I, grilla, sondeo por etapa
    ├── harmonic_editor.py  editor por armónico de v(t) e i(t)
    ├── frontend_panel.py   ganancia, llenado del ADC, cortes de los filtros
    ├── results_panel.py    tabla Ideal vs Medido vs %error + espectro
    ├── block_diagram.py    diagrama de bloques (esquina inferior izquierda)
    └── main_window.py      ensambla los paneles y maneja los timers en vivo
```

El flujo de datos es en un solo sentido: la UI arma objetos **inmutables**
(`SignalSpec`, `FrontEndConfig`), `dsp.pipeline` los convierte en `StageTraces`
(para el osciloscopio) y en `Measurements` (para la tabla). Dos timers en
`main_window` manejan un refresco rápido del osciloscopio (~40 FPS) y un refresco
más lento del DSP (sólo recalcula cuando cambia una entrada). El código está
pensado **modular** para las extensiones futuras.

### Detalles de implementación que vale la pena conocer

- **Filtro pasa-altos digital (remoción de continua).** Tiene dos variantes en
  `dsp/filters.py`. La de tiempo real (osciloscopio / visión del microcontrolador)
  es `dc_blocker`: un removedor de continua IIR de primer orden inspirado en el
  código del medidor de energía de Texas Instruments (`dc_filter16.c`). Un
  integrador con fuga *estima* el nivel de continua y se lo resta a cada muestra,
  lo que equivale al pasa-altos canónico `H(z) = (1 − z⁻¹)/(1 − r·z⁻¹)` con polo
  `r = exp(−2π·fc/fs)`. La columna de medición usa un Butterworth de fase cero
  (`filtfilt`) como referencia, igual que el notebook. Como se aclara en el PDF,
  este filtro es **vital**: la continua del frente analógico arruinaría el cálculo
  de Vrms e Irms.
- **Signo en Goertzel.** `power_calc` usa `conj(V)·I` (y no `V·conj(I)`) para que
  una carga inductiva (corriente atrasada) dé Q **positivo**, que es la convención
  física habitual.
- **Ganancia del PGA y rango del ADC.** El mismo ADC de 16 bits sirve tanto para
  una entrada de ±735 V como de ±46 V con sólo cambiar la ganancia; la barra de
  llenado muestra cuánto del rango se está usando y avisa el recorte.
- **Corriente por defecto = 7 A** (el notebook usaba 15 A) porque el frente real
  con shunt satura en ±12,5 A (ganancia G4).

---

## Trabajo Futuro (del PDF)

La modularidad del `dsp/` deja estos pasos como cambios acotados:

- **Energía (Wh):** integrar `P_total` en el tiempo con un acumulador nuevo.
- **Trifásico:** correr tres instancias de `pipeline` y agregar análisis de
  secuencia de fase y desequilibrio de carga.
- **Compensación de phase-lag:** ajustar el desfasaje de muestreo entre canales
  en `analog_frontend` / `signal_gen`.
- **Crest factor:** agregar `pico/rms` por canal en `power_calc`.
