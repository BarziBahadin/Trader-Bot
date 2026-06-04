package market

import (
	"math"
	"strings"
	"time"
)

type Candle struct {
	Timestamp string  `json:"timestamp"`
	Open      float64 `json:"open"`
	High      float64 `json:"high"`
	Low       float64 `json:"low"`
	Close     float64 `json:"close"`
	Volume    float64 `json:"volume"`
}

type Instrument struct {
	Symbol          string   `json:"symbol"`
	DisplayName     string   `json:"display_name"`
	AssetClass      string   `json:"asset_class"`
	Provider        string   `json:"provider"`
	BaseCurrency    string   `json:"base_currency"`
	QuoteCurrency   string   `json:"quote_currency"`
	Digits          int      `json:"digits"`
	Point           float64  `json:"point"`
	ContractSize    float64  `json:"contract_size"`
	VolumeMin       float64  `json:"volume_min"`
	VolumeStep      float64  `json:"volume_step"`
	DefaultLeverage float64  `json:"default_leverage"`
	TickValue       *float64 `json:"tick_value"`
	Spread          *float64 `json:"spread"`
	TradeEnabled    bool     `json:"trade_enabled"`
}

type PositionSizePreview struct {
	Symbol             string  `json:"symbol"`
	AssetClass         string  `json:"asset_class"`
	Price              float64 `json:"price"`
	RiskPercent        float64 `json:"risk_percent"`
	RiskAmount         float64 `json:"risk_amount"`
	StopLossDistance   float64 `json:"stop_loss_distance"`
	TakeProfitDistance float64 `json:"take_profit_distance"`
	StopLossPrice      float64 `json:"stop_loss_price"`
	TakeProfitPrice    float64 `json:"take_profit_price"`
	Leverage           float64 `json:"leverage"`
	LotSize            float64 `json:"lot_size"`
	Quantity           float64 `json:"quantity"`
	ContractSize       float64 `json:"contract_size"`
	Notional           float64 `json:"notional"`
	MarginRequired     float64 `json:"margin_required"`
	PipOrTickValue     float64 `json:"pip_or_tick_value"`
	AccountCurrency    string  `json:"account_currency"`
}

type ProviderStatus struct {
	Provider  string `json:"provider"`
	Connected bool   `json:"connected"`
	Message   string `json:"message"`
}

type AccountSummary struct {
	Connected     bool    `json:"connected"`
	Currency      string  `json:"currency"`
	Equity        float64 `json:"equity"`
	Free          float64 `json:"free"`
	Used          float64 `json:"used"`
	Total         float64 `json:"total"`
	UnrealizedPnL float64 `json:"unrealized_pnl"`
	MarketType    string  `json:"market_type,omitempty"`
	MarginMode    string  `json:"margin_mode,omitempty"`
	Demo          bool    `json:"demo"`
	Message       string  `json:"message"`
}

type OrderResult struct {
	ID     string  `json:"id"`
	Symbol string  `json:"symbol"`
	Side   string  `json:"side"`
	Amount float64 `json:"amount"`
	Price  float64 `json:"price"`
}

