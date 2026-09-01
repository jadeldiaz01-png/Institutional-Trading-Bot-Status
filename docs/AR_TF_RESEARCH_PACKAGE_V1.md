# AR-TF Research Package v1

## Estado

`RESEARCH` únicamente. `LIVE_TRADING_ENABLED=false`. La presencia de este código no constituye evidencia de rentabilidad ni autorización para PAPER, TESTNET o LIVE.

## Hipótesis

Un portafolio long/cash de criptoactivos spot líquidos puede capturar persistencia de tendencia mediante momentum multihorizonte, confirmación de tendencia/breakout y dimensionamiento inverso a volatilidad, siempre que el edge sobreviva costos, regímenes, validación fuera de muestra y múltiples pruebas.

## Componentes

1. **Dataset contract**: UTC, hash, fuente, versión, símbolos, gaps y control point-in-time/survivorship.
2. **Universe builder**: hasta 15 pares USDT líquidos con historia suficiente; stablecoins/tokens apalancados deben excluirse en la implementación de ingestión.
3. **Feature pipeline**: retornos log, momentum 7/30/90/180d, EMA 50/200, Donchian 55d, volatilidad anualizada y liquidez nocional.
4. **Signal engine**: combinación no-negativa de momentum y breakout, bloqueada fuera de `TREND_UP` para Spot long-only.
5. **Regime detector**: `TREND_UP`, `TREND_DOWN`, `SIDEWAYS`, `HIGH_VOL_STRESS`.
6. **Volatility estimator**: EWMA inicial; HAR-RV/EGARCH son candidatos de investigación, no dependencias obligatorias v1.
7. **Portfolio construction**: inverse-volatility, límites por activo y exposición bruta.
8. **Cost model**: fee + half-spread + slippage; estrés 1x/2x/3x. Debe extenderse con filtros/rate limits y snapshots históricos de Binance cuando los datos estén disponibles.
9. **Point-in-time backtester**: pesos desplazados una barra; timestamps únicos/ordenados.
10. **Walk-forward**: ventanas temporales train/test con embargo configurable.
11. **Robustness**: block bootstrap, Monte Carlo de drawdown, Deflated Sharpe y PBO.
12. **Certification**: fail-closed; la salida máxima antes de aprobación humana es `PAPER_CANDIDATE`.

## Protocolo obligatorio de investigación

- Congelar manifiesto/hash del dataset antes de optimizar.
- Mantener un holdout final sin tocar.
- Registrar cada combinación de parámetros evaluada, incluso fallidas.
- Comparar contra BTC buy-and-hold, equal-weight y una tendencia simple.
- Calcular resultados netos después de costos.
- Reportar resultados agregados y por símbolo/régimen/año.
- Ejecutar stress de costos 1x/2x/3x, delayed execution, missing bars y shocks de volatilidad.
- Evaluar sensibilidad alrededor de cada parámetro elegido; una isla estrecha de rentabilidad es evidencia contra promoción.
- Reportar intervalos bootstrap y distribución de drawdowns Monte Carlo.
- Aplicar DSR considerando número de trials y PBO sobre configuraciones/cross-validation.
- Ningún resultado in-sample puede decidir promoción.

## Gate RESEARCH -> PAPER

El certificado debe permanecer `NO_GO` ante cualquiera de estas condiciones: dataset no point-in-time, leakage, holdout contaminado, expectancy neta no positiva, Sharpe OOS no positivo, DSR bajo el umbral, PBO sobre el máximo, resultados inestables por régimen/símbolo, costos adversos que eliminan el edge, observaciones insuficientes o evidencia incompleta.

Pasar los gates cuantitativos solo produce `PAPER_CANDIDATE`; PAPER requiere además revisión humana y controles operativos de la especificación maestra.

## Evidencia todavía faltante

Este commit no contiene varios años de market data ni resultados empíricos. Por tanto el estado de AR-TF v1 continúa `PROPOSED/RESEARCH` y el gate global sigue `NO_GO` para PAPER.
