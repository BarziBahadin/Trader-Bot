package config

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type Settings struct {
	BotMode                 string
	EnableRealTrading       bool
	Exchange                string
	Provider                string
	Symbol                  string
	Timeframe               string
	AssetClass              string
	OKXAPIKey               string
	OKXAPISecret            string
	OKXPassphrase           string
	OKXDemo                 bool
	OKXMarketType           string
	OKXMarginMode           string
	LiveTradingAck          string
	APIAuthToken            string
	CORSOrigins             []string
	TelegramBotToken        string
	TelegramChatID          string
	InitialBalance          float64
	AccountCurrency         string
	DefaultLeverage         float64
	DefaultLotSize          float64
	MaxLeverage             float64
	MaxPositionNotional     float64
	AutoStartWorker         bool
	AutoStartTelegram       bool
	LoadProviderSymbols     bool
	TradingLoopSeconds      float64
	RiskPerTrade            float64
	MaxDailyLoss            float64
	MaxOpenPositions        int
	MaxConsecutiveLosses    int
	LossStreakPauseHours    float64
	StopLossPercent         float64
	TakeProfitPercent       float64
	RSIPeriod               int
	RSIBuyLevel             float64
	RSISellLevel            float64
	FastMA                  int
	SlowMA                  int
	ScalpRSIPeriod          int
	ScalpFastMA             int
	ScalpSlowMA             int
	DatabasePath            string
	StopFile                string
	TelegramConflictBackoff time.Duration
}

func Load() Settings {
	loadDotEnv(".env")
	return Settings{
		BotMode:                 env("BOT_MODE", "paper"),
		EnableRealTrading:       envBool("ENABLE_REAL_TRADING", false),
		Exchange:                env("EXCHANGE", "okx"),
		Provider:                env("PROVIDER", "paper"),
		Symbol:                  env("SYMBOL", "BTC/USDT:USDT"),
		Timeframe:               env("TIMEFRAME", "5m"),
		AssetClass:              env("ASSET_CLASS", "crypto"),
		OKXAPIKey:               env("OKX_API_KEY", ""),
		OKXAPISecret:            env("OKX_API_SECRET", ""),
		OKXPassphrase:           env("OKX_PASSPHRASE", ""),
		OKXDemo:                 envBool("OKX_DEMO", true),
		OKXMarketType:           env("OKX_MARKET_TYPE", "swap"),
		OKXMarginMode:           env("OKX_MARGIN_MODE", "cross"),
		LiveTradingAck:          env("LIVE_TRADING_ACK", ""),
		APIAuthToken:            env("API_AUTH_TOKEN", ""),
		CORSOrigins:             splitCSV(env("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")),
		TelegramBotToken:        env("TELEGRAM_BOT_TOKEN", ""),
		TelegramChatID:          env("TELEGRAM_CHAT_ID", ""),
		InitialBalance:          envFloat("INITIAL_BALANCE", 5),
		AccountCurrency:         env("ACCOUNT_CURRENCY", "USDT"),
		DefaultLeverage:         envFloat("DEFAULT_LEVERAGE", 1),
		DefaultLotSize:          envFloat("DEFAULT_LOT_SIZE", 0.01),
		MaxLeverage:             envFloat("MAX_LEVERAGE", 3),
		MaxPositionNotional:     envFloat("MAX_POSITION_NOTIONAL", 100),
		AutoStartWorker:         envBool("AUTO_START_WORKER", false),
		AutoStartTelegram:       envBool("AUTO_START_TELEGRAM", true),
		LoadProviderSymbols:     envBool("LOAD_PROVIDER_SYMBOLS_ON_STARTUP", false),
		TradingLoopSeconds:      envFloat("TRADING_LOOP_SECONDS", 60),
		RiskPerTrade:            envFloat("RISK_PER_TRADE", 0.02),
		MaxDailyLoss:            envFloat("MAX_DAILY_LOSS", 0.10),
		MaxOpenPositions:        envInt("MAX_OPEN_POSITIONS", 3),
		MaxConsecutiveLosses:    envInt("MAX_CONSECUTIVE_LOSSES", 3),
		LossStreakPauseHours:    envFloat("LOSS_STREAK_PAUSE_HOURS", 2),
		StopLossPercent:         envFloat("STOP_LOSS_PERCENT", 0.01),
		TakeProfitPercent:       envFloat("TAKE_PROFIT_PERCENT", 0.02),
		RSIPeriod:               envInt("RSI_PERIOD", 14),
		RSIBuyLevel:             envFloat("RSI_BUY_LEVEL", 30),
		RSISellLevel:            envFloat("RSI_SELL_LEVEL", 70),
		FastMA:                  envInt("FAST_MA", 20),
		SlowMA:                  envInt("SLOW_MA", 50),
		ScalpRSIPeriod:          envInt("SCALP_RSI_PERIOD", 14),
		ScalpFastMA:             envInt("SCALP_FAST_MA", 9),
		ScalpSlowMA:             envInt("SCALP_SLOW_MA", 21),
		DatabasePath:            databasePath(env("DATABASE_URL", "sqlite:///./trading_bot.db")),
		StopFile:                env("STOP_FILE", "STOP_BOT.txt"),
		TelegramConflictBackoff: time.Duration(envFloat("TELEGRAM_CONFLICT_BACKOFF_SECONDS", 60)) * time.Second,
	}
}

func (s Settings) IsLiveTradingAllowed() bool {
	return strings.EqualFold(s.BotMode, "live") && s.EnableRealTrading
}

func loadDotEnv(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") || !strings.Contains(line, "=") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		key := strings.TrimSpace(parts[0])
		value := strings.Trim(strings.TrimSpace(parts[1]), `"'`)
		if _, exists := os.LookupEnv(key); !exists {
			_ = os.Setenv(key, value)
		}
	}
}

func env(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func envBool(key string, fallback bool) bool {
	value, ok := os.LookupEnv(key)
	if !ok {
		return fallback
	}
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

func envFloat(key string, fallback float64) float64 {
	value, err := strconv.ParseFloat(env(key, ""), 64)
	if err != nil {
		return fallback
	}
	return value
}

func envInt(key string, fallback int) int {
	value, err := strconv.Atoi(env(key, ""))
	if err != nil {
		return fallback
	}
	return value
}

func splitCSV(value string) []string {
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func databasePath(url string) string {
	if strings.HasPrefix(url, "sqlite:///") {
		path := strings.TrimPrefix(url, "sqlite:///")
		if strings.HasPrefix(path, "/") {
			return path
		}
		return filepath.Clean(path)
	}
	return url
}
