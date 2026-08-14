# INSTITUTIONAL TRADING BOT STATUS — ESPECIFICACIÓN MAESTRA 2026

## Equipo institucional

La plataforma se diseña, audita y mejora bajo una estructura institucional compuesta por:

- Chief Software Architect
- Principal AI Engineer
- Senior Backend Engineer
- DevSecOps Engineer
- Site Reliability Engineer (SRE)
- Quant Researcher
- Portfolio Risk Manager
- Execution Engineer
- Data Engineer
- QA Automation Engineer
- AI Governance Officer

## Objetivo

Diseñar, auditar y mejorar continuamente el **Institutional Trading Bot Status** como plataforma empresarial de investigación, validación, ejecución supervisada y gobierno de trading algorítmico.

La prioridad absoluta es preservar capital, integridad de datos, seguridad, trazabilidad, reproducibilidad y cumplimiento antes que maximizar rentabilidad.

## Reglas innegociables

1. Operar por etapas: `RESEARCH → BACKTEST → WALK_FORWARD → PAPER → TESTNET → LIVE_PILOT → LIMITED_LIVE`.
2. `LIVE_TRADING_ENABLED=false` por defecto.
3. No operar dinero, emitir órdenes reales, modificar credenciales, ampliar permisos, borrar datos ni desplegar a producción sin aprobación humana explícita.
4. Toda acción crítica requiere idempotencia, auditoría, política, evidencia, rollback y kill switch.
5. La falta de evidencia produce `NO_GO`.
6. No considerar implementado un componente porque exista código, configuración o una bandera `enabled`.
7. Distinguir: `HECHO_VERIFICADO`, `INFERENCIA`, `HIPÓTESIS`, `RECOMENDACIÓN` e `INFORMACIÓN_INSUFICIENTE`.
8. Nunca guardar secretos en Git, logs, artefactos, prompts, dashboards ni ejemplos.
9. Aplicar deny-by-default, mínimo privilegio, separación de funciones y doble aprobación para acciones de alto riesgo.
10. Los agentes de IA solo asisten; no pueden promover estrategias, alterar límites de riesgo ni operar capital autónomamente.

## Madurez

- `PROPOSED`: idea documentada.
- `ADR_APPROVED`: arquitectura aprobada.
- `IMPLEMENTING`: en construcción.
- `EXPERIMENTAL`: prototipo aislado.
- `VALIDATED`: pruebas funcionales superadas.
- `CERTIFIED`: seguridad, rendimiento, resiliencia y evaluación aprobados.
- `PAPER_READY`: autorizado solo para paper.
- `TESTNET_READY`: autorizado para prueba.
- `LIVE_PILOT_READY`: capital mínimo y límites estrictos.
- `PRODUCTION_READY`: SLO, DR, seguridad, auditoría y gobierno completos.
- `DEGRADED`: operación reducida.
- `SUSPENDED`: bloqueado.
- `RETIRED`: sustituido con trazabilidad.

Toda certificación debe expirar y reevaluarse.

## Arquitectura

Usar inicialmente monorepo modular orientado a dominios.

### Control Plane

API, consola, configuración, feature flags, aprobaciones, políticas, identidad, comandos, eventos, workflows y kill switch.

### Data Plane

Datos de mercado, features, modelos, señales, órdenes, posiciones, métricas y evidencias.

### Runtime Plane

Agentes, MCP, herramientas, sandboxes, workflows y límites.

### Risk Plane

Pre-trade, intraday, portafolio, exposición, drawdown, VaR, CVaR, estrés y bloqueos.

### Observability Plane

Logs, métricas, trazas, costos, SLO, alertas, incidentes y auditoría.

### Domain Services

Investigación cuantitativa, ejecución, portafolio, gobierno y reporting.

## Componentes principales

