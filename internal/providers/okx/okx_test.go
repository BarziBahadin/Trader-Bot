package okx

import "testing"

func TestSymbolConversion(t *testing.T) {
	if got := instIDFromSymbol("BTC/USDT:USDT"); got != "BTC-USDT-SWAP" {
		t.Fatalf("swap instID = %q", got)
	}
	if got := instIDFromSymbol("PAXG/USDT"); got != "PAXG-USDT" {
		t.Fatalf("spot instID = %q", got)
	}
	if got := symbolFromInstID("BTC-USDT-SWAP", "SWAP"); got != "BTC/USDT:USDT" {
		t.Fatalf("swap symbol = %q", got)
	}
}

func TestSign(t *testing.T) {
	got := sign("2020-01-01T00:00:00.000Z", "GET", "/api/v5/account/balance", "", "secret")
	if got == "" {
		t.Fatal("signature should not be empty")
	}
	if got != sign("2020-01-01T00:00:00.000Z", "GET", "/api/v5/account/balance", "", "secret") {
		t.Fatal("signature should be deterministic")
	}
}
