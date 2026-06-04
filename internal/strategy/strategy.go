package strategy

import (
	"fmt"
	"math"
	"strings"

	"trader/internal/config"
	"trader/internal/market"
)

type Decision struct {
	Signal string
	Reason string
	Price  float64
	RSI    *float64
	FastMA *float64
	SlowMA *float64
}

type Engine struct {
	settings config.Settings
}

func New(settings config.Settings) Engine {
	return Engine{settings: settings}
}

func (e Engine) Evaluate(frames map[string][]market.Candle, hasOpenPosition bool, entryPrice *float64) Decision {
	signalCandles := chooseFrame(frames, "15m")
	entryCandles := chooseFrame(frames, "5m")
	trendCandles := chooseFrame(frames, "4h")
	structureCandles := chooseFrame(frames, "1h")
	rsiPeriod, fastPeriod, slowPeriod := e.settings.RSIPeriod, e.settings.FastMA, e.settings.SlowMA
	if e.settings.Timeframe == "1s" {
		rsiPeriod, fastPeriod, slowPeriod = e.settings.ScalpRSIPeriod, e.settings.ScalpFastMA, e.settings.ScalpSlowMA
	}
	if len(signalCandles) < max(slowPeriod, 60) {
		return Decision{Signal: "hold", Reason: "not enough candles"}
	}
	enriched := addIndicators(signalCandles, rsiPeriod, fastPeriod, slowPeriod)
	trend := enriched
	if len(trendCandles) >= 60 {
		trend = addIndicators(trendCandles, rsiPeriod, fastPeriod, slowPeriod)
	}
	structure := enriched
	if len(structureCandles) >= 30 {
		structure = addIndicators(structureCandles, rsiPeriod, fastPeriod, slowPeriod)
	}
	entry := enriched
	if len(entryCandles) >= 30 {
		entry = addIndicators(entryCandles, rsiPeriod, fastPeriod, slowPeriod)
	}
	latest := enriched[len(enriched)-1]
	decision := Decision{Signal: "hold", Reason: "indicators not ready", Price: latest.Close, RSI: optional(latest.RSI), FastMA: optional(latest.EMA9), SlowMA: optional(latest.EMA21)}
	if decision.RSI == nil || decision.FastMA == nil || decision.SlowMA == nil {
		return decision
	}
	if hasOpenPosition && entryPrice != nil {
		if latest.Close <= *entryPrice*(1-e.settings.StopLossPercent) {
			decision.Signal, decision.Reason = "sell", "stop-loss hit"
			return decision
		}
		if latest.Close >= *entryPrice*(1+e.settings.TakeProfitPercent) {
			decision.Signal, decision.Reason = "sell", "take-profit hit"
			return decision
		}
	}
	longScore := scoreDirection(enriched, trend, structure, entry, "long")
	shortScore := scoreDirection(enriched, trend, structure, entry, "short")
	if hasOpenPosition && shortScore.Valid {
		decision.Signal, decision.Reason = "sell", shortScore.Reason()
		return decision
	}
	if !hasOpenPosition && longScore.Valid {
		decision.Signal, decision.Reason = "buy", longScore.Reason()
		return decision
	}
	if !hasOpenPosition && shortScore.Valid {
		decision.Reason = "short setup ignored; long-only execution; " + shortScore.Reason()
		return decision
	}
	best := longScore
	if shortScore.Total >= longScore.Total {
		best = shortScore
	}
	decision.Reason = best.Reason()
	return decision
}

type confluenceScore struct {
	Direction string
	Total     float64
	Trend     int
	Momentum  int
	Volume    int
	Structure bool
	Valid     bool
	Fired     []string
	Blocked   []string
}

func (s confluenceScore) Reason() string {
	confidence := "LOW"
	if s.Total >= 8 {
		confidence = "HIGH"
	} else if s.Total >= 6 {
		confidence = "MEDIUM"
	}
	fired := "none"
	if len(s.Fired) > 0 {
		fired = strings.Join(s.Fired[:min(len(s.Fired), 8)], ", ")
	}
	blocked := "none"
	if len(s.Blocked) > 0 {
		blocked = strings.Join(s.Blocked[:min(len(s.Blocked), 4)], ", ")
	}
	return fmt.Sprintf("%s confluence %.1f/10 (trend %d/4, momentum %d/3, volume %d/2, structure %s, confidence %s); signals: %s; blockers: %s",
		strings.ToUpper(s.Direction), s.Total, s.Trend, s.Momentum, s.Volume, yesNo(s.Structure), confidence, fired, blocked)
}

