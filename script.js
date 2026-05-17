document.addEventListener('DOMContentLoaded', () => {
    let chart = null;
    let resizeAttached = false;
    let searchTimeout = null;

    const isMobile = () => window.innerWidth < 768;

    async function loadSymbols() {
        try {
            const res = await fetch('nifty500.json');
            if (!res.ok) throw new Error();
            const symbols = await res.json();
            const datalist = document.getElementById('niftySuggestions');
            datalist.innerHTML = '';
            symbols.forEach(sym => {
                const opt = document.createElement('option');
                opt.value = sym.endsWith('.NS') ? sym : `${sym}.NS`;
                datalist.appendChild(opt);
            });
        } catch {
            const fallback = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'WIPRO.NS'];
            const datalist = document.getElementById('niftySuggestions');
            datalist.innerHTML = '';
            fallback.forEach(sym => {
                const opt = document.createElement('option');
                opt.value = sym.endsWith('.NS') ? sym : `${sym}.NS`;
                datalist.appendChild(opt);
            });
        }
    }

    async function fetchStockData(symbol) {
        const url = `/data/processed/${symbol}`;
        const res = await fetch(url);
        if (!res.ok) {
            throw new Error(`No data for ${symbol}. Try: 360ONE.NS, AWL.NS`);
        }
        const data = await res.json();
        if (!data || !data.candles) throw new Error('Invalid data format');
        return data;
    }

    function drawChart(candles) {
        if (chart) { chart.remove(); chart = null; }
        const container = document.getElementById('chartContainer');
        container.innerHTML = '';
        const height = isMobile() ? 320 : 430;
        chart = LightweightCharts.createChart(container, {
            layout: { background: { color: '#0a1020' }, textColor: '#cbd5e6' },
            grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
            timeScale: { timeVisible: true },
            width: container.clientWidth,
            height: height
        });
        const candleSeries = chart.addCandlestickSeries({ upColor: '#22c55e', downColor: '#ef4444', borderVisible: false });
        candleSeries.setData(candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })));
        chart.timeScale().fitContent();
        if (!resizeAttached) {
            window.addEventListener('resize', () => {
                if (chart) chart.applyOptions({ width: container.clientWidth });
            });
            resizeAttached = true;
        }
    }

    function getSignalClass(signal) {
        const s = (signal || 'NEUTRAL').toUpperCase();
        if (s === 'BUY' || s === 'STRONG BUY') return 'buy';
        if (s === 'SELL' || s === 'STRONG SELL') return 'sell';
        return 'neutral';
    }

    function updateOdometer(buyCount, sellCount, total) {
        const buyPercent = total > 0 ? (buyCount / total) * 100 : 0;
        const sellPercent = total > 0 ? (sellCount / total) * 100 : 0;
        const netScore = buyCount - sellCount;
        const maxScore = total;
        const netPercent = maxScore > 0 ? ((netScore + maxScore) / (maxScore * 2)) * 100 : 50;

        // Animate odometer digits
        const buyOdo = document.getElementById('buyOdometer');
        const sellOdo = document.getElementById('sellOdometer');
        const netOdo = document.getElementById('netScoreOdometer');
        const buyFill = document.getElementById('buyFill');
        const sellFill = document.getElementById('sellFill');
        const netFill = document.getElementById('netFill');

        // Counting animation
        let currentBuy = 0;
        let currentSell = 0;
        let currentNet = 0;
        const targetBuy = Math.round(buyPercent);
        const targetSell = Math.round(sellPercent);
        const targetNet = netScore;

        const interval = setInterval(() => {
            if (currentBuy < targetBuy) { currentBuy++; buyOdo.innerText = currentBuy; }
            if (currentSell < targetSell) { currentSell++; sellOdo.innerText = currentSell; }
            if (currentNet < targetNet && targetNet > 0) { currentNet++; netOdo.innerText = currentNet; }
            else if (currentNet > targetNet && targetNet < 0) { currentNet--; netOdo.innerText = currentNet; }
            else if (currentNet === targetNet && currentBuy === targetBuy && currentSell === targetSell) {
                clearInterval(interval);
            }
        }, 10);

        buyFill.style.width = buyPercent + '%';
        sellFill.style.width = sellPercent + '%';
        netFill.style.width = netPercent + '%';

        document.getElementById('buyCountOdo').innerText = buyCount;
        document.getElementById('sellCountOdo').innerText = sellCount;
    }

    async function analyzeStock(symbol) {
        const loading = document.getElementById('loadingOverlay');
        const btn = document.getElementById('searchBtn');
        loading.classList.remove('hidden');
        btn.disabled = true;

        try {
            const data = await fetchStockData(symbol);
            document.getElementById('symbolTitle').innerText = symbol;
            drawChart(data.candles);

            const ind = data.indicators;
            
            // Render Trend Indicators
            const trendList = ['EMA20', 'EMA50', 'EMA100', 'EMA200', 'SMA20', 'SMA50', 'SMA200', 'SuperTrend', 'Ichimoku', 'Parabolic_SAR'];
            document.getElementById('trendIndicators').innerHTML = trendList.map(indName => {
                const indicator = ind[indName];
                const signal = indicator?.signal || 'NEUTRAL';
                const value = indicator?.value ? `(${indicator.value})` : '';
                return `<div class="indicator-row"><span class="indicator-name">${indName}</span><span class="signal-badge ${getSignalClass(signal)}">${signal} ${value}</span></div>`;
            }).join('');

            // Render Momentum Indicators
            const momentumList = ['RSI', 'StochasticRSI', 'MACD', 'CCI', 'Williams_R', 'ROC', 'Momentum', 'MFI', 'Ultimate_Oscillator'];
            document.getElementById('momentumIndicators').innerHTML = momentumList.map(indName => {
                const indicator = ind[indName];
                const signal = indicator?.signal || 'NEUTRAL';
                const value = indicator?.value ? `(${indicator.value})` : '';
                return `<div class="indicator-row"><span class="indicator-name">${indName}</span><span class="signal-badge ${getSignalClass(signal)}">${signal} ${value}</span></div>`;
            }).join('');

            // Render Volume Indicators
            const volumeList = ['OBV', 'CMF', 'VWAP'];
            document.getElementById('volumeIndicators').innerHTML = volumeList.map(indName => {
                const indicator = ind[indName];
                const signal = indicator?.signal || 'NEUTRAL';
                const value = indicator?.value ? `(${indicator.value})` : '';
                return `<div class="indicator-row"><span class="indicator-name">${indName}</span><span class="signal-badge ${getSignalClass(signal)}">${signal} ${value}</span></div>`;
            }).join('');

            // Render Volatility Indicators
            const volatilityList = ['BollingerBands', 'ATR', 'KeltnerChannel', 'StandardDeviation'];
            document.getElementById('volatilityIndicators').innerHTML = volatilityList.map(indName => {
                const indicator = ind[indName];
                let signal = indicator?.signal || 'NEUTRAL';
                let value = '';
                if (indName === 'ATR') value = indicator?.value ? `(${indicator.value})` : '';
                else if (indName === 'StandardDeviation') value = indicator?.value ? `(${indicator.value})` : '';
                else if (indName === 'BollingerBands') signal = indicator?.signal || 'NEUTRAL';
                return `<div class="indicator-row"><span class="indicator-name">${indName}</span><span class="signal-badge ${getSignalClass(signal)}">${signal} ${value}</span></div>`;
            }).join('');

            // Count signals
            const allSignals = [
                ind.EMA20?.signal, ind.EMA50?.signal, ind.EMA100?.signal, ind.EMA200?.signal,
                ind.SMA20?.signal, ind.SMA50?.signal, ind.SMA200?.signal,
                ind.SuperTrend?.signal, ind.Ichimoku?.signal, ind.Parabolic_SAR?.signal,
                ind.RSI?.signal, ind.StochasticRSI?.signal, ind.MACD?.signal,
                ind.CCI?.signal, ind.Williams_R?.signal, ind.ROC?.signal,
                ind.Momentum?.signal, ind.MFI?.signal, ind.Ultimate_Oscillator?.signal,
                ind.OBV?.signal, ind.CMF?.signal, ind.VWAP?.signal,
                ind.BollingerBands?.signal
            ];

            let buy = allSignals.filter(s => s === 'BUY').length;
            let sell = allSignals.filter(s => s === 'SELL').length;
            let neutral = allSignals.filter(s => s === 'NEUTRAL' || !s).length;
            let total = buy + sell + neutral;

            document.getElementById('buyCount').innerText = buy;
            document.getElementById('sellCount').innerText = sell;
            document.getElementById('neutralCount').innerText = neutral;

            // Update Odometer
            updateOdometer(buy, sell, total);

            let bullishPercent = total > 0 ? (buy / total) * 100 : 0;
            let finalRec = buy > sell + 2 ? 'STRONG BUY' : buy > sell ? 'BUY' : sell > buy + 2 ? 'STRONG SELL' : sell > buy ? 'SELL' : 'NEUTRAL';
            document.getElementById('finalRec').innerText = finalRec;
            document.getElementById('bullishPercent').innerText = Math.round(bullishPercent);
            document.getElementById('bullishMeterFill').style.width = bullishPercent + '%';

            let summary = `Based on ${total} indicators, bias is ${finalRec}. `;
            if (buy > sell) summary += `${buy} BUY vs ${sell} SELL shows bullish momentum. `;
            else if (sell > buy) summary += `${sell} SELL signals dominate. `;
            else summary += `Mixed signals suggest consolidation. `;
            document.getElementById('aiSummaryText').innerText = summary;

        } catch (err) {
            document.getElementById('aiSummaryText').innerHTML = `❌ ${err.message}`;
        } finally {
            loading.classList.add('hidden');
            btn.disabled = false;
        }
    }

    function handleSearch() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            let sym = document.getElementById('stockInput').value.trim().replace(/\s+/g, '').toUpperCase();
            if (!sym) return;
            if (!sym.endsWith('.NS')) sym += '.NS';
            analyzeStock(sym);
        }, 300);
    }

    document.getElementById('searchBtn').addEventListener('click', handleSearch);
    document.getElementById('stockInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); handleSearch(); }
    });

    loadSymbols();
    const placeholder = document.getElementById('chartContainer');
    if (placeholder) {
        placeholder.style.height = `${isMobile() ? 320 : 430}px`;
        placeholder.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8e9bb5;"><i class="fas fa-chart-line" style="margin-right:6px;"></i> Enter symbol & click Analyze</div>';
    }
});
