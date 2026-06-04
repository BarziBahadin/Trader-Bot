package telegram

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"trader/internal/config"
	"trader/internal/db"
	"trader/internal/market"
	"trader/internal/providers"
	"trader/internal/risk"
)

type updateResponse struct {
	OK     bool `json:"ok"`
	Result []struct {
		UpdateID int64 `json:"update_id"`
		Message  struct {
			Text string `json:"text"`
			From struct {
				ID int64 `json:"id"`
			} `json:"from"`
			Chat struct {
				ID int64 `json:"id"`
			} `json:"chat"`
		} `json:"message"`
	} `json:"result"`
}

func RunPolling(ctx context.Context, settings config.Settings, store *db.Store) {
	if settings.TelegramBotToken == "" {
		return
	}
	offset := int64(0)
	client := &http.Client{Timeout: 30 * time.Second}
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		updates, err := getUpdates(ctx, client, settings.TelegramBotToken, offset)
		if err != nil {
			log.Printf("telegram polling failed: %v", err)
			sleep(ctx, settings.TelegramConflictBackoff)
			continue
		}
		for _, update := range updates.Result {
			if update.UpdateID >= offset {
				offset = update.UpdateID + 1
			}
			if update.Message.Text == "" {
				continue
			}
			chatID := strconv.FormatInt(update.Message.Chat.ID, 10)
			if settings.TelegramChatID != "" && chatID != settings.TelegramChatID {
				_ = sendMessage(ctx, client, settings.TelegramBotToken, chatID, "This bot is locked to another chat.")
				continue
			}
			reply := HandleCommand(ctx, update.Message.Text, store, settings, chatID)
			_ = sendMessage(ctx, client, settings.TelegramBotToken, chatID, reply)
		}
	}
}

