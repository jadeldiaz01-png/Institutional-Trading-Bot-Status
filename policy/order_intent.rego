package trading.order_intent

default allow := false

allow if {
  input.environment == "PAPER"
  input.risk.allowed == true
  input.kill_switch_clear == true
}

allow if {
  input.environment == "TESTNET"
  input.risk.allowed == true
  input.kill_switch_clear == true
  input.identity.workload_verified == true
}

allow if {
  input.environment == "PROD"
  input.live_trading_enabled == true
  input.human_approval.valid == true
  input.human_approval.approvers >= 2
  input.risk.allowed == true
  input.kill_switch_clear == true
  input.identity.workload_verified == true
  input.audit_available == true
  input.reconciliation_available == true
}

deny_reason contains "live trading disabled" if {
  input.environment == "PROD"
  input.live_trading_enabled != true
}

deny_reason contains "human dual approval required" if {
  input.environment == "PROD"
  input.human_approval.approvers < 2
}

deny_reason contains "risk denied or unavailable" if {
  input.risk.allowed != true
}
