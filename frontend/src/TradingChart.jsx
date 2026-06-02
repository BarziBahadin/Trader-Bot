import React, { useEffect, useMemo, useRef } from 'react';
import { CandlestickSeries, ColorType, createChart, HistogramSeries } from 'lightweight-charts';

function toUnixTime(value) {
  const parsed = Date.parse(value);
  if (!Number.isNaN(parsed)) {
    return Math.floor(parsed / 1000);
  }
  return Math.floor(Number(value) / 1000);
}

export default function TradingChart({ candles, symbol, timeframe }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);

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

  useEffect(() => {
    if (!containerRef.current) return undefined;

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
        secondsVisible: false,
        rightOffset: 8,
        barSpacing: 9,
      },
      handleScroll: true,
      handleScale: true,
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
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

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const resize = () => {
      if (!containerRef.current) return;
      chart.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current || !volumeSeriesRef.current) return;
    candleSeriesRef.current.setData(chartData.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
    volumeSeriesRef.current.setData(
      chartData.map(({ time, open, close, volume }) => ({
        time,
        value: volume,
        color: close >= open ? 'rgba(34, 171, 148, 0.35)' : 'rgba(242, 54, 69, 0.35)',
      })),
    );
    chartRef.current.timeScale().fitContent();
  }, [chartData]);

  return (
    <div className="tvShell">
      <div className="tvHeader">
        <div>
          <strong>{symbol || '-'}</strong>
          <span>{timeframe || '-'}</span>
        </div>
        <div className="tvBadge">Candles</div>
      </div>
      <div className="tvChart" ref={containerRef} />
    </div>
  );
}