func HandleCommand(ctx context.Context, text string, store *db.Store, settings config.Settings, requesterID string) string {
	parts := strings.Fields(strings.TrimSpace(text))
	if len(parts) == 0 {
		return welcome()
	}
	command := normalizeCommand(parts[0])
	switch command {
	case "/start", "/menu", "/help":
		return welcome()
	case "/status":
		state, _ := store.AppState(settings)
		open, _ := store.LatestOpenTrade(state.ActiveSymbol)
		provider := providers.Build(state.ActiveProvider, settings)
		account := provider.AccountSummary(ctx)
		_, isStopped := stopState(settings.StopFile)
		return fmt.Sprintf("Bot status\nMode: %s\nMarket: %s (%s)\nProvider: %s - %s\nTimeframe: %s\nEquity: %.2f %s\nFree: %.2f %s\nUnrealized PnL: %.2f\nRisk per trade: %.2f%%\nStop distance: %.5f\nTake profit distance: %.5f\nLeverage: %.2fx\nEmergency stop: %s\nOpen position: %s\n\nUseful next commands:\n/whyhold\n/calc\n/sell",
			strings.ToUpper(settings.BotMode), state.ActiveSymbol, state.ActiveAssetClass, state.ActiveProvider, provider.Status(ctx).Message, state.Timeframe,
			account.Equity, account.Currency, account.Free, account.Currency, account.UnrealizedPnL, state.RiskPercent, state.StopLossDistance, state.TakeProfitDistance, state.Leverage, onOff(isStopped), yesNo(open != nil))
	case "/account":
		state, _ := store.AppState(settings)
		account := providers.Build(state.ActiveProvider, settings).AccountSummary(ctx)
		return fmt.Sprintf("Account: %s\nEquity: %.2f %s\nFree: %.2f %s\nUsed margin: %.2f %s\nUnrealized PnL: %.2f %s\nMarket: %s\nMargin mode: %s",
			account.Message, account.Equity, account.Currency, account.Free, account.Currency, account.Used, account.Currency, account.UnrealizedPnL, account.Currency, account.MarketType, account.MarginMode)
	case "/livecheck":
		state, _ := store.AppState(settings)
		readiness := risk.LiveReadiness(settings, state.ActiveSymbol)
		lines := []string{"Live futures ready: " + yesNo(readiness["ready"].(bool))}
		for _, raw := range readiness["checks"].([]map[string]any) {
			prefix := "NO "
			if raw["passed"].(bool) {
				prefix = "OK "
			}
			lines = append(lines, prefix+raw["name"].(string))
		}
		return strings.Join(lines, "\n")
	case "/whyhold", "/why":
		state, _ := store.AppState(settings)
		signal, _ := store.LatestSignal(state.ActiveSymbol)
		if signal == nil {
			return "No signal recorded yet for " + state.ActiveSymbol + "."
		}
		return fmt.Sprintf("Latest %s signal: %s\nReason: %s\nPrice: %.5f", state.ActiveSymbol, signal.Signal, signal.Reason, signal.Price)
	case "/symbols", "/watchlist", "/markets":
		state, _ := store.AppState(settings)
		items, _ := store.Watchlist()
		return watchlistMessage(items, state.ActiveSymbol)
	case "/set":
		if len(parts) < 2 {
			return "Tell me the market to use.\nExample: /set BTC/USDT:USDT\nUse /symbols to see your list."
		}
		if _, ok := store.FindInstrument(parts[1]); !ok {
			return "I do not know " + parts[1] + " yet.\nUse /symbols to see available markets."
		}
		state, err := store.ActivateSymbol(settings, parts[1])
		if err != nil {
			return "Could not change market: " + err.Error()
		}
		return fmt.Sprintf("Active market changed to %s\nType: %s\nProvider: %s\n\nNext: /status or /calc", state.ActiveSymbol, state.ActiveAssetClass, state.ActiveProvider)
	case "/timeframe":
		if len(parts) < 2 || !allowedTimeframe(parts[1]) {
			return "Choose a timeframe: /timeframe 5m\nAllowed: 1s, 1m, 5m, 15m, 30m, 1h, 4h, 1d"
		}
		state, _ := store.UpdateState(settings, map[string]any{"timeframe": parts[1]})
		return "Timeframe changed to " + state.Timeframe + "."
	case "/risk":
		state, _ := store.AppState(settings)
		return fmt.Sprintf("Risk settings\nRisk per trade: %.2f%%\nStop distance: %.5f\nTake profit distance: %.5f\nLeverage: %.2fx\n\nChange it like this:\n/setrisk 1 50 100 2", state.RiskPercent, state.StopLossDistance, state.TakeProfitDistance, state.Leverage)
	case "/setrisk":
		if len(parts) < 5 {
			return "Usage: /setrisk RISK% STOP_DISTANCE TAKE_PROFIT_DISTANCE LEVERAGE\nExample: /setrisk 1 50 100 2"
		}
		riskPercent, err1 := strconv.ParseFloat(parts[1], 64)
		stopLoss, err2 := strconv.ParseFloat(parts[2], 64)
		takeProfit, err3 := strconv.ParseFloat(parts[3], 64)
		leverage, err4 := strconv.ParseFloat(parts[4], 64)
		if err1 != nil || err2 != nil || err3 != nil || err4 != nil {
			return "Those numbers did not look right.\nExample: /setrisk 1 50 100 2"
		}
		if riskPercent <= 0 || riskPercent > 5 || stopLoss <= 0 || takeProfit <= 0 || leverage <= 0 {
			return "Risk must be 0-5%, and stop/take-profit/leverage must be positive."
		}
		if leverage > settings.MaxLeverage {
			return fmt.Sprintf("Leverage is capped at %.2fx.", settings.MaxLeverage)
		}
		state, _ := store.UpdateState(settings, map[string]any{"risk_percent": riskPercent, "stop_loss_distance": stopLoss, "take_profit_distance": takeProfit, "leverage": leverage})
		return fmt.Sprintf("Risk updated\nRisk: %.2f%%\nStop distance: %.5f\nTake profit distance: %.5f\nLeverage: %.2fx", state.RiskPercent, state.StopLossDistance, state.TakeProfitDistance, state.Leverage)
	case "/calc", "/size":
		if len(parts) < 4 {
			state, _ := store.AppState(settings)
			return fmt.Sprintf("Preview position size before the bot trades.\nExample: /calc %s %.2f %.5f\nFormat: /calc SYMBOL RISK%% STOP_DISTANCE", state.ActiveSymbol, state.RiskPercent, state.StopLossDistance)
		}
		instrument, ok := store.FindInstrument(parts[1])
		if !ok {
			return "Unknown symbol " + parts[1] + "."
		}
		riskPercent, err1 := strconv.ParseFloat(parts[2], 64)
		stopLoss, err2 := strconv.ParseFloat(parts[3], 64)
		if err1 != nil || err2 != nil || riskPercent <= 0 || riskPercent > 5 || stopLoss <= 0 {
			return "Usage: /calc SYMBOL RISK% SL_DISTANCE. Example: /calc BTC/USDT:USDT 1 50"
		}
		state, _ := store.AppState(settings)
		price := latestPrice(ctx, providers.Build(instrument.Provider, settings), instrument.Symbol, state.Timeframe)
		if price <= 0 {
			price = latestPrice(ctx, providers.Build("paper", settings), instrument.Symbol, state.Timeframe)
		}
		preview, err := market.CalculatePositionSize(instrument, settings.InitialBalance, price, riskPercent, stopLoss, state.TakeProfitDistance, state.Leverage, settings.AccountCurrency)
		if err != nil {
			return "Could not calculate size."
		}
		return fmt.Sprintf("Size preview for %s\nPrice: %.5f\nLot: %.8f\nRisk amount: %.2f %s\nMargin needed: %.2f %s\nLeverage: %.2fx\n\nThis is only a preview. It does not open a trade.", preview.Symbol, preview.Price, preview.LotSize, preview.RiskAmount, preview.AccountCurrency, preview.MarginRequired, preview.AccountCurrency, preview.Leverage)
	case "/stop":
		_ = risk.CreateStopFile(settings.StopFile)
		return "Emergency stop is ON.\nThe bot will not open new trades until you send /resume."
	case "/resume":
		_ = risk.RemoveStopFile(settings.StopFile)
		return "Emergency stop is OFF.\nThe bot may trade again if the strategy and safety checks allow it."
	case "/sell", "/close":
		state, _ := store.AppState(settings)
		trade, _ := store.LatestOpenTrade(state.ActiveSymbol)
		if trade == nil {
			return "There is no open position for the active market."
		}
		confirmation, _ := store.CreateConfirmation("close_position", requesterID, map[string]any{"trade_id": trade.ID, "symbol": trade.Symbol, "quantity": trade.Quantity})
		return fmt.Sprintf("Close position request\nMarket: %s\nQuantity: %.8f\n\nTo close it, send: /confirm %s\nThis code expires in 2 minutes.", trade.Symbol, trade.Quantity, confirmation.Code)
	case "/confirm":
		if len(parts) < 2 {
			return "Send the code from /sell.\nExample: /confirm 123456"
		}
		payload, ok := store.ConsumeConfirmation(parts[1], "close_position", requesterID)
		if !ok {
			return "That confirmation code is invalid, expired, or from another chat.\nSend /sell to create a fresh code."
		}
		id, _ := payload["trade_id"].(float64)
		trades, _ := store.Trades("WHERE id=? AND status='open'", []any{int64(id)}, 1)
		if len(trades) == 0 {
			return "Open trade not found."
		}
		trade := trades[0]
		if err := risk.ValidateLive(settings, trade.Provider, trade.Symbol); err != nil {
			return "Close blocked: " + err.Error()
		}
		provider := providers.Build(trade.Provider, settings)
		_, err := provider.ClosePosition(ctx, trade.Symbol, trade.Quantity)
		if err != nil {
			return "Close failed: " + err.Error()
		}
		price := latestPrice(ctx, provider, trade.Symbol, settings.Timeframe)
		if price <= 0 {
			price = trade.EntryPrice
		}
		_ = store.CloseTrade(trade.ID, price, (price-trade.EntryPrice)*trade.Quantity, "telegram close")
		return "Closed " + trade.Symbol + " position."
	default:
		return "I did not understand that.\nSend /menu to see what I can do."
	}
}

