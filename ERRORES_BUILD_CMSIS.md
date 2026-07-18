# Resumen: errores de build tras el clean (CMSIS-DSP) — 2026-07-18

Al hacer **Clean + Build All** en STM32CubeIDE aparecieron tres errores en cadena.
Los tres tenían la misma causa de fondo: **nunca se había hecho un build limpio
desde que se agregaron los archivos de CMSIS-DSP** (commit `802d0aa`). El repo
tenía 36 archivos `.o` viejos commiteados dentro de `Debug/`, así que los builds
anteriores "pasaban" reutilizando objetos viejos sin recompilar nada. El clean
los borró y expuso todos los problemas latentes de una vez.

## Error 1 — `dsp/filtering_functions.h: No such file or directory`

- **Síntoma:** los fuentes de `CM7/Core/Src/CMSIS_DSP/` no compilaban por
  headers `dsp/*.h` inexistentes.
- **Causa:** los fuentes y el `arm_math.h` de `Drivers/CMSIS/Include/` provienen
  de **CMSIS-DSP v1.15.0** (verificado: `arm_math.h` es byte-idéntico al del tag
  v1.15.0, aunque su comentario diga "V1.10.0" — ARM dejó el sello desactualizado).
  Esa versión usa headers divididos en una subcarpeta `Include/dsp/` con 33
  archivos, que nunca se copió al repo. Ojo: no son los fuentes de CMSIS_4
  (esos incluyen solo `arm_math.h`); por eso el link de GitHub de CMSIS_4 no
  coincidía con lo que hay en el repo.
- **Fix (`6ab0c2b`):** se agregaron los 33 headers de `Include/dsp/` del tag
  v1.15.0 en `STM32/Drivers/CMSIS/Include/dsp/`. No hace falta tocar los include
  paths del IDE: caen dentro de `Drivers/CMSIS/Include`, que ya estaba.

## Error 2 — typedefs inexistentes (`arm_biquad_cascade_df1_f32_t`, `arm_rfft_fast_f32_t`)

- **Síntoma:** con los headers ya en su lugar, `filters.c` y `goertzel.c`
  fallaban con "unknown type name". Era el problema que habíamos dejado
  pendiente ("punto 1") — dejó de ser diferible porque bloqueaba el build.
- **Causa:** `filters.h:50` y `goertzel.h:76` usaban nombres de tipo que no
  existen en ninguna versión de CMSIS-DSP.
- **Fix (`6ab0c2b`):** se reemplazaron por los nombres reales de CMSIS:
  - `arm_biquad_cascade_df1_f32_t` → `arm_biquad_casd_df1_inst_f32`
  - `arm_rfft_fast_f32_t` → `arm_rfft_fast_instance_f32`
  - En `mock_arm_math.h` se agregó un alias para que los tests de host sigan
    compilando con el mock.

## Error 3 — `multiple definition of 'filters_highpass_init'` (y de `main`)

- **Síntoma:** la compilación ya pasaba, pero el **link** fallaba: cada función
  DSP estaba definida dos veces.
- **Causa:** `host_dsp_test.c` (programa de validación **solo para PC**, con sus
  propias copias simplificadas de las funciones DSP y su propio `main`) estaba
  dentro de `Core/Src/`, y CubeIDE compila todo lo que hay ahí.
- **Fix (`0e9ab6a`):** se movió a `STM32/host_tests/host_dsp_test.c`, fuera del
  árbol de fuentes del IDE. Sigue funcionando en PC:
  `gcc host_dsp_test.c -I../CM7/Core/Inc -lm` (los 4 suites de test pasan).

## Error 4 — `undefined reference to 'arm_radix8_butterfly_f32'` / `arm_bitreversal_32`

- **Síntoma:** el link fallaba por símbolos de la FFT sin definir.
- **Causa:** al armar la carpeta `CMSIS_DSP/` faltaron tres fuentes que la FFT
  necesita en tiempo de link:
  - `arm_cfft_radix8_f32.c` → define `arm_radix8_butterfly_f32`
  - `arm_bitreversal2.c` → define `arm_bitreversal_32`
  - `arm_bitreversal.c` → define `arm_bitreversal_f32` (camino radix-4 legado)
- **Fix (`78c2cd5`):** se agregaron los tres desde el mismo tag v1.15.0.

## Verificación (sin hardware, con `arm-none-eabi-gcc` local)

- Los 21 objetos DSP (15 de CMSIS + 6 módulos propios) compilan con los mismos
  flags del IDE (`-mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -DCORE_CM7 …`).
- **Cierre de símbolos con `nm`:** todo símbolo `arm_*` referenciado queda
  definido dentro del conjunto; solo quedan sin resolver `memcpy`, `sinf`,
  `sqrtf`, etc., que los aporta `-lc -lm` en el link. No hay más archivos de
  CMSIS faltantes escondidos.

## Error 5 — `arm_math_types.h: No such file or directory` (solo en la otra laptop)

- **Síntoma:** después de clonar el repo en la segunda laptop, el build volvía a
  fallar por headers CMSIS faltantes, aunque en la máquina original compilaba.
- **Causa:** los 14 headers de nivel superior de `Drivers/CMSIS/Include/`
  (`arm_math.h`, `arm_math_types.h`, `arm_common_tables.h`, …) **nunca
  estuvieron trackeados en git**: existían solo en el disco de la máquina
  original. El fix del Error 1 commiteó la subcarpeta `dsp/`, pero sus
  compañeros de nivel superior quedaron afuera. El build local pasaba (los
  archivos estaban en el disco); un clon fresco no los recibía.
- **Fix (`8f24175`):** se agregaron los 14 headers a git. `arm_vec_fft.h` no
  hace falta (solo se incluye bajo guardas `ARM_MATH_MVEF`/Helium, que un
  Cortex-M7 nunca activa). La carpeta local `Drivers/CMSIS_DSP_Source/` (12 MB,
  stash de donde se copiaron archivos a mano) no se commitea: el build no la
  referencia.
- **Verificación definitiva:** se hizo un **clon fresco desde git** (solo
  archivos trackeados) y ahí compilan los 21 fuentes DSP **y también**
  `main.c`, `stm32h7xx_it.c`, `stm32h7xx_hal_msp.c` y el system file con los
  include paths del IDE. El repo ya es autocontenido.

## Regla para el futuro

- **CMSIS-DSP está vendoreado en la versión v1.15.0.** Si alguna vez hay que
  agregar más fuentes de CMSIS, sacarlos de ese mismo tag
  (`github.com/ARM-software/CMSIS-DSP`, tag `v1.15.0`) — mezclar versiones fue
  lo que hizo que los headers v1.10 no sirvieran.
- Los `.o` viejos trackeados en `Debug/` fueron los que enmascararon todo esto
  durante semanas; conviene dejar de trackear esa carpeta.
- **Un build verde en la máquina donde se crearon los archivos no prueba que el
  repo esté completo — git solo entrega lo que trackea.** Después de vendorear
  cualquier archivo, verificar con `git ls-files <ruta>` que git lo tomó, y
  ante la duda validar con un clon fresco.
