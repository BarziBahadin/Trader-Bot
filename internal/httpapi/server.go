package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"strconv"
	"strings"

	"trader/internal/config"
	"trader/internal/db"
	"trader/internal/market"
	"trader/internal/providers"
	"trader/internal/risk"
)

type Server struct {
	settings config.Settings
	store    *db.Store
	mux      *http.ServeMux
}

func NewServer(settings config.Settings, store *db.Store) http.Handler {
	server := &Server{settings: settings, store: store, mux: http.NewServeMux()}
	server.routes()
	return server.middleware(server.mux)
}

func (s *Server) routes() {
	for _, prefix := range []string{"/api/v1", "/api"} {
		s.mux.HandleFunc(prefix+"/status", s.auth(s.status))
		s.mux.HandleFunc(prefix+"/worker", s.auth(s.worker))
		s.mux.HandleFunc(prefix+"/account", s.auth(s.account))
		s.mux.HandleFunc(prefix+"/live-readiness", s.auth(s.liveReadiness))
		s.mux.HandleFunc(prefix+"/symbols", s.symbols)
		s.mux.HandleFunc(prefix+"/watchlist", s.watchlist)
		s.mux.HandleFunc(prefix+"/symbols/activate", s.auth(s.activateSymbol))
		s.mux.HandleFunc(prefix+"/settings", s.auth(s.settingsHandler))
		s.mux.HandleFunc(prefix+"/position-size", s.auth(s.positionSize))
		s.mux.HandleFunc(prefix+"/candles", s.candles)
		s.mux.HandleFunc(prefix+"/trades", s.auth(s.trades))
		s.mux.HandleFunc(prefix+"/signals", s.auth(s.signals))
		s.mux.HandleFunc(prefix+"/risk-events", s.auth(s.riskEvents))
		s.mux.HandleFunc(prefix+"/emergency-stop", s.auth(s.emergencyStop))
		s.mux.HandleFunc(prefix+"/resume", s.auth(s.resume))
		s.mux.HandleFunc(prefix+"/position/close/preview", s.auth(s.closePreview))
		s.mux.HandleFunc(prefix+"/position/close/confirm", s.auth(s.closeConfirm))
	}
	s.mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
}

func (s *Server) status(w http.ResponseWriter, r *http.Request) {
	state, err := s.store.AppState(s.settings)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	provider := providers.Build(state.ActiveProvider, s.settings)
	latest := latestPrice(r.Context(), provider, state.ActiveSymbol, state.Timeframe)
	account := provider.AccountSummary(r.Context())
	open, _ := s.store.LatestOpenTrade(state.ActiveSymbol)
	_, stopped := stopped(s.settings.StopFile)
	writeJSON(w, http.StatusOK, map[string]any{
		"mode": s.settings.BotMode, "real_trading_enabled": s.settings.EnableRealTrading, "symbol": state.ActiveSymbol,
		"provider": state.ActiveProvider, "asset_class": state.ActiveAssetClass, "timeframe": state.Timeframe,
		"risk_percent": state.RiskPercent, "lot_size": state.LotSize, "leverage": state.Leverage,
		"emergency_stop": stopped, "open_position": open != nil, "latest_price": latest,
		"provider_status": provider.Status(r.Context()), "account": account, "live_readiness": risk.LiveReadiness(s.settings, state.ActiveSymbol),
	})
}

func (s *Server) worker(w http.ResponseWriter, r *http.Request) {
	_, stopped := stopped(s.settings.StopFile)
	writeJSON(w, http.StatusOK, map[string]any{"running": s.settings.AutoStartWorker, "loop_interval_seconds": s.settings.TradingLoopSeconds, "emergency_stop": stopped})
}

func (s *Server) account(w http.ResponseWriter, r *http.Request) {
	state, _ := s.store.AppState(s.settings)
	writeJSON(w, http.StatusOK, providers.Build(state.ActiveProvider, s.settings).AccountSummary(r.Context()))
}

