package market

import "testing"

func TestInferAssetClass(t *testing.T) {
	cases := map[string]string{
		"BTC/USDT:USDT": "crypto",
		"EURUSD":        "forex",
		"XAUUSD":        "metals",
		"USOIL":         "commodities",
	}
	for symbol, want := range cases {
		if got := InferAssetClass(symbol); got != want {
			t.Fatalf("InferAssetClass(%q) = %q, want %q", symbol, got, want)
		}
	}
}

func TestCalculatePositionSize(t *testing.T) {
	instrument := DefaultInstrument("XAUUSD", "paper")
	preview, err := CalculatePositionSize(instrument, 1000, 2350, 1, 10, 20, 5, "USD")
	if err != nil {
		t.Fatal(err)
	}
	if preview.RiskAmount != 10 {
		t.Fatalf("risk amount = %v, want 10", preview.RiskAmount)
	}
	if preview.LotSize < instrument.VolumeMin {
		t.Fatalf("lot size %v below min %v", preview.LotSize, instrument.VolumeMin)
	}
	if preview.MarginRequired <= 0 {
		t.Fatalf("margin should be positive, got %v", preview.MarginRequired)
	}
}