func scoreDirection(signal, trend, structure, entry []enriched, direction string) confluenceScore {
	latest, previous := signal[len(signal)-1], signal[len(signal)-2]
	trendLatest := trend[len(trend)-1]
	long := direction == "long"
	score := confluenceScore{Direction: direction}
	add := func(name, group string, points float64) {
		score.Total += points
		score.Fired = append(score.Fired, name)
		switch group {
		case "trend":
			score.Trend++
		case "momentum":
			score.Momentum++
		case "volume":
			score.Volume++
		}
	}
	if valid(latest.EMA9, latest.EMA21) && ((long && latest.Close > latest.EMA9 && latest.EMA9 > latest.EMA21) || (!long && latest.Close < latest.EMA9 && latest.EMA9 < latest.EMA21)) {
		add("fast/slow EMA alignment", "trend", 1)
	} else {
		score.Blocked = append(score.Blocked, "EMA alignment")
	}
	if valid(trendLatest.EMA200) && ((long && trendLatest.Close > trendLatest.EMA200) || (!long && trendLatest.Close < trendLatest.EMA200)) {
		add("200 EMA filter", "trend", 1)
	} else {
		score.Blocked = append(score.Blocked, "200 EMA hard filter")
	}
	if valid(latest.MACD, latest.MACDSignal) && ((long && latest.MACD > latest.MACDSignal) || (!long && latest.MACD < latest.MACDSignal)) {
		add("MACD alignment", "trend", 1)
		if valid(latest.MACDHist, previous.MACDHist) && ((long && latest.MACDHist > previous.MACDHist) || (!long && latest.MACDHist < previous.MACDHist)) {
			score.Total += 0.5
			score.Fired = append(score.Fired, "MACD histogram momentum")
		}
	} else {
		score.Blocked = append(score.Blocked, "MACD")
	}
	if valid(latest.ADX, latest.PlusDI, latest.MinusDI) && latest.ADX > 25 && ((long && latest.PlusDI > latest.MinusDI) || (!long && latest.MinusDI > latest.PlusDI)) {
		add("ADX/DI trend strength", "trend", 1)
	} else {
		score.Blocked = append(score.Blocked, "ADX/DI")
	}
	if valid(latest.RSI, previous.RSI) && ((long && latest.RSI > previous.RSI) || (!long && latest.RSI < previous.RSI)) {
		add("RSI slope", "momentum", 1)
	} else {
		score.Blocked = append(score.Blocked, "RSI slope")
	}
	if valid(latest.StochK, latest.StochD, previous.StochK, previous.StochD) && ((long && previous.StochK <= previous.StochD && latest.StochK > latest.StochD && latest.StochK < 80) || (!long && previous.StochK >= previous.StochD && latest.StochK < latest.StochD && latest.StochK > 20)) {
		add("Stoch RSI cross", "momentum", 1)
	} else {
		score.Blocked = append(score.Blocked, "Stoch RSI")
	}
	if valid(latest.ROC, previous.ROC) && ((long && latest.ROC > 0 && latest.ROC > previous.ROC) || (!long && latest.ROC < 0 && latest.ROC < previous.ROC)) {
		add("ROC acceleration", "momentum", 1)
	} else {
		score.Blocked = append(score.Blocked, "ROC")
	}
	avgVolume := averageVolume(signal, 20)
	if avgVolume > 0 && latest.Volume > 1.5*avgVolume {
		add("volume spike", "volume", 1)
	} else {
		score.Blocked = append(score.Blocked, "volume spike")
	}
	obvPrev := math.NaN()
	if len(signal) >= 5 {
		obvPrev = signal[len(signal)-5].OBV
	}
	if valid(latest.OBV, obvPrev) && ((long && latest.OBV > obvPrev) || (!long && latest.OBV < obvPrev)) {
		add("OBV trend", "volume", 1)
	} else {
		score.Blocked = append(score.Blocked, "OBV")
	}
	score.Structure = structureBreakout(signal, structure, direction, 20)
	if score.Structure {
		score.Total += 1
		score.Fired = append(score.Fired, "structure breakout")
	} else {
		score.Blocked = append(score.Blocked, "structure breakout mandatory")
	}
	score.Valid = score.Total >= 6 && score.Trend >= 3 && score.Momentum >= 2 && score.Volume >= 1 && score.Structure
	_ = entry
	return score
}

func structureBreakout(signal, structure []enriched, direction string, lookback int) bool {
	if len(signal) < lookback+2 {
		return false
	}
	latest := signal[len(signal)-1].Close
	signalHigh, signalLow := extrema(signal[len(signal)-lookback-1 : len(signal)-1])
	structureHigh, structureLow := signalHigh, signalLow
	if len(structure) >= lookback+2 {
		structureHigh, structureLow = extrema(structure[len(structure)-lookback-1 : len(structure)-1])
	}
	if direction == "long" {
		return latest > math.Min(signalHigh, structureHigh)
	}
	return latest < math.Max(signalLow, structureLow)
}

func chooseFrame(frames map[string][]market.Candle, key string) []market.Candle {
	if frame := frames[key]; len(frame) > 0 {
		return frame
	}
	for _, frame := range frames {
		return frame
	}
	return nil
}

func extrema(values []enriched) (float64, float64) {
	high, low := math.Inf(-1), math.Inf(1)
	for _, value := range values {
		high = math.Max(high, value.High)
		low = math.Min(low, value.Low)
	}
	return high, low
}

func averageVolume(values []enriched, period int) float64 {
	if len(values) < period {
		return 0
	}
	sum := 0.0
	for _, value := range values[len(values)-period:] {
		sum += value.Volume
	}
	return sum / float64(period)
}

func optional(value float64) *float64 {
	if math.IsNaN(value) {
		return nil
	}
	return &value
}

func valid(values ...float64) bool {
	for _, value := range values {
		if math.IsNaN(value) {
			return false
		}
	}
	return true
}

func yesNo(value bool) string {
	if value {
		return "yes"
	}
	return "no"
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