func (s *Server) liveReadiness(w http.ResponseWriter, r *http.Request) {
	state, _ := s.store.AppState(s.settings)
	writeJSON(w, http.StatusOK, risk.LiveReadiness(s.settings, state.ActiveSymbol))
}

func (s *Server) symbols(w http.ResponseWriter, r *http.Request) {
	instruments, err := s.store.Instruments()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, instruments)
}

func (s *Server) watchlist(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.Watchlist()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}

func (s *Server) activateSymbol(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
		return
	}
	var request struct {
		Symbol string `json:"symbol"`
	}
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	state, err := s.store.ActivateSymbol(s.settings, request.Symbol)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, state)
}

func (s *Server) settingsHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		state, err := s.store.AppState(s.settings)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err)
			return
		}
		writeJSON(w, http.StatusOK, state)
	case http.MethodPatch:
		values := map[string]any{}
		if err := json.NewDecoder(r.Body).Decode(&values); err != nil {
			writeError(w, http.StatusBadRequest, err)
			return
		}
		state, err := s.store.UpdateState(s.settings, values)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err)
			return
		}
		writeJSON(w, http.StatusOK, state)
	default:
		writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
	}
}

func (s *Server) positionSize(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, errors.New("method not allowed"))
		return
	}
	var request struct {
		Symbol             string  `json:"symbol"`
		RiskPercent        float64 `json:"risk_percent"`
		StopLossDistance   float64 `json:"stop_loss_distance"`
		TakeProfitDistance float64 `json:"take_profit_distance"`
		Leverage           float64 `json:"leverage"`
		Price              float64 `json:"price"`
	}
	_ = json.NewDecoder(r.Body).Decode(&request)
	state, _ := s.store.AppState(s.settings)
	if request.Symbol == "" {
		request.Symbol = state.ActiveSymbol
	}
	instrument, ok := s.store.FindInstrument(request.Symbol)
	if !ok {
		writeError(w, http.StatusNotFound, errors.New("unknown symbol "+request.Symbol))
		return
	}
	price := request.Price
	if price <= 0 {
		price = latestPrice(r.Context(), providers.Build(instrument.Provider, s.settings), instrument.Symbol, state.Timeframe)
	}
	if price <= 0 {
		price = latestPrice(r.Context(), providers.Build("paper", s.settings), instrument.Symbol, state.Timeframe)
	}
	if price <= 0 {
		writeError(w, http.StatusServiceUnavailable, errors.New("price unavailable for "+instrument.Symbol))
		return
	}
	riskPercent, sl, tp, lev := request.RiskPercent, request.StopLossDistance, request.TakeProfitDistance, request.Leverage
	if riskPercent <= 0 {
		riskPercent = state.RiskPercent
	}
	if sl <= 0 {
		sl = state.StopLossDistance
	}
	if tp <= 0 {
		tp = state.TakeProfitDistance
	}
	if lev <= 0 {
		lev = state.Leverage
	}
	preview, err := market.CalculatePositionSize(instrument, s.settings.InitialBalance, price, riskPercent, sl, tp, lev, s.settings.AccountCurrency)
	if err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	writeJSON(w, http.StatusOK, preview)
}

