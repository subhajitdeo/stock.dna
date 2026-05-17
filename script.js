// Wait for DOM and technicalindicators library before running
document.addEventListener('DOMContentLoaded', () => {
    // Ensure technicalindicators is loaded
    if (typeof technicalindicators === 'undefined') {
        console.error('Technical Indicators library failed to load');
        document.getElementById('aiSummaryText').innerHTML = '⚠️ Library error. Please refresh.';
        return;
    }

    let chart = null;
    let resizeAttached = false;
    let currentAbort = null;
    let searchTimeout = null;

    const isMobile = () => window.innerWidth < 768;

    // Load NIFTY 500 symbols from JSON
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

    // Fetch 1 year daily data from Yahoo via proxy
    async function fetchStockData(symbol, signal) {
        const end = new Date();
        const start = new Date();
        start.setFullYear(end.getFullYear() - 1);
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?period1=${Math.floor(start/1000)}&period2=${Math.floor(end/1000)}&interval=1d`;
        const proxy = `https://corsproxy.io/?${encodeURIComponent(url)}`;
        const resp = await fetch(proxy, { signal });
        if (!resp.ok) {
            if (resp.status === 429) throw new Error('Rate limit exceeded');
            if (resp.status >= 500) throw new Error('Market data server unavailable');
            throw new Error(`HTTP ${resp.status}`);
        }
        const json = await resp.json();
        if (json.chart?.error) throw new Error(json.chart.error.description || 'Yahoo error');
        if (!json.chart?.result?.length) throw new Error('Symbol not found');
        const quotes = json.chart.result[0].indicators?.quote?.[0];
        if (!quotes) throw new Error('Invalid data format');
        const timestamps = json.chart.result[0].timestamp;
        const data = [];
        for (let i = 0; i < timestamps.length; i++) {
            if (quotes.open[i] != null && quotes.high[i] != null && quotes.low[i] != null && quotes.close[i] != null && quotes.volume[i] != null) {
                data.push({
                    time: new Date(timestamps[i]*1000).toISOString().split('T')[0],
                    open: quotes.open[i],
                    high: quotes.high[i],
                    low: quotes.low[i],
                    close: quotes.close[i],
                    volume: quotes.volume[i]
                });
            }
        }
        if (data.length < 30) throw new Error('Insufficient data');
        return data;
    }

    // Draw candlestick chart
    function drawChart(data) {
        if (chart) { chart.remove(); chart = null; }
        const container = document.getElementById('chartContainer');
        container.innerHTML = '';
        const height = isMobile() ? 320 : 430;
        chart = LightweightCharts.createChart(container, {
            layout: { background: { color: '#0a1020' }, textColor: '#cbd5e6' },
            grid: { vertLines: { color: '#1e2a3a' }, horzLines: { color: '#1e2a3a' } },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            rightPriceScale: { borderColor: '#2d3a5e' },
            timeScale: { borderColor: '#2d3a5e', timeVisible: true },
            width: container.clientWidth,
            height: height
        });
        const candleSeries = chart.addCandlestickSeries({ upColor: '#26a69a', downColor: '#ef5350', borderVisible: false });
        candleSeries.setData(data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })));
        chart.timeScale().fitContent();
        if (!resizeAttached) {
            window.addEventListener('resize', () => {
                if (chart) chart.applyOptions({ width: document.getElementById('chartContainer').clientWidth, height: isMobile() ? 320 : 430 });
                else {
                    const c = document.getElementById('chartContainer');
                    if (c && c.innerHTML.includes('Enter')) c.style.height = `${isMobile() ? 320 : 430}px`;
                }
            });
            resizeAttached = true;
        }
    }

    // Indicator helpers
    const getRSI = (r) => r > 70 ? 'SELL' : r < 30 ? 'BUY' : 'NEUTRAL';
    const getMACD = (m,s) => m > s ? 'BUY' : m < s ? 'SELL' : 'NEUTRAL';
    const getEMA = (p,e) => p > e ? 'BUY' : p < e ? 'SELL' : 'NEUTRAL';
    const getBB = (c,u,l) => c > u ? 'SELL' : c < l ? 'BUY' : 'NEUTRAL';
    const getStochRSI = (s) => s > 80 ? 'SELL' : s < 20 ? 'BUY' : 'NEUTRAL';
    const getCCI = (c) => c > 100 ? 'SELL' : c < -100 ? 'BUY' : 'NEUTRAL';
    const getMomentum = (m) => m > 0 ? 'BUY' : m < 0 ? 'SELL' : 'NEUTRAL';
    const getOBV = (o) => o.length<2 ? 'NEUTRAL' : o[o.length-1] > o[o.length-2] ? 'BUY' : 'SELL';
    const getSuperTrend = (st,close) => close > st ? 'BUY' : 'SELL';

    function computeSuperTrend(high, low, close, period=10, mult=3) {
        const atr = technicalindicators.ATR.calculate({ high, low, close, period });
        if (atr.length < period) return null;
        const lastATR = atr[atr.length-1];
        const hl2 = high.map((h,i)=>(h+low[i])/2);
        const basicUpper = hl2.map((v,i)=> v + mult * (atr[i]||lastATR));
        const basicLower = hl2.map((v,i)=> v - mult * (atr[i]||lastATR));
        let finalUpper=[], finalLower=[], trend=[];
        for (let i=0;i<close.length;i++) {
            if(i===0) { finalUpper[i]=basicUpper[i]; finalLower[i]=basicLower[i]; trend[i]=1; continue; }
            finalUpper[i] = (basicUpper[i] < finalUpper[i-1] || close[i-1] > finalUpper[i-1]) ? basicUpper[i] : finalUpper[i-1];
            finalLower[i] = (basicLower[i] > finalLower[i-1] || close[i-1] < finalLower[i-1]) ? basicLower[i] : finalLower[i-1];
            if(trend[i-1]===1 && close[i] <= finalLower[i]) trend[i]=-1;
            else if(trend[i-1]===-1 && close[i] >= finalUpper[i]) trend[i]=1;
            else trend[i]=trend[i-1];
        }
        return trend.map((t,i)=> t===1 ? finalLower[i] : finalUpper[i]);
    }

    // Main analysis
    async function analyzeStock(symbol) {
        if (currentAbort) currentAbort.abort();
        currentAbort = new AbortController();
        const loading = document.getElementById('loadingOverlay');
        const btn = document.getElementById('searchBtn');
        loading.classList.remove('hidden');
        btn.disabled = true;

        try {
            const data = await fetchStockData(symbol, currentAbort.signal);
            currentAbort = null;
            document.getElementById('symbolTitle').innerText = symbol;
            drawChart(data);

            const closes = data.map(d=>d.close);
            const highs = data.map(d=>d.high);
            const lows = data.map(d=>d.low);
            const volumes = data.map(d=>d.volume);
            const latest = closes[closes.length-1];

            // Compute indicators
            const ema20 = technicalindicators.EMA.calculate({period:20, values:closes});
            const ema50 = technicalindicators.EMA.calculate({period:50, values:closes});
            const ema100 = technicalindicators.EMA.calculate({period:100, values:closes});
            const ema200 = technicalindicators.EMA.calculate({period:200, values:closes});
            const sma20 = technicalindicators.SMA.calculate({period:20, values:closes});
            const sma50 = technicalindicators.SMA.calculate({period:50, values:closes});
            const sma200 = technicalindicators.SMA.calculate({period:200, values:closes});

            const ema20v = ema20.length ? ema20.pop() : latest;
            const ema50v = ema50.length ? ema50.pop() : latest;
            const ema100v = ema100.length ? ema100.pop() : latest;
            const ema200v = ema200.length ? ema200.pop() : latest;
            const sma20v = sma20.length ? sma20.pop() : latest;
            const sma50v = sma50.length ? sma50.pop() : latest;
            const sma200v = sma200.length ? sma200.pop() : latest;

            const rsi = technicalindicators.RSI.calculate({values:closes,period:14}).pop();
            const macdOut = technicalindicators.MACD.calculate({values:closes,fastPeriod:12,slowPeriod:26,signalPeriod:9}).pop();
            const bb = technicalindicators.BollingerBands.calculate({period:20,values:closes,stdDev:2}).pop();
            const atr = technicalindicators.ATR.calculate({high:highs,low:lows,close:closes,period:14}).pop();
            const adxObj = technicalindicators.ADX.calculate({high:highs,low:lows,close:closes,period:14}).pop();
            const stochRSI = technicalindicators.StochasticRSI.calculate({values:closes,rsiPeriod:14,stochasticPeriod:14,kPeriod:3,dPeriod:3}).pop();
            const cci = technicalindicators.CCI.calculate({high:highs,low:lows,close:closes,period:20}).pop();
            const roc = technicalindicators.ROC.calculate({values:closes,period:12}).pop();
            const momentum = technicalindicators.Momentum.calculate({values:closes,period:10}).pop();

            let vwapSum=0, volSum=0;
            for(let i=0;i<data.length;i++){ const typical = (data[i].high+data[i].low+data[i].close)/3; vwapSum+=typical*data[i].volume; volSum+=data[i].volume; }
            const vwap = vwapSum/volSum;
            const obvVals = technicalindicators.OBV.calculate({close:closes,volume:volumes});
            const obvSig = getOBV(obvVals);
            const superTrendVals = computeSuperTrend(highs, lows, closes);
            const superSig = superTrendVals ? getSuperTrend(superTrendVals[superTrendVals.length-1], latest) : 'NEUTRAL';
            const psar = technicalindicators.PSAR.calculate({high:highs,low:lows,step:0.02,maxFactor:0.2}).pop();
            const psarSig = psar ? (latest > psar ? 'BUY' : 'SELL') : 'NEUTRAL';
            const adxVal = adxObj ? adxObj.adx : null;

            const signals = {
                'EMA 20': getEMA(latest, ema20v), 'EMA 50': getEMA(latest, ema50v),
                'EMA 100': getEMA(latest, ema100v), 'EMA 200': getEMA(latest, ema200v),
                'SMA 20': getEMA(latest, sma20v), 'SMA 50': getEMA(latest, sma50v),
                'SMA 200': getEMA(latest, sma200v), 'RSI (14)': rsi!==undefined?getRSI(rsi):'NEUTRAL',
                'MACD': macdOut?getMACD(macdOut.MACD, macdOut.signal):'NEUTRAL',
                'Bollinger Bands': bb?getBB(latest, bb.upper, bb.lower):'NEUTRAL',
                'ATR': atr?'VOLATILE':'NEUTRAL', 'ADX': (adxVal && adxVal>25)?'TRENDING':'NEUTRAL',
                'Stochastic RSI': stochRSI?getStochRSI(stochRSI.stochRSI):'NEUTRAL',
                'CCI': cci!==undefined?getCCI(cci):'NEUTRAL',
                'ROC': roc!==undefined?(roc>0?'BUY':roc<0?'SELL':'NEUTRAL'):'NEUTRAL',
                'Momentum': momentum!==undefined?getMomentum(momentum):'NEUTRAL',
                'VWAP': vwap?(latest>vwap?'BUY':'SELL'):'NEUTRAL', 'OBV': obvSig,
                'SuperTrend': superSig, 'Parabolic SAR': psarSig
            };

            const trendList = ['EMA 20','EMA 50','EMA 100','EMA 200','SMA 20','SMA 50','SMA 200','Parabolic SAR','SuperTrend'];
            const momList = ['RSI (14)','MACD','Stochastic RSI','CCI','ROC','Momentum'];
            const volList = ['VWAP','OBV'];
            const volaList = ['Bollinger Bands','ATR','ADX'];

            function renderCategory(id, list) {
                const container = document.getElementById(id);
                if (!container) return;
                let html = '';
                for (let ind of list) {
                    let sig = signals[ind] || 'NEUTRAL';
                    let cls = sig.toLowerCase().replace(/\s+/g,'-');
                    html += `<div class="indicator-row"><span class="indicator-name">${ind}</span><span class="signal-badge ${cls}">${sig}</span></div>`;
                }
                container.innerHTML = html;
            }
            renderCategory('trendIndicators', trendList);
            renderCategory('momentumIndicators', momList);
            renderCategory('volumeIndicators', volList);
            renderCategory('volatilityIndicators', volaList);

            let buy=0,sell=0,neu=0;
            Object.values(signals).forEach(s=>{
                if(s==='BUY'||s==='STRONG BUY') buy++;
                else if(s==='SELL'||s==='STRONG SELL') sell++;
                else neu++;
            });
            let bullPer = buy/(buy+sell+0.001)*100;
            let finalRec = buy>sell+2 ? 'STRONG BUY' : buy>sell ? 'BUY' : sell>buy+2 ? 'STRONG SELL' : sell>buy ? 'SELL' : 'NEUTRAL';
            document.getElementById('finalRec').innerText = finalRec;
            document.getElementById('bullishPercent').innerText = Math.round(bullPer);
            document.getElementById('bullishMeterFill').style.width = bullPer+'%';
            document.getElementById('buyCount').innerText = buy;
            document.getElementById('sellCount').innerText = sell;
            document.getElementById('neutralCount').innerText = neu;

            let summary = `Based on ${trendList.length+momList.length+volList.length+volaList.length} indicators, bias is ${finalRec}. `;
            if(buy>sell) summary += `${buy} BUY vs ${sell} SELL shows bullish momentum. `;
            else if(sell>buy) summary += `${sell} SELL signals dominate. `;
            else summary += `Mixed signals suggest consolidation. `;
            if(signals['RSI (14)']==='BUY') summary+= 'RSI oversold recovery potential. ';
            if(signals['Bollinger Bands']==='BUY') summary+= 'Price near lower band. ';
            if(signals['ADX']==='TRENDING') summary+= 'Strong trend detected. ';
            document.getElementById('aiSummaryText').innerText = summary;
        } catch(err) {
            if(err.name==='AbortError') return;
            let msg = err.message;
            if(msg.includes('Rate limit')) msg='⏳ Rate limit exceeded. Please wait.';
            else if(msg.includes('unavailable')) msg='🔧 Market data server busy. Try later.';
            else if(msg.includes('Symbol not found')) msg='❌ Invalid symbol. Try another NIFTY 500 stock.';
            else msg = `⚠️ ${msg}`;
            document.getElementById('aiSummaryText').innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${msg}`;
            ['trendIndicators','momentumIndicators','volumeIndicators','volatilityIndicators'].forEach(id=>{
                const el = document.getElementById(id);
                if(el) el.innerHTML = '<div class="indicator-row">⚠️ Failed to load</div>';
            });
        } finally {
            loading.classList.add('hidden');
            document.getElementById('searchBtn').disabled = false;
            if(currentAbort && currentAbort.signal.aborted) currentAbort = null;
        }
    }

    // Handle search with debounce
    function handleSearch() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            let sym = document.getElementById('stockInput').value.trim().replace(/\s+/g, '').toUpperCase();
            if (!sym) return;
            if (!sym.endsWith('.NS')) sym += '.NS';
            analyzeStock(sym);
        }, 300);
    }

    // Attach event listeners
    document.getElementById('searchBtn').addEventListener('click', handleSearch);
    document.getElementById('stockInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); handleSearch(); }
    });

    // Initialise
    loadSymbols();
    const placeholder = document.getElementById('chartContainer');
    if (placeholder) {
        placeholder.style.height = `${isMobile() ? 320 : 430}px`;
        placeholder.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8e9bb5;"><i class="fas fa-chart-line" style="margin-right:6px;"></i> Enter symbol & click Analyze</div>';
    }
});
