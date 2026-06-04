package strategy

import (
	"strings"
	"testing"
	"time"

	"trader/internal/config"
	"trader/internal/market"
)

func TestEvaluateNeedsEnoughCandles(t *testing.T) {
	decision := New(config.Settings{RSIPeriod: 14, FastMA: 20, SlowMA: 50}).Evaluate(map[string][]market.Candle{"15m": market.SyntheticCandles("BTC/USDT", 10)}, false, nil)
	if decision.Signal != "hold" || !strings.Contains(decision.Reason, "not enough candles") {
		t.Fatalf("decision = %+v", decision)
	}
}

func TestEvaluateStopLoss(t *testing.T) {
	candles := market.SyntheticCandles("BTC/USDT", 240)
	for i := range candles {
		candles[i].Timestamp = time.Now().Add(time.Duration(i) * time.Minute).Format(time.RFC3339)
	}
	entry := candles[len(candles)-1].Close * 1.02
	settings := config.Settings{RSIPeriod: 14, FastMA: 20, SlowMA: 50, StopLossPercent: 0.01, TakeProfitPercent: 0.02}
	decision := New(settings).Evaluate(map[string][]market.Candle{"15m": candles, "5m": candles, "1h": candles, "4h": candles}, true, &entry)
	if decision.Signal != "sell" || decision.Reason != "stop-loss hit" {
		t.Fatalf("decision = %+v", decision)
	}
}
