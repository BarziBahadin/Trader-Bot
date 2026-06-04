package okx

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"trader/internal/config"
	"trader/internal/market"
)

const baseURL = "https://www.okx.com"

type Provider struct {
	settings config.Settings
	client   *http.Client
}

func New(settings config.Settings) *Provider {
	return &Provider{settings: settings, client: &http.Client{Timeout: 15 * time.Second}}
}

func (p *Provider) Name() string { return "okx" }

func (p *Provider) Status(context.Context) market.ProviderStatus {
	if p.hasPrivateCredentials() {
		mode := "live"
		if p.settings.OKXDemo {
			mode = "demo"
		}
		return market.ProviderStatus{Provider: "okx", Connected: true, Message: fmt.Sprintf("OKX %s %s API configured", mode, p.settings.OKXMarketType)}
	}
	return market.ProviderStatus{Provider: "okx", Connected: true, Message: "OKX public market data active; trading keys missing"}
}

func (p *Provider) Instruments(ctx context.Context) ([]market.Instrument, error) {
	instruments := make([]market.Instrument, 0, len(market.DefaultInstruments))
	for _, instrument := range market.DefaultInstruments {
		if instrument.Provider == "okx" {
			instruments = append(instruments, instrument)
		}
	}
	instType := strings.ToUpper(okxInstType(p.settings.OKXMarketType))
	var response struct {
		Code string `json:"code"`
		Msg  string `json:"msg"`
		Data []struct {
			InstID string `json:"instId"`
			Base   string `json:"baseCcy"`
			Quote  string `json:"quoteCcy"`
			CtVal  string `json:"ctVal"`
			MinSz  string `json:"minSz"`
			LotSz  string `json:"lotSz"`
			TickSz string `json:"tickSz"`
			State  string `json:"state"`
		} `json:"data"`
	}
	if err := p.public(ctx, "/api/v5/public/instruments?instType="+url.QueryEscape(instType), &response); err != nil {
		return instruments, nil
	}
	existing := map[string]bool{}
	for _, instrument := range instruments {
		existing[instrument.Symbol] = true
	}
	for _, row := range response.Data {
		symbol := symbolFromInstID(row.InstID, instType)
		if symbol == "" || existing[symbol] || row.State == "suspend" {
			continue
		}
		base, quote := row.Base, row.Quote
		if base == "" || quote == "" {
			parts := strings.Split(row.InstID, "-")
			if len(parts) >= 2 {
				base, quote = parts[0], parts[1]
			}
		}
		point := parseFloat(row.TickSz, 0.01)
		instruments = append(instruments, market.Instrument{
			Symbol: symbol, DisplayName: row.InstID, AssetClass: market.InferAssetClass(symbol), Provider: "okx",
			BaseCurrency: base, QuoteCurrency: quote, Digits: digitsFromTick(point), Point: point,
			ContractSize: parseFloat(row.CtVal, 1), VolumeMin: parseFloat(row.MinSz, 0.01), VolumeStep: parseFloat(row.LotSz, 0.01),
			DefaultLeverage: 1, TradeEnabled: true,
		})
	}
	return instruments, nil
}

func (p *Provider) Candles(ctx context.Context, symbol, timeframe string, limit int) ([]market.Candle, error) {
	if limit <= 0 {
		limit = 120
	}
	if timeframe == "1s" {
		timeframe = "1m"
	}
	instID := instIDFromSymbol(symbol)
	if instID == "" || !strings.Contains(symbol, "/") {
		return market.SyntheticCandles(symbol, limit), nil
	}
	var response struct {
		Code string     `json:"code"`
		Msg  string     `json:"msg"`
		Data [][]string `json:"data"`
	}
	path := fmt.Sprintf("/api/v5/market/candles?instId=%s&bar=%s&limit=%d", url.QueryEscape(instID), url.QueryEscape(okxBar(timeframe)), limit)
	if err := p.public(ctx, path, &response); err != nil {
		return nil, err
	}
	if response.Code != "" && response.Code != "0" {
		return nil, errors.New(response.Msg)
	}
	rows := make([]market.Candle, 0, len(response.Data))
	for i := len(response.Data) - 1; i >= 0; i-- {
		row := response.Data[i]
		if len(row) < 6 {
			continue
		}
		ms, _ := strconv.ParseInt(row[0], 10, 64)
		rows = append(rows, market.Candle{
			Timestamp: time.UnixMilli(ms).UTC().Format(time.RFC3339),
			Open:      parseFloat(row[1], 0),
			High:      parseFloat(row[2], 0),
			Low:       parseFloat(row[3], 0),
			Close:     parseFloat(row[4], 0),
			Volume:    parseFloat(row[5], 0),
		})
	}
	return rows, nil
}