Control API; Operator Console; Approval Engine; Policy Decision Point; Identity and Access; Command Bus; Event Bus; Workflow Orchestrator durable; Agent Registry; Capability Registry; Model Registry; Model Router; AI Gateway; MCP Gateway; Memory Service; Knowledge Graph; Evidence Ledger; Dataset Registry; Feature Store point-in-time; Backtesting Engine; Walk-Forward Engine; Strategy Certification; OMS; EMS; Broker/Exchange Adapters; Smart Order Router; Risk Policy Engine; Portfolio Construction; Reconciliation; OpenTelemetry; CI/CD; GitOps; IaC; SBOM; firmas; procedencia; Disaster Recovery; Digital Twin y AIOC limitado.

## Gobierno de datos

Cada dataset debe registrar propietario, fuente, licencia, versión, hash, zona horaria, ventana, transformaciones, calidad y procedencia.

Aplicar sincronización temporal, contratos, detección de missing values, outliers y duplicados, ajustes corporativos, point-in-time joins, prevención de leakage y look-ahead bias, separación train/validation/test/holdout, versionado de features, retención, clasificación, evidencia inmutable y monitoreo de frescura y cambios de esquema.

Los datos sintéticos deben identificarse y nunca mezclarse silenciosamente con datos reales.

## Investigación cuantitativa

Cada estrategia parte de una hipótesis explícita y se compara contra un baseline simple.

Implementar catálogo de hipótesis, experiment tracking, backtesting reproducible, costos realistas, spread, comisión, slippage, financiación, rechazos, gaps, walk-forward, purged/embargoed validation cuando aplique, Monte Carlo, bootstrap, control de múltiples pruebas, análisis por símbolo, sesión, volatilidad y régimen, estabilidad fuera de muestra, sensibilidad de parámetros, capacidad, liquidez, estrés y certificación.

No promover por win rate aislado.

## Métricas

Registrar:

- PnL bruto/neto
- expectancy
- Profit Factor neto
- Sharpe
- Sortino
- Calmar
- drawdown
- recovery factor
- hit rate
- turnover
- exposición
- apalancamiento
- VaR
- CVaR
- skew
- kurtosis
- autocorrelación
- estabilidad por régimen
- comisiones
- spread
- slippage mean/median/p95/p99
- latencia mean/p95/p99
- reject rate
- fill ratio
- partial fills

Para modelos:

- Brier Score
- Log Loss
- ROC-AUC
- PR-AUC
- calibration error
- precision
- recall
- F1
- PSI
- KS
- feature drift
- concept drift
- estabilidad temporal

Toda métrica debe incluir fórmula, ventana, unidad, fuente e incertidumbre.

## GO / NO_GO

- `RESEARCH → BACKTEST`: hipótesis, datos y protocolo reproducible.
- `BACKTEST → WALK_FORWARD`: costos, baseline, ausencia de leakage y estabilidad mínima.
- `WALK_FORWARD → PAPER`: holdout limpio, resultados por régimen y riesgo controlado.
- `PAPER → TESTNET`: reconciliación, idempotencia, telemetría, slippage y latencia aceptables.
- `TESTNET → LIVE_PILOT`: OCO verificadas, kill switch probado, runbooks y aprobación.
- `LIVE_PILOT → LIMITED_LIVE`: capital mínimo, límites duros, monitoreo, rollback y evidencia.

Todo GO tiene expiración. Toda regresión crítica produce `DEGRADED` o `SUSPENDED`.

## Ejecución

Cada orden debe incluir:

- `client_order_id`
- `idempotency_key`
- timestamp sincronizado
- estrategia
- versión
- señal
- riesgo
- aprobación
- política

Implementar validación pre-trade, prevención de duplicados, cancel/replace, fills parciales, OCO, timeouts, retries con backoff/jitter, circuit breakers, rate limits, smart routing, reconciliación de órdenes/fills/posiciones/balances, detección de stale orders, latencia, bloqueo por desconexión y kill switch global y por estrategia.

Ningún agente de IA puede tener permisos de retiro.

## Riesgo

Controles en cuatro niveles:

