# Quanta 03 — Pit loss

## Concepto

El **pit loss** es el tiempo perdido al entrar a boxes, comparado con quedarse en pista. No es solo el "tiempo del pit stop" (que en F1 son 2-3 segundos):

```
pit_loss = (lap_time_in + duración_stop + lap_time_out) - 3·lap_time_potencial
```

Donde:

- `lap_time_in` = vuelta de entrada (más lenta porque hay frenado para box)
- `duración_stop` = tiempo estacionario del coche
- `lap_time_out` = vuelta de salida (más lenta porque hay aceleración)
- `lap_time_potencial` = vuelta normal con neumáticos del momento

Típicamente está entre **18 y 24 segundos** dependiendo del circuito y del equipo.

## Por qué importa para el producto

El pit loss es la **barrera** que el undercut tiene que superar. Si subestimamos pit loss, generamos falsos positivos. Si sobreestimamos, no detectamos undercuts viables.

## Cómo se modela en PitWall

### V1 (entregable)

Calculamos la **mediana histórica por (circuito, equipo)** con los datos
ingeridos disponibles. En Day 6 el alcance real es el set demo 2024
(Bahrain, Monaco, Hungary):

```sql
SELECT 
  circuit_id, 
  team_code, 
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pit_loss_ms) AS pit_loss_ms,
  COUNT(*) AS n_samples
FROM pit_stops
WHERE n_samples >= 5  -- solo estimaciones con suficientes muestras
GROUP BY circuit_id, team_code;
```

Persistido en tabla `pit_loss_estimates`. También se persiste un fallback
por circuito con `team_code IS NULL`.

### Fallbacks (en orden)

1. Mediana específica `(circuit_id, team_code)`.
2. Si `n_samples < 5`, mediana del circuito (todos los equipos).
3. Si tampoco hay datos, constante conservadora del motor (`DEFAULT_PIT_LOSS_MS = 21_000`).

## Estimación Day 6

El fitting actual prefiere `pit_stops.pit_loss_ms` cuando FastF1 lo provee.
Si no existe, estima de forma conservadora:

```text
pit_loss_ms = pit_in_lap_ms + pit_out_lap_ms - 2 * median_nearby_clean_lap_ms
```

Las vueltas limpias cercanas son del mismo piloto y sesión, no son pit-in/out,
son válidas, tienen pista verde cuando el dato existe y quedan entre 60-180 s.
Se descartan muestras fuera de 10-40 s antes de calcular medianas.

Última corrida demo:

| Circuito | Fallback circuito | Samples |
|----------|-------------------|---------|
| bahrain | 25,071 ms | 40 |
| monaco | 20,561 ms | 7 |
| hungary | 20,393 ms | 40 |

Monaco queda funcional pero ruidoso por pocos samples.

## Por qué varía

| Factor | Efecto en pit loss |
|--------|---------------------|
| Longitud y forma del pit lane | Mónaco corto, Bahrein largo |
| Speed limit | 60 km/h vs 80 km/h |
| Equipo | Algunos teams hacen stops de 2.0 s, otros de 2.8 s consistentemente |
| Posición de la salida del pit lane | Si sales en la curva 1 o en la recta principal cambia |
| Tráfico al salir | Variable carrera a carrera; V1 lo ignora |

## Ejemplo numérico

Mónaco 2024, McLaren:

```sql
-- Datos hipotéticos
team='McLaren', circuit='monaco', samples=8, median pit_loss=22_400 ms
```

→ `pit_loss_estimates[(monaco, McLaren)] = 22_400 ms`

Si en V1 estimamos pit loss de Mercedes en Mónaco con solo 2 samples (n_samples < 5), caemos al fallback de circuito (mediana de todos los equipos en Mónaco).

## Riesgos / variantes

- **Slow stop**: si un equipo tiene un fallo (rueda mal apretada), ese pit_loss es 5+ segundos de outlier. Por eso usamos mediana, no media.
- **Pit window forzada**: stops bajo SC tienen pit_loss menor (porque todos van más despacio en pista). Filtrar pit stops bajo SC del cálculo.
- **Cambio de reglamento**: 2022 vs 2024 son eras distintas; teóricamente debería ajustar. V1 mezcla 2022-2024 simple.

## Implementación

- Cálculo histórico: [`scripts/fit_pit_loss.py`](../../scripts/fit_pit_loss.py)
- Validación: [`scripts/validate_pit_loss.py`](../../scripts/validate_pit_loss.py)
- Tabla: `pit_loss_estimates` (ver [`docs/interfaces/db_schema_v1.sql`](../interfaces/db_schema_v1.sql))
- Lookup en runtime: [`backend/src/pitwall/engine/pit_loss.py`](../../backend/src/pitwall/engine/pit_loss.py)

## Quanta relacionadas

- [01 — Undercut](01-undercut.md)
- [04 — Ventana de undercut](04-ventana-undercut.md)
