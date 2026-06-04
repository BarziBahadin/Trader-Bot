package worker

import (
	"context"
	"log"
	"os"
	"time"

	"trader/internal/config"
	"trader/internal/db"
	"trader/internal/market"
	"trader/internal/providers"
	"trader/internal/risk"
	"trader/internal/strategy"
)

func Run(ctx context.Context, settings config.Settings, store *db.Store) {
	interval := time.Duration(settings.TradingLoopSeconds * float64(time.Second))
	if interval <= 0 {
		interval = time.Minute
	}
	log.Printf("trading worker started in %s mode", settings.BotMode)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := os.Stat(settings.StopFile); err == nil {
			log.Printf("emergency stop file exists; trading paused")
		} else if err := runOnce(ctx, settings, store); err != nil {
			log.Printf("trading worker iteration failed: %v", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func runOnce(ctx context.Context, settings config.Settings, store *db.Store) error {
	state, err := store.AppState(settings)
	if err != nil {
		return err
	}
	settings.Symbol = state.ActiveSymbol
	settings.Provider = state.ActiveProvider
	settings.AssetClass = state.ActiveAssetClass
	settings.Timeframe = state.Timeframe
	providerName := state.ActiveProvider
	if settings.BotMode == "paper" {
		providerName = "paper"
	}
	if settings.BotMode == "live" {
		if err := risk.ValidateLive(settings, state.ActiveProvider, state.ActiveSymbol); err != nil {
			log.Printf("live trading paused for %s: %v", state.ActiveSymbol, err)
			return nil
		}
	}
	provider := providers.Build(providerName, settings)
	return runDecision(ctx, settings, store, provider, state)
}

func runDecision(ctx context.Context, settings config.Settings, store *db.Store, provider providers.Provider, state db.AppState) error {
	frames := map[string][]market.Candle{}
	for _, tf := range []string{"5m", "15m", "1h", "4h"} {
		rows, err := provider.Candles(ctx, state.ActiveSymbol, tf, 240)
		if err != nil {
			return err
		}
		frames[tf] = rows
	}
	open, _ := store.LatestOpenTrade(state.ActiveSymbol)
	var entry *float64
	if open != nil {
		entry = &open.EntryPrice
	}
	decision := strategy.New(settings).Evaluate(frames, open != nil, entry)
	_ = store.InsertSignal(db.Signal{Symbol: state.ActiveSymbol, Provider: state.ActiveProvider, AssetClass: state.ActiveAssetClass, Timeframe: state.Timeframe, Signal: decision.Signal, RSI: decision.RSI, FastMA: decision.FastMA, SlowMA: decision.SlowMA, Price: decision.Price, Reason: decision.Reason})
	if decision.Signal == "buy" {
		return buy(ctx, settings, store, provider, state, decision)
	}
	if decision.Signal == "sell" && open != nil {
		return sell(ctx, store, provider, open, decision.Price, decision.Reason)
	}
	return nil
}

func buy(ctx context.Context, settings config.Settings, store *db.Store, provider providers.Provider, state db.AppState, decision strategy.Decision) error {
	account := provider.AccountSummary(ctx)
	balance := account.Free
	if balance <= 0 {
		balance = account.Equity
	}
	riskDecision := risk.ValidateEntry(store, settings, state.ActiveProvider, state.ActiveSymbol, decision.Price, balance)
	if !riskDecision.Allowed {
		return nil
	}
	order, err := provider.CreateMarketBuy(ctx, state.ActiveSymbol, riskDecision.Quantity)
	if err != nil {
		store.InsertRiskEvent("order_failed", err.Error())
		return nil
	}
	leverage, margin, contract := settings.DefaultLeverage, 0.0, 1.0
	if leverage > 0 {
		margin = (riskDecision.Quantity * order.Price) / leverage
	}
	return store.InsertOpenTrade(db.Trade{
		Symbol: state.ActiveSymbol, Provider: state.ActiveProvider, AssetClass: state.ActiveAssetClass, Side: "buy",
		EntryPrice: order.Price, Quantity: riskDecision.Quantity, LotSize: &riskDecision.Quantity, Leverage: &leverage,
		MarginRequired: &margin, ContractSize: &contract, StopLoss: &riskDecision.StopLoss, TakeProfit: &riskDecision.TakeProfit,
		PnL: 0, Status: "open", Mode: settings.BotMode, Reason: decision.Reason,
	})
}

func sell(ctx context.Context, store *db.Store, provider providers.Provider, trade *db.Trade, price float64, reason string) error {
	if _, err := provider.CreateMarketSell(ctx, trade.Symbol, trade.Quantity); err != nil {
		store.InsertRiskEvent("close_failed", err.Error())
		return nil
	}
	return store.CloseTrade(trade.ID, price, (price-trade.EntryPrice)*trade.Quantity, reason)
}