1. **Trade:** stop, tamaño, riesgo por operación, spread, slippage y validez.
2. **Estrategia:** pérdida diaria, drawdown, posiciones, régimen y drift.
3. **Portafolio:** exposición, correlación, concentración, leverage, VaR, CVaR y liquidez.
4. **Sistema:** salud, reconciliación, datos, broker, latencia, seguridad y telemetría.

El motor de riesgo debe aprobar antes de aceptar órdenes; si no está disponible, bloquear.

Definir límites por símbolo, estrategia, cuenta, sesión, sector, factor y contraparte, además de emergency lock, daily loss limit, max drawdown y cooldown.

## Portafolio

Implementar risk parity, volatility targeting, dynamic risk budgeting, correlation clustering, factor exposure, asignación por estrategia, turnover control, rebalanceo, margen, cash management, hedging, attribution y promotion gate.

Detectar concentración oculta y correlaciones que aumentan durante estrés.

## IA, modelos y agentes

Todo modelo registra versión, dataset, features, parámetros, métricas, propietario, riesgo y certificación.

Toda inferencia crítica es trazable.

El Agent Registry administra definiciones, no miles de procesos permanentes.

Cada agente incluye identidad, rol, capacidades, herramientas permitidas/prohibidas, modelo, presupuesto, límites de tiempo/pasos/tokens, riesgo, memoria, evaluaciones, estado, firma y TTL.

Instanciar bajo demanda en sandbox, con egress allowlist y mínimo privilegio.

Probar prompt injection, tool poisoning, memory poisoning, data exfiltration, excessive agency y hallucination.

Validar salidas críticas con esquemas e inspección independiente.

## Memoria y Knowledge Graph

Separar working, session, episodic, semantic y procedural memory, más knowledge graph.

Cada recuerdo registra fuente, confianza, sensibilidad, fecha, validez, retención, hash y evidencia.

Clasificar como `CLAIM`, `INFERENCE`, `HYPOTHESIS`, `VERIFIED_FACT`, `REJECTED` o `STALE`.

La memoria de IA nunca se convierte automáticamente en hecho.

## Seguridad y DevSecOps

Implementar OpenBao/Vault, OIDC, workload identity, credenciales temporales, RBAC/ABAC, policy-as-code, SAST, dependency scanning, container scanning, IaC scanning, secret scanning, SBOM, firma de artefactos, procedencia SLSA, acciones CI fijadas por SHA, branch protection, CODEOWNERS, network policies, cifrado, backups, recuperación e incident response.

Contenedores sin privilegios y filesystem de solo lectura cuando sea posible.

La remediación automática nunca amplía permisos ni modifica secretos maestros.

## Observabilidad y SRE

Instrumentar con OpenTelemetry trazas distribuidas, logs estructurados, métricas, costos, llamadas a modelos/herramientas, órdenes, fills, riesgo y aprobaciones.

Definir SLO, error budgets, alertas, runbooks, on-call y postmortems.

Medir disponibilidad, error rate, latencia p50/p95/p99, saturación, colas, retries, timeouts, circuit breakers, MTTD, MTTR, RPO y RTO.

La pérdida de telemetría crítica degrada el sistema a modo seguro.

## Pruebas

Exigir pruebas unitarias, integración, contratos, property-based, mutation testing en riesgo/ejecución, end-to-end, rendimiento, carga, caos, seguridad, adversariales, recuperación, migraciones, golden datasets y regresión.

Ningún test omitido cuenta como superado.

Conservar semillas, hardware, versión, commit, dataset y configuración.

## DevOps y plataforma

Usar pyproject y lockfile, builds reproducibles, Docker Compose para desarrollo, Kubernetes solo si la escala lo justifica, Gateway API, GitOps con Argo CD, Helm/Kustomize, OpenTofu, canary o blue-green, artefactos promovidos y no reconstruidos, entornos separados, feature flags, rollback a versión certificada y DR probado.

Medir deployment frequency, lead time, change failure rate y recovery time.

## Autorrecuperación, Digital Twin y AIOC

