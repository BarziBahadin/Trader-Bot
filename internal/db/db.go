package db

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"

	"trader/internal/config"
	"trader/internal/market"
)

type Store struct {
	db *sql.DB
}

type AppState struct {
	ActiveSymbol       string    `json:"active_symbol"`
	ActiveProvider     string    `json:"active_provider"`
	ActiveAssetClass   string    `json:"active_asset_class"`
	Timeframe          string    `json:"timeframe"`
	RiskPercent        float64   `json:"risk_percent"`
	StopLossDistance   float64   `json:"stop_loss_distance"`
	TakeProfitDistance float64   `json:"take_profit_distance"`
	Leverage           float64   `json:"leverage"`
	LotSize            float64   `json:"lot_size"`
	UpdatedAt          time.Time `json:"updated_at"`
}

type WatchlistItem struct {
	Symbol     string `json:"symbol"`
	Provider   string `json:"provider"`
	AssetClass string `json:"asset_class"`
}

type Trade struct {
	ID             int64      `json:"id"`
	Symbol         string     `json:"symbol"`
	Provider       string     `json:"provider"`
	AssetClass     string     `json:"asset_class"`
	Side           string     `json:"side"`
	EntryPrice     float64    `json:"entry_price"`
	ExitPrice      *float64   `json:"exit_price"`
	Quantity       float64    `json:"quantity"`
	LotSize        *float64   `json:"lot_size"`
	Leverage       *float64   `json:"leverage"`
	MarginRequired *float64   `json:"margin_required"`
	ContractSize   *float64   `json:"contract_size"`
	StopLoss       *float64   `json:"stop_loss"`
	TakeProfit     *float64   `json:"take_profit"`
	PnL            float64    `json:"pnl"`
	Status         string     `json:"status"`
	Mode           string     `json:"mode"`
	OpenedAt       time.Time  `json:"opened_at"`
	ClosedAt       *time.Time `json:"closed_at"`
	Reason         string     `json:"reason"`
}

type Signal struct {
	ID         int64     `json:"id"`
	Symbol     string    `json:"symbol"`
	Provider   string    `json:"provider"`
	AssetClass string    `json:"asset_class"`
	Timeframe  string    `json:"timeframe"`
	Signal     string    `json:"signal"`
	RSI        *float64  `json:"rsi"`
	FastMA     *float64  `json:"fast_ma"`
	SlowMA     *float64  `json:"slow_ma"`
	Price      float64   `json:"price"`
	Reason     string    `json:"reason"`
	CreatedAt  time.Time `json:"created_at"`
}

type RiskEvent struct {
	ID        int64     `json:"id"`
	EventType string    `json:"event_type"`
	Message   string    `json:"message"`
	CreatedAt time.Time `json:"created_at"`
}

type Confirmation struct {
	Code      string
	Action    string
	Requester string
	Payload   map[string]any
	ExpiresAt time.Time
}

func Open(path string) (*Store, error) {
	if dir := filepath.Dir(path); dir != "." && dir != "" {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, err
		}
	}
	handle, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	handle.SetMaxOpenConns(1)
	return &Store{db: handle}, nil
}

func (s *Store) Close() error { return s.db.Close() }