func (p *Provider) AccountSummary(ctx context.Context) market.AccountSummary {
	summary := market.AccountSummary{Connected: false, Currency: p.settings.AccountCurrency, MarketType: p.settings.OKXMarketType, MarginMode: p.settings.OKXMarginMode, Demo: p.settings.OKXDemo}
	if !p.hasPrivateCredentials() {
		summary.Message = "OKX trading keys are missing"
		return summary
	}
	var response struct {
		Code string `json:"code"`
		Msg  string `json:"msg"`
		Data []struct {
			Details []struct {
				Ccy      string `json:"ccy"`
				Eq       string `json:"eq"`
				AvailBal string `json:"availBal"`
				Frozen   string `json:"frozenBal"`
				Upl      string `json:"upl"`
			} `json:"details"`
		} `json:"data"`
	}
	if err := p.private(ctx, http.MethodGet, "/api/v5/account/balance", nil, &response); err != nil {
		summary.Message = "OKX account error: " + err.Error()
		return summary
	}
	if response.Code != "" && response.Code != "0" {
		summary.Message = "OKX account error: " + response.Msg
		return summary
	}
	currency := p.settings.AccountCurrency
	if currency == "" {
		currency = "USDT"
	}
	for _, account := range response.Data {
		for _, detail := range account.Details {
			if detail.Ccy == currency || currency == "" {
				summary.Connected = true
				summary.Currency = detail.Ccy
				summary.Equity = parseFloat(detail.Eq, 0)
				summary.Free = parseFloat(detail.AvailBal, 0)
				summary.Used = parseFloat(detail.Frozen, 0)
				summary.Total = summary.Equity
				summary.UnrealizedPnL = parseFloat(detail.Upl, 0)
				if p.settings.OKXDemo {
					summary.Message = "OKX demo account connected"
				} else {
					summary.Message = "OKX live account connected"
				}
				return summary
			}
		}
	}
	summary.Message = "OKX account loaded, currency balance not found"
	return summary
}

func (p *Provider) CreateMarketBuy(ctx context.Context, symbol string, amount float64) (market.OrderResult, error) {
	if err := p.setLeverage(ctx, symbol); err != nil {
		return market.OrderResult{}, err
	}
	return p.createOrder(ctx, symbol, "buy", amount, false)
}

func (p *Provider) CreateMarketSell(ctx context.Context, symbol string, amount float64) (market.OrderResult, error) {
	return p.ClosePosition(ctx, symbol, amount)
}

func (p *Provider) ClosePosition(ctx context.Context, symbol string, amount float64) (market.OrderResult, error) {
	return p.createOrder(ctx, symbol, "sell", amount, true)
}

func (p *Provider) createOrder(ctx context.Context, symbol, side string, amount float64, reduceOnly bool) (market.OrderResult, error) {
	if !p.hasPrivateCredentials() {
		return market.OrderResult{}, errors.New("OKX trading keys are missing")
	}
	body := map[string]any{
		"instId":  instIDFromSymbol(symbol),
		"tdMode":  p.settings.OKXMarginMode,
		"side":    side,
		"ordType": "market",
		"sz":      fmt.Sprintf("%.8f", amount),
	}
	if reduceOnly {
		body["reduceOnly"] = "true"
	}
	var response struct {
		Code string `json:"code"`
		Msg  string `json:"msg"`
		Data []struct {
			OrdID string `json:"ordId"`
			SCode string `json:"sCode"`
			SMsg  string `json:"sMsg"`
		} `json:"data"`
	}
	if err := p.private(ctx, http.MethodPost, "/api/v5/trade/order", body, &response); err != nil {
		return market.OrderResult{}, err
	}
	if response.Code != "0" {
		return market.OrderResult{}, errors.New(response.Msg)
	}
	orderID := ""
	if len(response.Data) > 0 {
		if response.Data[0].SCode != "" && response.Data[0].SCode != "0" {
			return market.OrderResult{}, errors.New(response.Data[0].SMsg)
		}
		orderID = response.Data[0].OrdID
	}
	price := 0.0
	candles, _ := p.Candles(ctx, symbol, p.settings.Timeframe, 1)
	if len(candles) > 0 {
		price = candles[len(candles)-1].Close
	}
	return market.OrderResult{ID: orderID, Symbol: symbol, Side: side, Amount: amount, Price: price}, nil
}