var DefaultInstruments = []Instrument{
	newInstrument("BTC/USDT:USDT", "Bitcoin USDT perpetual", "crypto", "okx", "BTC", "USDT", 2, 0.01, 1, 0.01, 0.01, 10, true),
	newInstrument("ETH/USDT:USDT", "Ethereum USDT perpetual", "crypto", "okx", "ETH", "USDT", 2, 0.01, 1, 0.01, 0.01, 10, true),
	newInstrument("SOL/USDT:USDT", "Solana USDT perpetual", "crypto", "okx", "SOL", "USDT", 3, 0.001, 1, 0.01, 0.01, 10, true),
	newInstrument("XAU/USDT:USDT", "Gold USDT perpetual", "metals", "okx", "XAU", "USDT", 2, 0.01, 1, 0.01, 0.01, 1, true),
	newInstrument("XAG/USDT:USDT", "Silver USDT perpetual", "metals", "okx", "XAG", "USDT", 3, 0.001, 1, 0.01, 0.01, 1, true),
	newInstrument("BTC/USDT", "Bitcoin / Tether", "crypto", "okx", "BTC", "USDT", 2, 0.01, 1, 0.00001, 0.00001, 1, true),
	newInstrument("ETH/USDT", "Ethereum / Tether", "crypto", "okx", "ETH", "USDT", 2, 0.01, 1, 0.0001, 0.0001, 1, true),
	newInstrument("SOL/USDT", "Solana / Tether", "crypto", "okx", "SOL", "USDT", 3, 0.001, 1, 0.001, 0.001, 1, true),
	newInstrument("PAXG/USDT", "PAX Gold / Tether", "metals", "okx", "PAXG", "USDT", 2, 0.01, 1, 0.0001, 0.0001, 1, true),
	newInstrument("PAXG/USD", "PAX Gold / US Dollar", "metals", "okx", "PAXG", "USD", 2, 0.01, 1, 0.0001, 0.0001, 1, true),
	newInstrument("XAUT/USDT", "Tether Gold / Tether", "metals", "okx", "XAUT", "USDT", 2, 0.01, 1, 0.0001, 0.0001, 1, true),
	newInstrument("EUR/USDT", "Euro / Tether", "forex", "okx", "EUR", "USDT", 5, 0.00001, 1, 0.01, 0.01, 1, true),
	newInstrument("EURC/USDT", "Euro Coin / Tether", "forex", "okx", "EURC", "USDT", 5, 0.00001, 1, 0.01, 0.01, 1, true),
	newInstrument("XAUUSD", "Gold / US Dollar preview", "metals", "okx", "XAU", "USD", 2, 0.01, 100, 0.01, 0.01, 20, false),
	newInstrument("USOIL", "US Oil preview", "commodities", "okx", "OIL", "USD", 2, 0.01, 1000, 0.01, 0.01, 10, false),
}

var DefaultWatchlistSymbols = []string{
	"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XAU/USDT:USDT", "XAG/USDT:USDT",
	"PAXG/USDT", "PAXG/USD", "XAUT/USDT", "EUR/USDT", "EURC/USDT", "USOIL",
}

func newInstrument(symbol, displayName, assetClass, provider, base, quote string, digits int, point, contractSize, volumeMin, volumeStep, leverage float64, enabled bool) Instrument {
	return Instrument{Symbol: symbol, DisplayName: displayName, AssetClass: assetClass, Provider: provider, BaseCurrency: base, QuoteCurrency: quote, Digits: digits, Point: point, ContractSize: contractSize, VolumeMin: volumeMin, VolumeStep: volumeStep, DefaultLeverage: leverage, TradeEnabled: enabled}
}

func NormalizeSymbol(symbol string) string {
	return strings.ToUpper(strings.TrimSpace(symbol))
}

func InferAssetClass(symbol string) string {
	normalized := strings.ReplaceAll(NormalizeSymbol(symbol), "/", "")
	base := strings.Split(NormalizeSymbol(symbol), "/")[0]
	if normalized == "XAUUSD" || normalized == "XAGUSD" || base == "XAU" || base == "XAG" || base == "PAXG" || base == "XAUT" {
		return "metals"
	}
	if normalized == "USOIL" || normalized == "UKOIL" || normalized == "WTI" || normalized == "BRENT" {
		return "commodities"
	}
	if strings.Contains(symbol, "/") || strings.HasSuffix(normalized, "USDT") || strings.HasSuffix(normalized, "BTC") || strings.HasSuffix(normalized, "ETH") {
		return "crypto"
	}
	if len(normalized) == 6 {
		return "forex"
	}
	return "commodities"
}