func getUpdates(ctx context.Context, client *http.Client, token string, offset int64) (updateResponse, error) {
	var response updateResponse
	endpoint := fmt.Sprintf("https://api.telegram.org/bot%s/getUpdates?offset=%d&timeout=20", url.PathEscape(token), offset)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	res, err := client.Do(req)
	if err != nil {
		return response, err
	}
	defer res.Body.Close()
	if res.StatusCode == http.StatusConflict {
		return response, fmt.Errorf("409 conflict: another Telegram poller is active")
	}
	if res.StatusCode >= 400 {
		return response, fmt.Errorf("telegram HTTP %d", res.StatusCode)
	}
	return response, json.NewDecoder(res.Body).Decode(&response)
}

func sendMessage(ctx context.Context, client *http.Client, token, chatID, text string) error {
	body, _ := json.Marshal(map[string]string{"chat_id": chatID, "text": text})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", url.PathEscape(token)), bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	res, err := client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	return nil
}

func latestPrice(ctx context.Context, provider providers.Provider, symbol, timeframe string) float64 {
	rows, err := provider.Candles(ctx, symbol, timeframe, 1)
	if err != nil || len(rows) == 0 {
		return 0
	}
	return rows[len(rows)-1].Close
}

func welcome() string {
	return "Trader bot menu\n\nWhat you can do:\n/status - see what the bot is doing\n/account - see equity and free balance\n/symbols - see markets you can pick\n/set BTC/USDT:USDT - change market\n/risk - see risk settings\n/setrisk 1 50 100 2 - change risk settings\n/calc BTC/USDT:USDT 1 50 - preview position size\n/whyhold - explain the last HOLD\n/stop - pause trading\n/resume - allow trading again\n/sell - close an open position with confirmation\n\nGood first step: send /status"
}

