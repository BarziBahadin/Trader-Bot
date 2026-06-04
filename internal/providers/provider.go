package providers

import (
	"context"

	"trader/internal/config"
	"trader/internal/market"
	"trader/internal/providers/okx"
	"trader/internal/providers/paper"
)

type Provider interface {
	Name() string
	Status(context.Context) market.ProviderStatus
	Instruments(context.Context) ([]market.Instrument, error)
	Candles(context.Context, string, string, int) ([]market.Candle, error)
	AccountSummary(context.Context) market.AccountSummary
	CreateMarketBuy(context.Context, string, float64) (market.OrderResult, error)
	CreateMarketSell(context.Context, string, float64) (market.OrderResult, error)
	ClosePosition(context.Context, string, float64) (market.OrderResult, error)
}

func Build(name string, settings config.Settings) Provider {
	if name == "okx" {
		return okx.New(settings)
	}
	return paper.New(settings)
}
