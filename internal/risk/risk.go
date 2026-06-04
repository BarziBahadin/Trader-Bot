package risk

import (
	"errors"
	"fmt"
	"os"
	"strings"

	"trader/internal/config"
	"trader/internal/db"
)

type Decision struct {
	Allowed    bool
	Reason     string
	Quantity   float64
	StopLoss   float64
	TakeProfit float64
}

func ValidateLive(settings config.Settings, provider, symbol string) error {
	if provider == "paper" {
		return nil
	}
	if settings.BotMode != "live" {
		return fmt.Errorf("real provider %s requires BOT_MODE=live", provider)
	}
	if !settings.EnableRealTrading {
		return errors.New("live mode requires ENABLE_REAL_TRADING=true")
	}
	if settings.APIAuthToken == "" {
		return errors.New("live futures requires API_AUTH_TOKEN")
	}
	if settings.LiveTradingAck != "I_UNDERSTAND_LIVE_FUTURES_RISK" {
		return errors.New("live futures requires LIVE_TRADING_ACK=I_UNDERSTAND_LIVE_FUTURES_RISK")
	}
	if provider != "okx" {
		return errors.New("live futures requires PROVIDER=okx")
	}
	if settings.OKXDemo {
		return errors.New("live futures requires OKX_DEMO=false")
	}
	if settings.OKXMarketType != "swap" && settings.OKXMarketType != "future" && settings.OKXMarketType != "futures" {
		return errors.New("live futures requires OKX_MARKET_TYPE=swap")
	}
	if settings.OKXAPIKey == "" || settings.OKXAPISecret == "" || settings.OKXPassphrase == "" {
		return errors.New("live futures requires OKX_API_KEY, OKX_API_SECRET, and OKX_PASSPHRASE")
	}
	if settings.DefaultLeverage > settings.MaxLeverage {
		return fmt.Errorf("DEFAULT_LEVERAGE cannot exceed MAX_LEVERAGE=%.2f", settings.MaxLeverage)
	}
	if !contains(symbol, ":USDT") {
		return errors.New("live futures requires an OKX swap symbol such as BTC/USDT:USDT")
	}
	return nil
}

func ValidateEntry(store *db.Store, settings config.Settings, provider, symbol string, price, balance float64) Decision {
	if _, err := os.Stat(settings.StopFile); err == nil {
		return reject(store, "emergency_stop", "STOP_BOT.txt exists")
	}
	if trade, _ := store.LatestOpenTrade(symbol); trade != nil {
		return reject(store, "open_position_exists", "open "+symbol+" position already exists")
	}
	if count, _ := store.OpenPositionCount(); count >= settings.MaxOpenPositions {
		return reject(store, "max_open_positions", fmt.Sprintf("max open positions reached: %d", settings.MaxOpenPositions))
	}
	if provider != "paper" || settings.BotMode == "live" {
		if err := ValidateLive(settings, provider, symbol); err != nil {
			return reject(store, "real_trading_blocked", err.Error())
		}
	}
	if settings.BotMode == "backtest" {
		return reject(store, "backtest_execution_blocked", "backtest mode cannot place live orders")
	}
	if price <= 0 {
		return reject(store, "invalid_price", "order price must be positive")
	}
	if balance <= 0 {
		return reject(store, "minimum_balance", "balance must be positive")
	}
	stopLoss := price * (1 - settings.StopLossPercent)
	takeProfit := price * (1 + settings.TakeProfitPercent)
	unitRisk := price - stopLoss
	if unitRisk <= 0 {
		return reject(store, "missing_stop_loss", "stop-loss is required")
	}
	quantity := (balance * settings.RiskPerTrade) / unitRisk
	notional := quantity * price
	if notional > balance {
		quantity = balance / price
		notional = quantity * price
	}
	if provider != "paper" && notional > settings.MaxPositionNotional {
		quantity = settings.MaxPositionNotional / price
	}
	if quantity <= 0 {
		return reject(store, "minimum_balance", "balance too low for order")
	}
	return Decision{Allowed: true, Reason: "allowed", Quantity: quantity, StopLoss: stopLoss, TakeProfit: takeProfit}
}

func LiveReadiness(settings config.Settings, symbol string) map[string]any {
	checks := []map[string]any{
		check("BOT_MODE=live", settings.BotMode == "live"),
		check("ENABLE_REAL_TRADING=true", settings.EnableRealTrading),
		check("LIVE_TRADING_ACK set", settings.LiveTradingAck == "I_UNDERSTAND_LIVE_FUTURES_RISK"),
		check("PROVIDER=okx", settings.Provider == "okx"),
		check("OKX_DEMO=false", !settings.OKXDemo),
		check("OKX swap market", settings.OKXMarketType == "swap" || settings.OKXMarketType == "future" || settings.OKXMarketType == "futures"),
		check("OKX credentials", settings.OKXAPIKey != "" && settings.OKXAPISecret != "" && settings.OKXPassphrase != ""),
		check("API auth token", settings.APIAuthToken != ""),
		check("leverage cap", settings.DefaultLeverage <= settings.MaxLeverage),
		check("swap symbol", contains(symbol, ":USDT")),
	}
	ready := true
	for _, item := range checks {
		if !item["passed"].(bool) {
			ready = false
		}
	}
	if _, err := os.Stat(settings.StopFile); err == nil {
		ready = false
		checks = append(checks, check("emergency stop off", false))
	}
	return map[string]any{"ready": ready, "checks": checks, "max_position_notional": settings.MaxPositionNotional, "max_leverage": settings.MaxLeverage}
}

func CreateStopFile(path string) error {
	return os.WriteFile(path, []byte("Emergency stop enabled.\n"), 0o644)
}

func RemoveStopFile(path string) error {
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

func reject(store *db.Store, eventType, message string) Decision {
	store.InsertRiskEvent(eventType, message)
	return Decision{Allowed: false, Reason: message}
}

func check(name string, passed bool) map[string]any {
	return map[string]any{"name": name, "passed": passed}
}

func contains(value, part string) bool {
	return strings.Contains(value, part)
}