func watchlistMessage(items []db.WatchlistItem, active string) string {
	if len(items) == 0 {
		return "Your watchlist is empty."
	}
	groups := map[string][]string{}
	for _, item := range items {
		marker := ""
		if item.Symbol == active {
			marker = " selected"
		}
		groups[item.AssetClass] = append(groups[item.AssetClass], fmt.Sprintf("- %s (%s)%s", item.Symbol, item.Provider, marker))
	}
	lines := []string{"Markets"}
	for _, group := range []string{"crypto", "forex", "metals", "commodities"} {
		if len(groups[group]) == 0 {
			continue
		}
		lines = append(lines, "", strings.Title(group))
		lines = append(lines, groups[group]...)
	}
	lines = append(lines, "", "Change market with: /set SYMBOL")
	return strings.Join(lines, "\n")
}

func normalizeCommand(raw string) string {
	command := strings.ToLower(raw)
	if strings.HasPrefix(command, "/") {
		return command
	}
	aliases := map[string]string{"start": "/start", "menu": "/menu", "help": "/help", "status": "/status", "account": "/account", "symbols": "/symbols", "markets": "/markets", "risk": "/risk", "stop": "/stop", "resume": "/resume", "sell": "/sell", "close": "/close", "why": "/whyhold"}
	if value, ok := aliases[command]; ok {
		return value
	}
	return command
}

func allowedTimeframe(value string) bool {
	switch value {
	case "1s", "1m", "5m", "15m", "30m", "1h", "4h", "1d":
		return true
	default:
		return false
	}
}

func stopState(path string) (error, bool) {
	_, err := http.Dir(".").Open(path)
	return err, err == nil
}

func yesNo(value bool) string {
	if value {
		return "YES"
	}
	return "NO"
}

func onOff(value bool) string {
	if value {
		return "ON"
	}
	return "OFF"
}

func sleep(ctx context.Context, duration time.Duration) {
	timer := time.NewTimer(duration)
	defer timer.Stop()
	select {
	case <-ctx.Done():
	case <-timer.C:
	}
}