func (s *Store) Migrate() error {
	statements := []string{
		`CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol VARCHAR(32), provider VARCHAR(32) DEFAULT 'paper', asset_class VARCHAR(32) DEFAULT 'crypto', side VARCHAR(8), entry_price FLOAT, exit_price FLOAT, quantity FLOAT, lot_size FLOAT, leverage FLOAT, margin_required FLOAT, contract_size FLOAT, stop_loss FLOAT, take_profit FLOAT, pnl FLOAT DEFAULT 0, status VARCHAR(16), mode VARCHAR(16), opened_at DATETIME, closed_at DATETIME, reason TEXT DEFAULT '')`,
		`CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, symbol VARCHAR(32), provider VARCHAR(32) DEFAULT 'paper', asset_class VARCHAR(32) DEFAULT 'crypto', timeframe VARCHAR(16), signal VARCHAR(16), rsi FLOAT, fast_ma FLOAT, slow_ma FLOAT, price FLOAT, reason TEXT DEFAULT '', created_at DATETIME)`,
		`CREATE TABLE IF NOT EXISTS risk_events (id INTEGER PRIMARY KEY, event_type VARCHAR(64), message TEXT, created_at DATETIME)`,
		`CREATE TABLE IF NOT EXISTS app_state (id INTEGER PRIMARY KEY, active_symbol VARCHAR(32), active_provider VARCHAR(32), active_asset_class VARCHAR(32), timeframe VARCHAR(16), risk_percent FLOAT, stop_loss_distance FLOAT, take_profit_distance FLOAT, leverage FLOAT, lot_size FLOAT, updated_at DATETIME)`,
		`CREATE TABLE IF NOT EXISTS instruments (id INTEGER PRIMARY KEY, symbol VARCHAR(32), display_name VARCHAR(128), asset_class VARCHAR(32), provider VARCHAR(32), base_currency VARCHAR(16), quote_currency VARCHAR(16), digits INTEGER, point FLOAT, contract_size FLOAT, volume_min FLOAT, volume_step FLOAT, default_leverage FLOAT, tick_value FLOAT, spread FLOAT, trade_enabled BOOLEAN)`,
		`CREATE TABLE IF NOT EXISTS watchlist_items (id INTEGER PRIMARY KEY, symbol VARCHAR(32), provider VARCHAR(32), asset_class VARCHAR(32), created_at DATETIME)`,
		`CREATE TABLE IF NOT EXISTS confirmation_codes (id INTEGER PRIMARY KEY, code VARCHAR(16), code_hash VARCHAR(128), action VARCHAR(64), requester_id VARCHAR(64), payload TEXT DEFAULT '{}', expires_at DATETIME, used_at DATETIME, created_at DATETIME)`,
		`CREATE TABLE IF NOT EXISTS paper_accounts (id INTEGER PRIMARY KEY, cash FLOAT DEFAULT 10000, updated_at DATETIME)`,
	}
	for _, statement := range statements {
		if _, err := s.db.Exec(statement); err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) SeedDefaults(settings config.Settings) error {
	for _, instrument := range market.DefaultInstruments {
		if err := s.UpsertInstrument(instrument); err != nil {
			return err
		}
	}
	count := 0
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM watchlist_items`).Scan(&count); err != nil {
		return err
	}
	if count == 0 {
		for _, symbol := range market.DefaultWatchlistSymbols {
			instrument, ok := s.FindInstrument(symbol)
			if ok {
				_, _ = s.db.Exec(`INSERT INTO watchlist_items(symbol, provider, asset_class, created_at) VALUES(?, ?, ?, ?)`, instrument.Symbol, instrument.Provider, instrument.AssetClass, time.Now().UTC())
			}
		}
	}
	state, err := s.AppState(settings)
	if err == nil && state.ActiveSymbol != "" {
		return nil
	}
	active := market.DefaultInstrument(settings.Symbol, settings.Provider)
	_, err = s.db.Exec(`INSERT OR REPLACE INTO app_state(id, active_symbol, active_provider, active_asset_class, timeframe, risk_percent, stop_loss_distance, take_profit_distance, leverage, lot_size, updated_at) VALUES(1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		active.Symbol, active.Provider, active.AssetClass, settings.Timeframe, settings.RiskPerTrade*100, 100.0, 200.0, settings.DefaultLeverage, settings.DefaultLotSize, time.Now().UTC())
	return err
}

func (s *Store) UpsertInstrument(instrument market.Instrument) error {
	existing, ok := s.FindInstrument(instrument.Symbol)
	if ok {
		_, err := s.db.Exec(`UPDATE instruments SET display_name=?, asset_class=?, provider=?, base_currency=?, quote_currency=?, digits=?, point=?, contract_size=?, volume_min=?, volume_step=?, default_leverage=?, tick_value=?, spread=?, trade_enabled=? WHERE symbol=? AND provider=?`,
			instrument.DisplayName, instrument.AssetClass, instrument.Provider, instrument.BaseCurrency, instrument.QuoteCurrency, instrument.Digits, instrument.Point, instrument.ContractSize, instrument.VolumeMin, instrument.VolumeStep, instrument.DefaultLeverage, instrument.TickValue, instrument.Spread, instrument.TradeEnabled, existing.Symbol, existing.Provider)
		return err
	}
	_, err := s.db.Exec(`INSERT INTO instruments(symbol, display_name, asset_class, provider, base_currency, quote_currency, digits, point, contract_size, volume_min, volume_step, default_leverage, tick_value, spread, trade_enabled) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		instrument.Symbol, instrument.DisplayName, instrument.AssetClass, instrument.Provider, instrument.BaseCurrency, instrument.QuoteCurrency, instrument.Digits, instrument.Point, instrument.ContractSize, instrument.VolumeMin, instrument.VolumeStep, instrument.DefaultLeverage, instrument.TickValue, instrument.Spread, instrument.TradeEnabled)
	return err
}

func (s *Store) AppState(settings config.Settings) (AppState, error) {
	var state AppState
	err := s.db.QueryRow(`SELECT active_symbol, active_provider, active_asset_class, timeframe, risk_percent, stop_loss_distance, take_profit_distance, leverage, lot_size, updated_at FROM app_state WHERE id=1`).Scan(
		&state.ActiveSymbol, &state.ActiveProvider, &state.ActiveAssetClass, &state.Timeframe, &state.RiskPercent, &state.StopLossDistance, &state.TakeProfitDistance, &state.Leverage, &state.LotSize, &state.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		err = s.SeedDefaults(settings)
		if err != nil {
			return state, err
		}
		return s.AppState(settings)
	}
	return state, err
}

func (s *Store) UpdateState(settings config.Settings, values map[string]any) (AppState, error) {
	state, err := s.AppState(settings)
	if err != nil {
		return state, err
	}
	if symbol, ok := stringValue(values["active_symbol"]); ok {
		instrument := market.DefaultInstrument(symbol, state.ActiveProvider)
		if found, ok := s.FindInstrument(symbol); ok {
			instrument = found
		}
		state.ActiveSymbol, state.ActiveProvider, state.ActiveAssetClass = instrument.Symbol, instrument.Provider, instrument.AssetClass
		_ = s.EnsureWatchlist(instrument)
	}
	if value, ok := stringValue(values["timeframe"]); ok {
		state.Timeframe = value
	}
	setFloat := func(key string, dest *float64) {
		if value, ok := floatValue(values[key]); ok {
			*dest = value
		}
	}
	setFloat("risk_percent", &state.RiskPercent)
	setFloat("stop_loss_distance", &state.StopLossDistance)
	setFloat("take_profit_distance", &state.TakeProfitDistance)
	setFloat("leverage", &state.Leverage)
	setFloat("lot_size", &state.LotSize)
	state.UpdatedAt = time.Now().UTC()
	_, err = s.db.Exec(`UPDATE app_state SET active_symbol=?, active_provider=?, active_asset_class=?, timeframe=?, risk_percent=?, stop_loss_distance=?, take_profit_distance=?, leverage=?, lot_size=?, updated_at=? WHERE id=1`,
		state.ActiveSymbol, state.ActiveProvider, state.ActiveAssetClass, state.Timeframe, state.RiskPercent, state.StopLossDistance, state.TakeProfitDistance, state.Leverage, state.LotSize, state.UpdatedAt)
	return state, err
}

func (s *Store) ActivateSymbol(settings config.Settings, symbol string) (AppState, error) {
	return s.UpdateState(settings, map[string]any{"active_symbol": symbol})
}

func (s *Store) FindInstrument(symbol string) (market.Instrument, bool) {
	rows, err := s.db.Query(`SELECT symbol, display_name, asset_class, provider, base_currency, quote_currency, digits, point, contract_size, volume_min, volume_step, default_leverage, tick_value, spread, trade_enabled FROM instruments`)
	if err != nil {
		return market.Instrument{}, false
	}
	defer rows.Close()
	normalized := market.NormalizeSymbol(symbol)
	for rows.Next() {
		instrument, err := scanInstrument(rows)
		if err == nil && market.NormalizeSymbol(instrument.Symbol) == normalized {
			return instrument, true
		}
	}
	return market.Instrument{}, false
}

func (s *Store) Instruments() ([]market.Instrument, error) {
	rows, err := s.db.Query(`SELECT symbol, display_name, asset_class, provider, base_currency, quote_currency, digits, point, contract_size, volume_min, volume_step, default_leverage, tick_value, spread, trade_enabled FROM instruments ORDER BY asset_class, symbol`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var instruments []market.Instrument
	for rows.Next() {
		instrument, err := scanInstrument(rows)
		if err != nil {
			return nil, err
		}
		instruments = append(instruments, instrument)
	}
	return instruments, rows.Err()
}

func (s *Store) Watchlist() ([]WatchlistItem, error) {
	rows, err := s.db.Query(`SELECT symbol, provider, asset_class FROM watchlist_items ORDER BY asset_class, symbol`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var items []WatchlistItem
	for rows.Next() {
		var item WatchlistItem
		if err := rows.Scan(&item.Symbol, &item.Provider, &item.AssetClass); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) EnsureWatchlist(instrument market.Instrument) error {
	items, err := s.Watchlist()
	if err != nil {
		return err
	}
	for _, item := range items {
		if market.NormalizeSymbol(item.Symbol) == market.NormalizeSymbol(instrument.Symbol) {
			return nil
		}
	}
	_, err = s.db.Exec(`INSERT INTO watchlist_items(symbol, provider, asset_class, created_at) VALUES(?, ?, ?, ?)`, instrument.Symbol, instrument.Provider, instrument.AssetClass, time.Now().UTC())
	return err
}

func (s *Store) LatestOpenTrade(symbol string) (*Trade, error) {
	trades, err := s.Trades(`WHERE symbol=? AND status='open'`, []any{symbol}, 1)
	if err != nil || len(trades) == 0 {
		return nil, err
	}
	return &trades[0], nil
}

func (s *Store) OpenPositionCount() (int, error) {
	var count int
	return count, s.db.QueryRow(`SELECT COUNT(*) FROM trades WHERE status='open'`).Scan(&count)
}

func (s *Store) Trades(where string, args []any, limit int) ([]Trade, error) {
	if limit <= 0 {
		limit = 200
	}
	query := `SELECT id, symbol, provider, asset_class, side, entry_price, exit_price, quantity, lot_size, leverage, margin_required, contract_size, stop_loss, take_profit, pnl, status, mode, opened_at, closed_at, reason FROM trades `
	if strings.TrimSpace(where) != "" {
		query += where + " "
	}
	query += fmt.Sprintf(`ORDER BY id DESC LIMIT %d`, limit)
	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var trades []Trade
	for rows.Next() {
		var trade Trade
		var exit, lot, lev, margin, contract, sl, tp sql.NullFloat64
		var closed sql.NullTime
		if err := rows.Scan(&trade.ID, &trade.Symbol, &trade.Provider, &trade.AssetClass, &trade.Side, &trade.EntryPrice, &exit, &trade.Quantity, &lot, &lev, &margin, &contract, &sl, &tp, &trade.PnL, &trade.Status, &trade.Mode, &trade.OpenedAt, &closed, &trade.Reason); err != nil {
			return nil, err
		}
		trade.ExitPrice, trade.LotSize, trade.Leverage = ptrFloat(exit), ptrFloat(lot), ptrFloat(lev)
		trade.MarginRequired, trade.ContractSize, trade.StopLoss, trade.TakeProfit = ptrFloat(margin), ptrFloat(contract), ptrFloat(sl), ptrFloat(tp)
		if closed.Valid {
			trade.ClosedAt = &closed.Time
		}
		trades = append(trades, trade)
	}
	return trades, rows.Err()
}

func (s *Store) InsertSignal(signal Signal) error {
	_, err := s.db.Exec(`INSERT INTO signals(symbol, provider, asset_class, timeframe, signal, rsi, fast_ma, slow_ma, price, reason, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		signal.Symbol, signal.Provider, signal.AssetClass, signal.Timeframe, signal.Signal, signal.RSI, signal.FastMA, signal.SlowMA, signal.Price, signal.Reason, time.Now().UTC())
	return err
}

func (s *Store) Signals(limit int) ([]Signal, error) {
	rows, err := s.db.Query(`SELECT id, symbol, provider, asset_class, timeframe, signal, rsi, fast_ma, slow_ma, price, reason, created_at FROM signals ORDER BY id DESC LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var signals []Signal
	for rows.Next() {
		var signal Signal
		var rsi, fast, slow sql.NullFloat64
		if err := rows.Scan(&signal.ID, &signal.Symbol, &signal.Provider, &signal.AssetClass, &signal.Timeframe, &signal.Signal, &rsi, &fast, &slow, &signal.Price, &signal.Reason, &signal.CreatedAt); err != nil {
			return nil, err
		}
		signal.RSI, signal.FastMA, signal.SlowMA = ptrFloat(rsi), ptrFloat(fast), ptrFloat(slow)
		signals = append(signals, signal)
	}
	return signals, rows.Err()
}

func (s *Store) LatestSignal(symbol string) (*Signal, error) {
	signals, err := s.Signals(200)
	if err != nil {
		return nil, err
	}
	for _, signal := range signals {
		if signal.Symbol == symbol {
			return &signal, nil
		}
	}
	return nil, nil
}

func (s *Store) RiskEvents(limit int) ([]RiskEvent, error) {
	rows, err := s.db.Query(`SELECT id, event_type, message, created_at FROM risk_events ORDER BY id DESC LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var events []RiskEvent
	for rows.Next() {
		var event RiskEvent
		if err := rows.Scan(&event.ID, &event.EventType, &event.Message, &event.CreatedAt); err != nil {
			return nil, err
		}
		events = append(events, event)
	}
	return events, rows.Err()
}

func (s *Store) InsertRiskEvent(eventType, message string) {
	_, _ = s.db.Exec(`INSERT INTO risk_events(event_type, message, created_at) VALUES(?, ?, ?)`, eventType, message, time.Now().UTC())
}

func (s *Store) InsertOpenTrade(trade Trade) error {
	_, err := s.db.Exec(`INSERT INTO trades(symbol, provider, asset_class, side, entry_price, quantity, lot_size, leverage, margin_required, contract_size, stop_loss, take_profit, pnl, status, mode, opened_at, reason) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		trade.Symbol, trade.Provider, trade.AssetClass, trade.Side, trade.EntryPrice, trade.Quantity, trade.LotSize, trade.Leverage, trade.MarginRequired, trade.ContractSize, trade.StopLoss, trade.TakeProfit, trade.PnL, trade.Status, trade.Mode, time.Now().UTC(), trade.Reason)
	return err
}

func (s *Store) CloseTrade(id int64, exitPrice, pnl float64, reason string) error {
	_, err := s.db.Exec(`UPDATE trades SET exit_price=?, pnl=?, status='closed', closed_at=?, reason=? WHERE id=?`, exitPrice, pnl, time.Now().UTC(), reason, id)
	return err
}

func (s *Store) CreateConfirmation(action, requester string, payload map[string]any) (Confirmation, error) {
	code := fmt.Sprintf("%06d", time.Now().UnixNano()%1000000)
	data, _ := json.Marshal(payload)
	expires := time.Now().UTC().Add(2 * time.Minute)
	_, err := s.db.Exec(`INSERT INTO confirmation_codes(code, action, requester_id, payload, expires_at, created_at) VALUES(?, ?, ?, ?, ?, ?)`, code, action, requester, string(data), expires, time.Now().UTC())
	return Confirmation{Code: code, Action: action, Requester: requester, Payload: payload, ExpiresAt: expires}, err
}

func (s *Store) ConsumeConfirmation(code, action, requester string) (map[string]any, bool) {
	var payloadText string
	var id int64
	var storedRequester sql.NullString
	var expires time.Time
	err := s.db.QueryRow(`SELECT id, requester_id, payload, expires_at FROM confirmation_codes WHERE code=? AND action=? AND used_at IS NULL ORDER BY id DESC LIMIT 1`, code, action).Scan(&id, &storedRequester, &payloadText, &expires)
	if err != nil || time.Now().UTC().After(expires) {
		return nil, false
	}
	if storedRequester.Valid && storedRequester.String != "" && requester != "" && storedRequester.String != requester {
		return nil, false
	}
	_, _ = s.db.Exec(`UPDATE confirmation_codes SET used_at=? WHERE id=?`, time.Now().UTC(), id)
	payload := map[string]any{}
	_ = json.Unmarshal([]byte(payloadText), &payload)
	return payload, true
}

func scanInstrument(rows interface{ Scan(dest ...any) error }) (market.Instrument, error) {
	var instrument market.Instrument
	var tick, spread sql.NullFloat64
	err := rows.Scan(&instrument.Symbol, &instrument.DisplayName, &instrument.AssetClass, &instrument.Provider, &instrument.BaseCurrency, &instrument.QuoteCurrency, &instrument.Digits, &instrument.Point, &instrument.ContractSize, &instrument.VolumeMin, &instrument.VolumeStep, &instrument.DefaultLeverage, &tick, &spread, &instrument.TradeEnabled)
	instrument.TickValue, instrument.Spread = ptrFloat(tick), ptrFloat(spread)
	return instrument, err
}

func ptrFloat(value sql.NullFloat64) *float64 {
	if !value.Valid {
		return nil
	}
	v := value.Float64
	return &v
}

func stringValue(value any) (string, bool) {
	v, ok := value.(string)
	return v, ok && v != ""
}

func floatValue(value any) (float64, bool) {
	switch v := value.(type) {
	case float64:
		return v, true
	case int:
		return float64(v), true
	default:
		return 0, false
	}
}