Automatizar únicamente acciones reversibles, idempotentes y de bajo riesgo: retry, requeue, restart stateless, circuit breaker, quarantine, failover, rollback canary y escalado dentro de límites.

Requerir aprobación para borrar, cambiar políticas, modificar secretos, ampliar permisos, operar dinero o afectar producción.

Probar remediaciones primero en digital twin, luego staging y finalmente canary.

## Investigación diaria

Investigar tecnologías, repositorios, MCP, agentes, IA, trading, seguridad, observabilidad, memoria, DevOps y automatización.

Priorizar documentación oficial, estándares, papers, repositorios oficiales, advisories y benchmarks.

Para cada candidato registrar problema, versión, licencia, mantenimiento, CVE, costo, lock-in, compatibilidad, benchmark, riesgo, alternativa y evidencia.

Clasificar `ADOPT`, `TRIAL`, `ASSESS`, `HOLD`, `REJECT` o `DEPRECATED`.

Puede abrir issue o PR en borrador, nunca auto-merge.

## Reporte institucional diario

1. Resumen ejecutivo.
2. Estado RESEARCH/BACKTEST/WALK_FORWARD/PAPER/TESTNET/LIVE_PILOT.
3. GO/NO_GO global.
4. Cambios desde el último reporte.
5. Riesgos críticos y bloqueadores.
6. Calidad y frescura de datos.
7. Estrategias y métricas.
8. Ejecución, OCO, fills, slippage y latencia.
9. Portafolio, exposición y concentración.
10. Drift y regímenes.
11. Salud de servicios, SLO y error budgets.
12. Seguridad, secretos y vulnerabilidades.
13. Incidentes y remediaciones.
14. Costos e infraestructura.
15. Pruebas y regresiones.
16. Evidencia nueva.
17. Próximas acciones priorizadas.
18. Decisiones que requieren aprobación.
19. Confianza, supuestos y limitaciones.

## Prioridad

`Priority Score = (Impacto × Reducción de Riesgo × Evidencia × Urgencia) / (Esfuerzo × Complejidad Operativa)`

### P0

Secretos, identidad, políticas, riesgo, idempotencia, reconciliación, auditoría, kill switch y CI segura.

### P1

Control plane, datos, backtesting, walk-forward, OMS/EMS, observabilidad, pruebas y DR.

### P2

Modelos, agentes, memoria, knowledge graph, AI Gateway, MCP y evaluación avanzada.

### P3

Digital twin, AIOC, multiagente a escala y optimización experimental.

**No avanzar mientras P0 tenga controles críticos incompletos.**

## Orden de implementación institucional

### P0

OpenBao/workload identity → policy engine → durable order intent → idempotencia → UNKNOWN/reconciliación → Risk Engine fail-closed → kill switches → audit/evidence ledger → aislamiento TESTNET/PROD.

### P1

Data contracts/point-in-time → backtest reproducible → walk-forward → OMS/EMS → adapter real → OCO → OpenTelemetry/SLO → backup + restore → DR → chaos.

### P2

Model Registry → AI Gateway → Agent Registry → MCP Gateway → memoria/knowledge graph → adversarial AI evaluations.

## Production-readiness framework requerido

El repositorio debe evolucionar hacia un framework verificable por CI que incluya como mínimo:

- schemas JSON versionados
- migraciones PostgreSQL
- estados formales del OMS
- contratos de adapters
- políticas Rego
- estructura OpenBao
- suite pytest/chaos
- generador firmado de `production-readiness-manifest.json`

La existencia de archivos no constituye por sí sola evidencia de implementación, validación, certificación ni autorización para producción.

## Criterio final

La plataforma solo está lista cuando es segura, reproducible, observable, auditable, resistente a fallos, económicamente sostenible, estadísticamente defendible y capaz de bloquearse ante incertidumbre.

La cantidad de herramientas, agentes o líneas de código no equivale a madurez.

---

**Estado inicial del repositorio:** especificación arquitectónica/documental. Ningún gate técnico o cuantitativo se considera aprobado hasta que exista evidencia ejecutable y verificable en CI.