func (s *Server) candles(w http.ResponseWriter, r *http.Request) {
	symbol := r.URL.Query().Get("symbol")
	timeframe := r.URL.Query().Get("timeframe")
	if timeframe == "" {
		timeframe = "15m"
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 {
		limit = 120
	}
	if symbol == "" {
		writeError(w, http.StatusBadRequest, errors.New("symbol is required"))
		return
	}
	instrument, ok := s.store.FindInstrument(symbol)
	if !ok {
		writeError(w, http.StatusNotFound, errors.New("unknown symbol "+symbol))
		return
	}
	rows, err := providers.Build(instrument.Provider, s.settings).Candles(r.Context(), instrument.Symbol, timeframe, limit)
	if err != nil {
		if s.settings.BotMode == "live" && strings.Contains(instrument.Symbol, ":USDT") {
			writeError(w, http.StatusServiceUnavailable, errors.New(instrument.Provider+" market data unavailable"))
			return
		}
		rows, err = providers.Build("paper", s.settings).Candles(r.Context(), instrument.Symbol, timeframe, limit)
	}
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func (s *Server) trades(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.Trades("", nil, 200)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func (s *Server) signals(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.Signals(200)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func (s *Server) riskEvents(w http.ResponseWriter, r *http.Request) {
	rows, err := s.store.RiskEvents(200)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func (s *Server) emergencyStop(w http.ResponseWriter, r *http.Request) {
	if err := risk.CreateStopFile(s.settings.StopFile); err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"emergency_stop": true})
}

func (s *Server) resume(w http.ResponseWriter, r *http.Request) {
	if err := risk.RemoveStopFile(s.settings.StopFile); err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"emergency_stop": false})
}

func (s *Server) closePreview(w http.ResponseWriter, r *http.Request) {
	state, _ := s.store.AppState(s.settings)
	trade, _ := s.store.LatestOpenTrade(state.ActiveSymbol)
	if trade == nil {
		writeError(w, http.StatusNotFound, errors.New("no open position"))
		return
	}
	confirmation, err := s.store.CreateConfirmation("close_position", "", map[string]any{"trade_id": trade.ID, "symbol": trade.Symbol, "quantity": trade.Quantity})
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"code": confirmation.Code, "expires_at": confirmation.ExpiresAt, "trade": trade})
}

func (s *Server) closeConfirm(w http.ResponseWriter, r *http.Request) {
	var request struct {
		Code string `json:"code"`
	}
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	payload, ok := s.store.ConsumeConfirmation(request.Code, "close_position", "")
	if !ok {
		writeError(w, http.StatusBadRequest, errors.New("invalid or expired confirmation code"))
		return
	}
	id := int64(payload["trade_id"].(float64))
	trades, _ := s.store.Trades("WHERE id=? AND status='open'", []any{id}, 1)
	if len(trades) == 0 {
		writeError(w, http.StatusNotFound, errors.New("open trade not found"))
		return
	}
	trade := trades[0]
	if err := risk.ValidateLive(s.settings, trade.Provider, trade.Symbol); err != nil {
		writeError(w, http.StatusForbidden, err)
		return
	}
	provider := providers.Build(trade.Provider, s.settings)
	_, err := provider.ClosePosition(r.Context(), trade.Symbol, trade.Quantity)
	if err != nil {
		writeError(w, http.StatusBadGateway, err)
		return
	}
	exit := latestPrice(r.Context(), provider, trade.Symbol, s.settings.Timeframe)
	if exit <= 0 {
		exit = trade.EntryPrice
	}
	_ = s.store.CloseTrade(trade.ID, exit, (exit-trade.EntryPrice)*trade.Quantity, trade.Reason)
	trades, _ = s.store.Trades("WHERE id=?", []any{id}, 1)
	writeJSON(w, http.StatusOK, trades[0])
}

func latestPrice(ctx context.Context, provider providers.Provider, symbol, timeframe string) float64 {
	rows, err := provider.Candles(ctx, symbol, timeframe, 2)
	if err != nil || len(rows) == 0 {
		return 0
	}
	return rows[len(rows)-1].Close
}

func (s *Server) auth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if s.settings.APIAuthToken != "" && r.Header.Get("X-API-Key") != s.settings.APIAuthToken {
			writeError(w, http.StatusUnauthorized, errors.New("missing or invalid API token"))
			return
		}
		next(w, r)
	}
}

func (s *Server) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		for _, allowed := range s.settings.CORSOrigins {
			if origin == allowed {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				w.Header().Set("Access-Control-Allow-Credentials", "true")
				break
			}
		}
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"detail": err.Error()})
}

func stopped(path string) (error, bool) {
	if _, statErr := os.Stat(path); statErr == nil {
		return nil, true
	}
	return nil, false
}
