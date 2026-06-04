import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CandlestickSeries, ColorType, createChart, HistogramSeries, LineSeries } from 'lightweight-charts';

function toUnixTime(value) {
  const parsed = Date.parse(value);
  if (!Number.isNaN(parsed)) {
    return Math.floor(parsed / 1000);
  }
  return Math.floor(Number(value) / 1000);
}

export default function TradingChart({ candles, symbol, timeframe, onTimeframeChange }) {
  const containerRef = useRef(null);
  const rsiContainerRef = useRef(null);
  const chartRef = useRef(null);
  const rsiChartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const ma20SeriesRef = useRef(null);
  const ma50SeriesRef = useRef(null);
  const rsiSeriesRef = useRef(null);
  const fittedKeyRef = useRef('');
  const [selectedCandle, setSelectedCandle] = useState(null);

  const chartData = useMemo(() => {
    return candles
      .map((candle) => ({
        time: toUnixTime(candle.timestamp),
        open: Number(candle.open),
        high: Number(candle.high),
        low: Number(candle.low),
        close: Number(candle.close),
        volume: Number(candle.volume || 0),
      }))
      .filter((candle) => Number.isFinite(candle.time) && Number.isFinite(candle.close))
      .sort((a, b) => a.time - b.time);
  }, [candles]);

  const ma20Data = useMemo(() => movingAverage(chartData, 20), [chartData]);
  const ma50Data = useMemo(() => movingAverage(chartData, 50), [chartData]);
  const rsiData = useMemo(() => rsi(chartData, 14), [chartData]);
  const latest = selectedCandle || chartData[chartData.length - 1];

  useEffect(() => {
    if (!containerRef.current || !rsiContainerRef.current) return undefined;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#111827' },
        textColor: '#b7c1cc',
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: 'rgba(75, 85, 99, 0.35)' },
        horzLines: { color: 'rgba(75, 85, 99, 0.35)' },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: '#75819a', width: 1, style: 3, labelBackgroundColor: '#2962ff' },
        horzLine: { color: '#75819a', width: 1, style: 3, labelBackgroundColor: '#2962ff' },
      },
      rightPriceScale: {
        borderColor: '#374151',
        scaleMargins: { top: 0.08, bottom: 0.22 },
      },
      timeScale: {
        borderColor: '#374151',
        timeVisible: true,
        secondsVisible: timeframe === '1s',
        rightOffset: 8,
        barSpacing: 9,
      },
      handleScroll: true,
      handleScale: true,
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    });

    const rsiChart = createChart(rsiContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#111827' },
        textColor: '#b7c1cc',
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: 'rgba(75, 85, 99, 0.35)' },
        horzLines: { color: 'rgba(75, 85, 99, 0.35)' },
      },
      rightPriceScale: {
        borderColor: '#374151',
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: '#374151',
        timeVisible: true,
        secondsVisible: timeframe === '1s',
      },
      handleScroll: true,
      handleScale: true,
      width: rsiContainerRef.current.clientWidth,
      height: rsiContainerRef.current.clientHeight,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22ab94',
      downColor: '#f23645',
      borderUpColor: '#22ab94',
      borderDownColor: '#f23645',
      wickUpColor: '#22ab94',
      wickDownColor: '#f23645',
      priceLineColor: '#2962ff',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      color: 'rgba(120, 130, 150, 0.45)',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    });

    const ma20Series = chart.addSeries(LineSeries, {
      color: '#f6c85f',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const ma50Series = chart.addSeries(LineSeries, {
      color: '#7c8cff',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const rsiSeries = rsiChart.addSeries(LineSeries, {
      color: '#d58cff',
      lineWidth: 2,
      priceLineVisible: false,
    });
    rsiSeries.createPriceLine({ price: 70, color: '#f23645', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '70' });
    rsiSeries.createPriceLine({ price: 30, color: '#22ab94', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '30' });

    chartRef.current = chart;
    rsiChartRef.current = rsiChart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    ma20SeriesRef.current = ma20Series;
    ma50SeriesRef.current = ma50Series;
    rsiSeriesRef.current = rsiSeries;

    chart.subscribeCrosshairMove((param) => {
      const candle = param.seriesData.get(candleSeries);
      if (candle) {
        setSelectedCandle(candle);
      }
    });

    const resize = () => {
      if (!containerRef.current || !rsiContainerRef.current) return;
      chart.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });
      rsiChart.applyOptions({
        width: rsiContainerRef.current.clientWidth,
        height: rsiContainerRef.current.clientHeight,
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(containerRef.current);
    observer.observe(rsiContainerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      rsiChart.remove();
      chartRef.current = null;
      rsiChartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      ma20SeriesRef.current = null;
      ma50SeriesRef.current = null;
      rsiSeriesRef.current = null;
    };
  }, [timeframe]);

  useEffect(() => {
    if (!chartRef.current || !rsiChartRef.current || !candleSeriesRef.current || !volumeSeriesRef.current) return;
    candleSeriesRef.current.setData(chartData.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
    ma20SeriesRef.current?.setData(ma20Data);
    ma50SeriesRef.current?.setData(ma50Data);
    rsiSeriesRef.current?.setData(rsiData);
    volumeSeriesRef.current.setData(
      chartData.map(({ time, open, close, volume }) => ({
        time,
        value: volume,
        color: close >= open ? 'rgba(34, 171, 148, 0.35)' : 'rgba(242, 54, 69, 0.35)',
      })),
    );
    const nextKey = `${symbol || ''}:${timeframe || ''}`;
    if (fittedKeyRef.current !== nextKey) {
      chartRef.current.timeScale().fitContent();
      rsiChartRef.current.timeScale().fitContent();
      fittedKeyRef.current = nextKey;
      setSelectedCandle(null);
    }
  }, [chartData, ma20Data, ma50Data, rsiData, symbol, timeframe]);

  return (
    <div className="tvShell">
      <div className="tvHeader">
        <div>
          <strong>{symbol || '-'}</strong>
          <span>{timeframe || '-'}</span>
        </div>
        <div className="tvToolbar">
          {['1s', '1m', '5m', '15m', '30m', '1h', '4h', '1d'].map((item) => (
            <button key={item} className={item === timeframe ? 'active' : ''} onClick={() => onTimeframeChange?.(item)}>{item}</button>
          ))}
        </div>
      </div>
      <div className="tvStats">
        <span>O {formatPrice(latest?.open)}</span>
        <span>H {formatPrice(latest?.high)}</span>
        <span>L {formatPrice(latest?.low)}</span>
        <span>C {formatPrice(latest?.close)}</span>
        <span className={(latest?.close || 0) >= (latest?.open || 0) ? 'up' : 'down'}>
          {changeText(latest)}
        </span>
        <span className="ma20">MA20</span>
        <span className="ma50">MA50</span>
        <span className="rsiLabel">RSI14</span>
      </div>
      <div className="tvChart" ref={containerRef} />
      <div className="tvRsiChart" ref={rsiContainerRef} />
    </div>
  );
}

function movingAverage(data, period) {
  const result = [];
  for (let index = period - 1; index < data.length; index += 1) {
    const window = data.slice(index - period + 1, index + 1);
    const value = window.reduce((sum, candle) => sum + candle.close, 0) / period;
    result.push({ time: data[index].time, value });
  }
  return result;
}

function rsi(data, period) {
  if (data.length <= period) return [];
  const result = [];
  let avgGain = 0;
  let avgLoss = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = data[index].close - data[index - 1].close;
    avgGain += Math.max(change, 0);
    avgLoss += Math.max(-change, 0);
  }
  avgGain /= period;
  avgLoss /= period;
  for (let index = period + 1; index < data.length; index += 1) {
    const change = data[index].close - data[index - 1].close;
    avgGain = (avgGain * (period - 1) + Math.max(change, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-change, 0)) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    result.push({ time: data[index].time, value: 100 - (100 / (1 + rs)) });
  }
  return result;
}

function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 5 });
}

function changeText(candle) {
  if (!candle) return '-';
  const change = candle.close - candle.open;
  const percent = candle.open ? (change / candle.open) * 100 : 0;
  const prefix = change >= 0 ? '+' : '';
  return `${prefix}${formatPrice(change)} (${prefix}${percent.toFixed(2)}%)`;
}
