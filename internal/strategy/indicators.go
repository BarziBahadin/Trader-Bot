package strategy

import (
	"math"

	"trader/internal/market"
)

type enriched struct {
	market.Candle
	RSI        float64
	FastMA     float64
	SlowMA     float64
	EMA9       float64
	EMA21      float64
	EMA200     float64
	MACD       float64
	MACDSignal float64
	MACDHist   float64
	StochK     float64
	StochD     float64
	ROC        float64
	OBV        float64
	ADX        float64
	PlusDI     float64
	MinusDI    float64
}

func addIndicators(candles []market.Candle, rsiPeriod, fastPeriod, slowPeriod int) []enriched {
	out := make([]enriched, len(candles))
	closes, highs, lows, volumes := make([]float64, len(candles)), make([]float64, len(candles)), make([]float64, len(candles)), make([]float64, len(candles))
	for i, candle := range candles {
		out[i].Candle = candle
		closes[i], highs[i], lows[i], volumes[i] = candle.Close, candle.High, candle.Low, candle.Volume
	}
	rsiValues := rsi(closes, rsiPeriod)
	fastMA, slowMA := sma(closes, fastPeriod), sma(closes, slowPeriod)
	ema9, ema21, ema200 := ema(closes, 9), ema(closes, 21), ema(closes, 200)
	macdLine, macdSignal := macd(closes)
	stochK, stochD := stochRSI(closes, rsiPeriod)
	rocValues := roc(closes, 10)
	obvValues := obv(closes, volumes)
	adxValues, plusDI, minusDI := adx(highs, lows, closes, 14)
	for i := range out {
		out[i].RSI, out[i].FastMA, out[i].SlowMA = rsiValues[i], fastMA[i], slowMA[i]
		out[i].EMA9, out[i].EMA21, out[i].EMA200 = ema9[i], ema21[i], ema200[i]
		out[i].MACD, out[i].MACDSignal, out[i].MACDHist = macdLine[i], macdSignal[i], macdLine[i]-macdSignal[i]
		out[i].StochK, out[i].StochD, out[i].ROC = stochK[i], stochD[i], rocValues[i]
		out[i].OBV, out[i].ADX, out[i].PlusDI, out[i].MinusDI = obvValues[i], adxValues[i], plusDI[i], minusDI[i]
	}
	return out
}

func sma(values []float64, period int) []float64 {
	out := nanSlice(len(values))
	sum := 0.0
	validCount := 0
	for i, value := range values {
		if !math.IsNaN(value) {
			sum += value
			validCount++
		}
		if i >= period {
			if !math.IsNaN(values[i-period]) {
				sum -= values[i-period]
				validCount--
			}
		}
		if i >= period-1 && validCount == period {
			out[i] = sum / float64(period)
		}
	}
	return out
}

func ema(values []float64, period int) []float64 {
	out := nanSlice(len(values))
	alpha := 2.0 / float64(period+1)
	prev := 0.0
	seed := make([]float64, 0, period)
	seeded := false
	for i, value := range values {
		if math.IsNaN(value) {
			continue
		}
		if !seeded {
			seed = append(seed, value)
			if len(seed) < period {
				continue
			}
			sum := 0.0
			for _, seedValue := range seed {
				sum += seedValue
			}
			prev = sum / float64(period)
			seeded = true
			out[i] = prev
			continue
		}
		prev = value*alpha + prev*(1-alpha)
		out[i] = prev
	}
	return out
}

func rsi(values []float64, period int) []float64 {
	out := nanSlice(len(values))
	if len(values) <= period {
		return out
	}
	gain, loss := 0.0, 0.0
	for i := 1; i <= period; i++ {
		diff := values[i] - values[i-1]
		if diff > 0 {
			gain += diff
		} else {
			loss -= diff
		}
	}
	avgGain, avgLoss := gain/float64(period), loss/float64(period)
	for i := period; i < len(values); i++ {
		if i > period {
			diff := values[i] - values[i-1]
			g, l := 0.0, 0.0
			if diff > 0 {
				g = diff
			} else {
				l = -diff
			}
			avgGain = (avgGain*float64(period-1) + g) / float64(period)
			avgLoss = (avgLoss*float64(period-1) + l) / float64(period)
		}
		if avgLoss == 0 {
			out[i] = 100
		} else {
			rs := avgGain / avgLoss
			out[i] = 100 - (100 / (1 + rs))
		}
	}
	return out
}

func macd(values []float64) ([]float64, []float64) {
	fast, slow := ema(values, 12), ema(values, 26)
	line := nanSlice(len(values))
	for i := range values {
		if !math.IsNaN(fast[i]) && !math.IsNaN(slow[i]) {
			line[i] = fast[i] - slow[i]
		}
	}
	return line, ema(line, 9)
}

func roc(values []float64, period int) []float64 {
	out := nanSlice(len(values))
	for i := period; i < len(values); i++ {
		if values[i-period] != 0 {
			out[i] = ((values[i] - values[i-period]) / values[i-period]) * 100
		}
	}
	return out
}

func stochRSI(values []float64, period int) ([]float64, []float64) {
	rsiValues := rsi(values, period)
	raw := nanSlice(len(values))
	for i := period * 2; i < len(values); i++ {
		low, high := math.Inf(1), math.Inf(-1)
		for j := i - period + 1; j <= i; j++ {
			if rsiValues[j] < low {
				low = rsiValues[j]
			}
			if rsiValues[j] > high {
				high = rsiValues[j]
			}
		}
		if high > low {
			raw[i] = ((rsiValues[i] - low) / (high - low)) * 100
		}
	}
	return sma(raw, 3), sma(sma(raw, 3), 3)
}

func obv(closes, volumes []float64) []float64 {
	out := make([]float64, len(closes))
	for i := 1; i < len(closes); i++ {
		direction := 0.0
		if closes[i] > closes[i-1] {
			direction = 1
		} else if closes[i] < closes[i-1] {
			direction = -1
		}
		out[i] = out[i-1] + direction*volumes[i]
	}
	return out
}

func adx(highs, lows, closes []float64, period int) ([]float64, []float64, []float64) {
	plusDM, minusDM, tr := make([]float64, len(closes)), make([]float64, len(closes)), make([]float64, len(closes))
	for i := 1; i < len(closes); i++ {
		up, down := highs[i]-highs[i-1], lows[i-1]-lows[i]
		if up > down && up > 0 {
			plusDM[i] = up
		}
		if down > up && down > 0 {
			minusDM[i] = down
		}
		tr[i] = math.Max(highs[i]-lows[i], math.Max(math.Abs(highs[i]-closes[i-1]), math.Abs(lows[i]-closes[i-1])))
	}
	atr, plusEMA, minusEMA := ema(tr, period), ema(plusDM, period), ema(minusDM, period)
	plusDI, minusDI, dx := nanSlice(len(closes)), nanSlice(len(closes)), nanSlice(len(closes))
	for i := range closes {
		if !math.IsNaN(atr[i]) && atr[i] != 0 {
			plusDI[i] = 100 * plusEMA[i] / atr[i]
			minusDI[i] = 100 * minusEMA[i] / atr[i]
			sum := plusDI[i] + minusDI[i]
			if sum != 0 {
				dx[i] = math.Abs(plusDI[i]-minusDI[i]) / sum * 100
			}
		}
	}
	return ema(dx, period), plusDI, minusDI
}

func nanSlice(size int) []float64 {
	out := make([]float64, size)
	for i := range out {
		out[i] = math.NaN()
	}
	return out
}
