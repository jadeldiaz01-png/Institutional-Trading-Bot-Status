# Institutional Trading Bot Status

Plataforma institucional de investigación, validación, ejecución supervisada y gobierno de trading algorítmico.

## Estado de seguridad por defecto

- `LIVE_TRADING_ENABLED=false`
- Ninguna orden real está autorizada por la mera existencia del repositorio.
- La falta de evidencia produce `NO_GO`.
- Ningún componente se considera implementado solo porque exista código, configuración o una bandera `enabled`.
- Los agentes de IA son asistentes y no pueden promover estrategias, alterar límites de riesgo ni operar capital autónomamente.

## Etapas obligatorias

`RESEARCH → BACKTEST → WALK_FORWARD → PAPER → TESTNET → LIVE_PILOT → LIMITED_LIVE`

Cada transición requiere evidencia verificable, controles de riesgo y, cuando corresponda, aprobación humana explícita.

## Especificación maestra

La arquitectura, reglas institucionales, gates, métricas, controles de riesgo, seguridad, SRE, DevSecOps, IA/agentes, datos, ejecución, portafolio y production-readiness framework se documentan en:

`docs/INSTITUTIONAL_TRADING_BOT_STATUS_2026.md`

## Prioridad de implementación

**P0:** secretos, workload identity, políticas, durable order intent, idempotencia, UNKNOWN/reconciliación, Risk Engine fail-closed, kill switches, audit/evidence ledger y aislamiento TESTNET/PROD.

**P1:** data contracts/point-in-time, backtest reproducible, walk-forward, OMS/EMS, adapter real, OCO, OpenTelemetry/SLO, backup/restore, DR y chaos.

**P2:** Model Registry, AI Gateway, Agent Registry, MCP Gateway, memoria/knowledge graph y evaluaciones adversariales de IA.

## Production readiness

El objetivo técnico es convertir la especificación en gates demostrables por CI mediante schemas JSON, migraciones PostgreSQL, estados formales del OMS, contratos de adapters, políticas Rego, OpenBao, pytest/chaos y un `production-readiness-manifest.json` firmado.

**Estado actual:** especificación documental inicial. No implica `PAPER_READY`, `TESTNET_READY`, `LIVE_PILOT_READY` ni `PRODUCTION_READY`.