func DefaultInstrument(symbol, provider string) Instrument {
	normalized := NormalizeSymbol(symbol)
	for _, instrument := range DefaultInstruments {
		if NormalizeSymbol(instrument.Symbol) == normalized {
			if provider == "paper" {
				instrument.Provider = "paper"
			}
			return instrument
		}
	}
	assetClass := InferAssetClass(normalized)
	digits := 2
	point := 0.01
	contractSize := 100.0
	leverage := 20.0
	if assetClass == "forex" {
		digits = 5
		point = 0.00001
		contractSize = 100000
		leverage = 30
	}
	base := normalized
	quote := "USD"
	if len(normalized) >= 6 {
		base = normalized[:3]
		quote = normalized[3:6]
	}
	return newInstrument(normalized, normalized, assetClass, provider, base, quote, digits, point, contractSize, 0.01, 0.01, leverage, true)
}

func CalculatePositionSize(instrument Instrument, accountBalance, price, riskPercent, stopLossDistance, takeProfitDistance, leverage float64, accountCurrency string) (PositionSizePreview, error) {
	if accountBalance <= 0 || price <= 0 || riskPercent <= 0 || stopLossDistance <= 0 {
		return PositionSizePreview{}, ErrInvalidSizingInput
	}
	if leverage <= 0 {
		leverage = instrument.DefaultLeverage
	}
	if takeProfitDistance <= 0 {
		takeProfitDistance = stopLossDistance * 2
	}
	riskAmount := accountBalance * (riskPercent / 100)
	rawLots := riskAmount / (stopLossDistance * instrument.ContractSize)
	lotSize := RoundVolume(rawLots, instrument)
	quantity := lotSize * instrument.ContractSize
	notional := quantity * price
	pipOrTickValue := instrument.Point * instrument.ContractSize * lotSize
	if instrument.TickValue != nil {
		pipOrTickValue = *instrument.TickValue
	}
	return PositionSizePreview{
		Symbol: instrument.Symbol, AssetClass: instrument.AssetClass, Price: price, RiskPercent: riskPercent, RiskAmount: riskAmount,
		StopLossDistance: stopLossDistance, TakeProfitDistance: takeProfitDistance, StopLossPrice: price - stopLossDistance,
		TakeProfitPrice: price + takeProfitDistance, Leverage: leverage, LotSize: lotSize, Quantity: quantity,
		ContractSize: instrument.ContractSize, Notional: notional, MarginRequired: notional / leverage, PipOrTickValue: pipOrTickValue,
		AccountCurrency: accountCurrency,
	}, nil
}

var ErrInvalidSizingInput = errString("invalid sizing input")

type errString string

func (e errString) Error() string { return string(e) }

func RoundVolume(volume float64, instrument Instrument) float64 {
	if volume <= instrument.VolumeMin {
		return instrument.VolumeMin
	}
	steps := math.Floor((volume - instrument.VolumeMin) / instrument.VolumeStep)
	return math.Round((instrument.VolumeMin+steps*instrument.VolumeStep)*1e8) / 1e8
}

func SyntheticCandles(symbol string, limit int) []Candle {
	basePrices := map[string]float64{"EURUSD": 1.08, "GBPUSD": 1.27, "USDJPY": 155, "XAUUSD": 2350, "XAGUSD": 31, "USOIL": 78}
	base := basePrices[NormalizeSymbol(symbol)]
	if base == 0 {
		base = 100
	}
	now := time.Now().UTC().Truncate(time.Minute)
	rows := make([]Candle, 0, limit)
	for i := 0; i < limit; i++ {
		wave := math.Sin(float64(i)/7) * base * 0.002
		trend := float64(i-limit) * base * 0.00002
		close := base + wave + trend
		open := close - math.Sin(float64(i)/3)*base*0.0005
		high := math.Max(open, close) + base*0.001
		low := math.Min(open, close) - base*0.001
		ts := now.Add(-time.Duration(limit-i) * time.Minute).Format(time.RFC3339)
		rows = append(rows, Candle{Timestamp: ts, Open: open, High: high, Low: low, Close: close, Volume: 1000 + float64(i)})
	}
	return rows
}
