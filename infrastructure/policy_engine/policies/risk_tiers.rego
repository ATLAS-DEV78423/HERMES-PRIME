package sentinel.risk_tiers

risk_tier["filesystem.read"] := "T0"
risk_tier["miner.dispatch"] := "T0"
risk_tier["filesystem.write"] := "T1"
risk_tier["filesystem.commit"] := "T2"
risk_tier["capability.request"] := "T1"
risk_tier["memory.write"] := "T2"
risk_tier["execution.command"] := "T2"