func (p *Provider) setLeverage(ctx context.Context, symbol string) error {
	if p.settings.OKXMarketType != "swap" && p.settings.OKXMarketType != "future" && p.settings.OKXMarketType != "futures" {
		return nil
	}
	body := map[string]any{"instId": instIDFromSymbol(symbol), "lever": fmt.Sprintf("%.0f", p.settings.DefaultLeverage), "mgnMode": p.settings.OKXMarginMode}
	var response struct {
		Code string `json:"code"`
		Msg  string `json:"msg"`
	}
	if err := p.private(ctx, http.MethodPost, "/api/v5/account/set-leverage", body, &response); err != nil {
		return err
	}
	if response.Code != "" && response.Code != "0" {
		return errors.New(response.Msg)
	}
	return nil
}

func (p *Provider) public(ctx context.Context, path string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL+path, nil)
	if err != nil {
		return err
	}
	res, err := p.client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode >= 400 {
		return fmt.Errorf("OKX HTTP %d", res.StatusCode)
	}
	return json.NewDecoder(res.Body).Decode(out)
}

func (p *Provider) private(ctx context.Context, method, path string, body any, out any) error {
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			return err
		}
	}
	req, err := http.NewRequestWithContext(ctx, method, baseURL+path, bytes.NewReader(payload))
	if err != nil {
		return err
	}
	ts := time.Now().UTC().Format("2006-01-02T15:04:05.000Z")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("OK-ACCESS-KEY", p.settings.OKXAPIKey)
	req.Header.Set("OK-ACCESS-PASSPHRASE", p.settings.OKXPassphrase)
	req.Header.Set("OK-ACCESS-TIMESTAMP", ts)
	req.Header.Set("OK-ACCESS-SIGN", sign(ts, method, path, string(payload), p.settings.OKXAPISecret))
	if p.settings.OKXDemo {
		req.Header.Set("x-simulated-trading", "1")
	}
	res, err := p.client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode >= 400 {
		data, _ := io.ReadAll(io.LimitReader(res.Body, 512))
		return fmt.Errorf("OKX HTTP %d: %s", res.StatusCode, strings.TrimSpace(string(data)))
	}
	return json.NewDecoder(res.Body).Decode(out)
}

func (p *Provider) hasPrivateCredentials() bool {
	return p.settings.OKXAPIKey != "" && p.settings.OKXAPISecret != "" && p.settings.OKXPassphrase != ""
}

func sign(timestamp, method, path, body, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(timestamp + strings.ToUpper(method) + path + body))
	return base64.StdEncoding.EncodeToString(mac.Sum(nil))
}

func instIDFromSymbol(symbol string) string {
	symbol = strings.TrimSpace(symbol)
	if !strings.Contains(symbol, "/") {
		return strings.ReplaceAll(symbol, "/", "-")
	}
	parts := strings.Split(symbol, "/")
	base := parts[0]
	quote := parts[1]
	if strings.Contains(quote, ":") {
		quote = strings.Split(quote, ":")[0]
		return base + "-" + quote + "-SWAP"
	}
	return base + "-" + quote
}

func symbolFromInstID(instID, instType string) string {
	parts := strings.Split(instID, "-")
	if len(parts) < 2 {
		return ""
	}
	if instType == "SWAP" || strings.HasSuffix(instID, "-SWAP") {
		return parts[0] + "/" + parts[1] + ":" + parts[1]
	}
	return parts[0] + "/" + parts[1]
}

func okxInstType(marketType string) string {
	switch strings.ToLower(marketType) {
	case "spot":
		return "SPOT"
	case "future", "futures":
		return "FUTURES"
	default:
		return "SWAP"
	}
}

func okxBar(timeframe string) string {
	switch timeframe {
	case "1m", "3m", "5m", "15m", "30m":
		return timeframe
	case "1h":
		return "1H"
	case "4h":
		return "4H"
	case "1d":
		return "1D"
	default:
		return "15m"
	}
}

func parseFloat(value string, fallback float64) float64 {
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return fallback
	}
	return parsed
}

func digitsFromTick(point float64) int {
	text := strconv.FormatFloat(point, 'f', -1, 64)
	if !strings.Contains(text, ".") {
		return 0
	}
	return len(strings.TrimRight(strings.Split(text, ".")[1], "0"))
}
