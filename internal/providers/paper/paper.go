package paper

import (
	"context"
	"fmt"

	"trader/internal/config"
	"trader/internal/market"
)

type Provider struct {
	settings config.Settings
}

func New(settings config.Settings) *Provider {
	return &Provider{settings: settings}
}

func (p *Provider) Name() string { return "paper" }

func (p *Provider) Status(context.Context) market.ProviderStatus {
	return market.ProviderStatus{Provider: "paper", Connected: true, Message: "Paper provider active"}
}

func (p *Provider) Instruments(context.Context) ([]market.Instrument, error) {
	instruments := make([]market.Instrument, 0, len(market.DefaultInstruments))
	for _, instrument := range market.DefaultInstruments {
		instrument.Provider = "paper"
		instruments = append(instruments, instrument)
	}
	return instruments, nil
}

func (p *Provider) Candles(ctx context.Context, symbol, timeframe string, limit int) ([]market.Candle, error) {
	_ = ctx
	_ = timeframe
	if limit <= 0 {
		limit = 120
	}
	return market.SyntheticCandles(symbol, limit), nil
}

func (p *Provider) AccountSummary(context.Context) market.AccountSummary {
	return market.AccountSummary{Connected: true, Currency: p.settings.AccountCurrency, Equity: p.settings.InitialBalance, Free: p.settings.InitialBalance, Total: p.settings.InitialBalance, Message: "Paper account active"}
}

func (p *Provider) CreateMarketBuy(ctx context.Context, symbol string, amount float64) (market.OrderResult, error) {
	return p.order(ctx, symbol, "buy", amount)
}

func (p *Provider) CreateMarketSell(ctx context.Context, symbol string, amount float64) (market.OrderResult, error) {
	return p.order(ctx, symbol, "sell", amount)
}

func (p *Provider) ClosePosition(ctx context.Context, symbol string, amount float64) (market.OrderResult, error) {
	return p.order(ctx, symbol, "sell", amount)
}

func (p *Provider) order(ctx context.Context, symbol, side string, amount float64) (market.OrderResult, error) {
	candles, _ := p.Candles(ctx, symbol, p.settings.Timeframe, 1)
	price := 0.0
	if len(candles) > 0 {
		price = candles[len(candles)-1].Close
	}
	return market.OrderResult{ID: fmt.Sprintf("paper-%s", side), Symbol: symbol, Side: side, Amount: amount, Price: price}, nil
}
