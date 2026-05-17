// script.js - Complete Technical Analysis Engine
// Final version: keydown, safe data access, mobile helper, reusable search,
// Removed: CMF, Ichimoku, Williams %R, MFI.
// Datalist options now always end with .NS

let chart = null;
let resizeHandlerAttached = false;
let currentAbortController = null;
let searchTimeout = null;

// ---------- HELPER: Mobile View Detection ----------
function isMobileView() {
    return window.innerWidth < 768;
}

// ---------- LOAD NIFTY 500 SYMBOLS (auto-add .NS) ----------
async function loadNiftySymbols() {
    try {
        const response = await fetch('nifty500.json');
        if (!response.ok) throw new Error();
        const symbols = await response.json();
        const datalist = document.getElementById("niftySuggestions");
        datalist.innerHTML = "";
        symbols.forEach(sym => {
            const opt = document.createElement("option");
            // Ensure symbol ends with .NS
            opt.value = sym.endsWith(".NS") ? sym : `${sym}.NS`;
            datalist.appendChild(opt);
        });
    } catch (err) {
        console.warn("Using fallback symbols");
        const fallback = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "WIPRO.NS"];
        const datalist = document.getElementById("niftySuggestions");
        datalist.innerHTML = "";
        fallback.forEach(sym => {
            const opt = document.createElement("option");
            opt.value = sym.endsWith(".NS") ? sym : `${sym}.NS`;
            datalist.appendChild(opt);
        });
    }
}

// ---------- FETCH 1 YEAR DATA (with AbortController & Yahoo error handling) ----------
async function fetchStockData(symbol, signal) {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setFullYear(endDate.getFullYear() - 1);
    const period1 = Math.floor(startDate.getTime() / 1000);
    const period2 = Math.floor(endDate.getTime() / 1000);
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?period1=${period1}&period2=${period2}&interval=1d`;
    const proxyUrl = `https://corsproxy.io/?${encodeURIComponent(url)}`;
    const response = await fetch(proxyUrl, { signal });
    
    if (!response.ok) {
        if (response.status === 429) throw new Error("Rate limit exceeded. Please wait.");
        if (response.status >= 500) throw new Error("Market data server temporarily unavailable.");
        throw new Error(`HTTP ${response.status}`);
    }
    
    const json = await response.json();
    
    if (json.chart?.error) {
        throw new Error(json.chart.error.description || "Yahoo Finance error: Symbol not found or invalid");
    }
    
    if (!json.chart?.result?.length) throw new Error("Symbol not found or no data available");
    
    const result = json.chart.result[0];
    const timestamps = result.timestamp;
    const quotes = result.indicators?.quote?.[0];
    if (!quotes) {
        throw new Error("Invalid market data format from Yahoo Finance");
    }
    
    const data = [];
    for (let i = 0; i < timestamps.length; i++) {
        if (
            quotes.open[i] != null &&
            quotes.high[i] != null &&
            quotes.low[i] != null &&
            quotes.close[i] != null &&
            quotes.volume[i] != null
        ) {
            data.push({
                time: new Date(timestamps[i] * 1000).toISOString().split('T')[0],
                open: quotes.open[i],
                high: quotes.high[i],
                low: quotes.low[i],
                close: quotes.close[i],
                volume: quotes.volume[i]
            });
        }
    }
    if (data.length < 30) throw new Error("Insufficient data (less than 30 trading days)");
    return data;
}

// ---------- SIGNAL HELPERS ----------
function getRSISignal(rsi) { if (rsi > 70) return "SELL"; if (rsi < 30) return "BUY"; return "NEUTRAL"; }
function getMacdSignal(macd, signal) { return macd > signal ? "BUY" : (macd < signal ? "SELL" : "NEUTRAL"); }
function getEMASignal(price, ema) { return price > ema ? "BUY" : (price < ema ? "SELL" : "NEUTRAL"); }
function getBollingerSignal(close, upper, lower) { if (close > upper) return "SELL"; if (close < lower) return "BUY"; return "NEUTRAL"; }
function getStochRSISignal(stochRsi) { if (stochRsi > 80) return "SELL"; if (stochRsi < 20) return "BUY"; return "NEUTRAL"; }
function getCCISignal(cci) { if (cci > 100) return "SELL"; if (cci < -100) return "BUY"; return "NEUTRAL"; }
function getMomentumSignal(momentum) { return momentum > 0 ? "BUY" : (momentum < 0 ? "SELL" : "NEUTRAL"); }
function getOBVSignal(obvValues) { if(obvValues.length<2) return "NEUTRAL"; return obvValues[obvValues.length-1] > obvValues[obvValues.length-2] ? "BUY" : "SELL"; }
function getSuperTrendSignal(superTrend, close) { return close > superTrend ? "BUY" : "SELL"; }

function computeSuperTrend(high, low, close, period = 10, multiplier = 3) {
    const atr = technicalindicators.ATR.calculate({ high, low, close, period });
    if (atr.length < period) return null;
    const lastATR = atr[atr.length-1];
    const hl2 = high.map((h,i) => (h + low[i])/2);
    const basicUpper = hl2.map((v,i) => v + multiplier * (atr[i] || lastATR));
    const basicLower = hl2.map((v,i) => v - multiplier * (atr[i] || lastATR));
    let finalUpper = [], finalLower = [], trend = [];
    for (let i=0; i<close.length; i++) {
        if(i===0) { finalUpper[i]=basicUpper[i]; finalLower[i]=basicLower[i]; trend[i]=1; continue; }
        finalUpper[i] = (basicUpper[i] < finalUpper[i-1] || close[i-1] > finalUpper[i-1]) ? basicUpper[i] : finalUpper[i-1];
        finalLower[i] = (basicLower[i] > finalLower[i-1] || close[i-1] < finalLower[i-1]) ? basicLower[i] : finalLower[i-1];
        if(trend[i-1]===1 && close[i] <= finalLower[i]) trend[i]=-1;
        else if(trend[i-1]===-1 && close[i] >= finalUpper[i]) trend[i]=1;
        else trend[i]=trend[i-1];
    }
    return trend.map((t,i) => t===1 ? finalLower[i] : finalUpper[i]);
}

// ---------- DRAW CHART (memory leak fix + responsive height) ----------
function drawChart(data) {
    if (chart) {
        chart.remove();
        chart = null;
    }
    const container = document.getElementById("chartContainer");
    container.innerHTML = "";
    const chartHeight = isMobileView() ? 320 : 430;
    
    chart = LightweightCharts.createChart(container, {
        layout: { background: { color: '#0a1020' }, textColor: '#cbd5e6' },
        grid: { vertLines: { color: '#1e2a3a' }, horzLines: { color: '#1e2a3a' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#2d3a5e' },
        timeScale: { borderColor: '#2d3a5e', timeVisible: true },
        width: container.clientWidth,
        height: chartHeight
    });
    const candleSeries = chart.addCandlestickSeries({ upColor: '#26a69a', downColor: '#ef5350', borderVisible: false });
    candleSeries.setData(data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })));
    chart.timeScale().fitContent();
    
    if (!resizeHandlerAttached) {
        window.addEventListener('resize', () => {
            if (chart) {
                const newWidth = document.getElementById("chartContainer").clientWidth;
                const newHeight = isMobileView() ? 320 : 430;
                chart.applyOptions({ width: newWidth, height: newHeight });
            } else {
                const container = document.getElementById("chartContainer");
                if (container && container.innerHTML.includes("Enter a symbol")) {
                    container.style.height = `${isMobileView() ? 320 : 430}px`;
                }
            }
        });
        resizeHandlerAttached = true;
    }
}

// ---------- MAIN ANALYSIS ENGINE ----------
async function analyzeStock(symbol) {
    if (currentAbortController) currentAbortController.abort();
    currentAbortController = new AbortController();
    const signal = currentAbortController.signal;

    const loading = document.getElementById("loadingOverlay");
    const searchBtn = document.getElementById("searchBtn");
    loading.classList.remove("hidden");
    searchBtn.disabled = true;

    try {
        const data = await fetchStockData(symbol, signal);
        currentAbortController = null;
        document.getElementById("symbolTitle").innerText = symbol;
        drawChart(data);
        
        const closes = data.map(d => d.close);
        const highs = data.map(d => d.high);
        const lows = data.map(d => d.low);
        const volumes = data.map(d => d.volume);
        const latestClose = closes[closes.length-1];
        
        const ema20 = technicalindicators.EMA.calculate({period:20, values:closes});
        const ema50 = technicalindicators.EMA.calculate({period:50, values:closes});
        const ema100 = technicalindicators.EMA.calculate({period:100, values:closes});
        const ema200 = technicalindicators.EMA.calculate({period:200, values:closes});
        const sma20 = technicalindicators.SMA.calculate({period:20, values:closes});
        const sma50 = technicalindicators.SMA.calculate({period:50, values:closes});
        const sma200 = technicalindicators.SMA.calculate({period:200, values:closes});
        
        const ema20Val = ema20.length ? ema20.pop() : latestClose;
        const ema50Val = ema50.length ? ema50.pop() : latestClose;
        const ema100Val = ema100.length ? ema100.pop() : latestClose;
        const ema200Val = ema200.length ? ema200.pop() : latestClose;
        const sma20Val = sma20.length ? sma20.pop() : latestClose;
        const sma50Val = sma50.length ? sma50.pop() : latestClose;
        const sma200Val = sma200.length ? sma200.pop() : latestClose;
        
        const rsi = technicalindicators.RSI.calculate({values:closes, period:14}).pop();
        const macdOutput = technicalindicators.MACD.calculate({values:closes, fastPeriod:12, slowPeriod:26, signalPeriod:9}).pop();
        const bb = technicalindicators.BollingerBands.calculate({period:20, values:closes, stdDev:2}).pop();
        const atr = technicalindicators.ATR.calculate({high:highs, low:lows, close:closes, period:14}).pop();
        const adxObj = technicalindicators.ADX.calculate({high:highs, low:lows, close:closes, period:14}).pop();
        const stochRSI = technicalindicators.StochasticRSI.calculate({values:closes, rsiPeriod:14, stochasticPeriod:14, kPeriod:3, dPeriod:3}).pop();
        const cci = technicalindicators.CCI.calculate({high:highs, low:lows, close:closes, period:20}).pop();
        const roc = technicalindicators.ROC.calculate({values:closes, period:12}).pop();
        const momentum = technicalindicators.Momentum.calculate({values:closes, period:10}).pop();
        
        let vwapSum = 0, volSum = 0;
        for(let i=0;i<data.length;i++) { 
            const typical = (data[i].high + data[i].low + data[i].close) / 3;
            vwapSum += typical * data[i].volume; 
            volSum += data[i].volume; 
        }
        const vwap = vwapSum/volSum;
        
        const obvValues = technicalindicators.OBV.calculate({close:closes, volume:volumes});
        const obvSignal = getOBVSignal(obvValues);
        
        const superTrendVals = computeSuperTrend(highs, lows, closes, 10, 3);
        const superTrendSignal = superTrendVals ? getSuperTrendSignal(superTrendVals[superTrendVals.length-1], latestClose) : "NEUTRAL";
        const psar = technicalindicators.PSAR.calculate({high:highs, low:lows, step:0.02, maxFactor:0.2}).pop();
        const psarSignal = psar !== undefined ? (latestClose > psar ? "BUY" : "SELL") : "NEUTRAL";
        
        const adxValue = adxObj ? adxObj.adx : null;
        
        const signals = {
            "EMA 20": getEMASignal(latestClose, ema20Val),
            "EMA 50": getEMASignal(latestClose, ema50Val),
            "EMA 100": getEMASignal(latestClose, ema100Val),
            "EMA 200": getEMASignal(latestClose, ema200Val),
            "SMA 20": getEMASignal(latestClose, sma20Val),
            "SMA 50": getEMASignal(latestClose, sma50Val),
            "SMA 200": getEMASignal(latestClose, sma200Val),
            "RSI (14)": rsi !== undefined ? getRSISignal(rsi) : "NEUTRAL",
            "MACD": macdOutput ? getMacdSignal(macdOutput.MACD, macdOutput.signal) : "NEUTRAL",
            "Bollinger Bands": bb ? getBollingerSignal(latestClose, bb.upper, bb.lower) : "NEUTRAL",
            "ATR": atr ? "VOLATILE" : "NEUTRAL",
            "ADX": (adxValue !== null && adxValue > 25) ? "TRENDING" : "NEUTRAL",
            "Stochastic RSI": stochRSI ? getStochRSISignal(stochRSI.stochRSI) : "NEUTRAL",
            "CCI": cci !== undefined ? getCCISignal(cci) : "NEUTRAL",
            "ROC": roc !== undefined ? (roc>0 ? "BUY" : (roc<0 ? "SELL" : "NEUTRAL")) : "NEUTRAL",
            "Momentum": momentum !== undefined ? getMomentumSignal(momentum) : "NEUTRAL",
            "VWAP": vwap ? (latestClose > vwap ? "BUY" : "SELL") : "NEUTRAL",
            "OBV": obvSignal,
            "SuperTrend": superTrendSignal,
            "Parabolic SAR": psarSignal
        };
        
        const trendInds = ["EMA 20","EMA 50","EMA 100","EMA 200","SMA 20","SMA 50","SMA 200","Parabolic SAR","SuperTrend"];
        const momentumInds = ["RSI (14)","MACD","Stochastic RSI","CCI","ROC","Momentum"];
        const volumeInds = ["VWAP","OBV"];
        const volatilityInds = ["Bollinger Bands","ATR","ADX"];
        
        function renderCategory(containerId, indicatorsList) {
            const container = document.getElementById(containerId);
            if (!container) return;
            let html = "";
            for (let ind of indicatorsList) {
                let sig = signals[ind] || "NEUTRAL";
                let sigClass = sig.toLowerCase().replace(/\s+/g, "-");
                html += `<div class="indicator-row"><span class="indicator-name">${ind}</span><span class="signal-badge ${sigClass}">${sig}</span></div>`;
            }
            container.innerHTML = html;
        }
        renderCategory("trendIndicators", trendInds);
        renderCategory("momentumIndicators", momentumInds);
        renderCategory("volumeIndicators", volumeInds);
        renderCategory("volatilityIndicators", volatilityInds);
        
        let buyCount=0, sellCount=0, neutralCount=0;
        Object.values(signals).forEach(s => { 
            if(s==="BUY"||s==="STRONG BUY") buyCount++; 
            else if(s==="SELL"||s==="STRONG SELL") sellCount++; 
            else neutralCount++; 
        });
        let bullishPercent = buyCount/(buyCount+sellCount+0.001)*100;
        let finalRec = "";
        if(buyCount > sellCount+2) finalRec = "STRONG BUY";
        else if(buyCount > sellCount) finalRec = "BUY";
        else if(sellCount > buyCount+2) finalRec = "STRONG SELL";
        else if(sellCount > buyCount) finalRec = "SELL";
        else finalRec = "NEUTRAL";
        document.getElementById("finalRec").innerText = finalRec;
        document.getElementById("bullishPercent").innerText = Math.round(bullishPercent);
        document.getElementById("bullishMeterFill").style.width = bullishPercent+"%";
        document.getElementById("buyCount").innerText = buyCount;
        document.getElementById("sellCount").innerText = sellCount;
        document.getElementById("neutralCount").innerText = neutralCount;
        
        let summary = `Based on ${trendInds.length+ momentumInds.length+ volumeInds.length+ volatilityInds.length} indicators, the overall bias is ${finalRec}. `;
        if(buyCount>sellCount) summary += `Majority of signals (${buyCount} BUY vs ${sellCount} SELL) show bullish momentum. `;
        else if(sellCount>buyCount) summary += `Selling pressure dominates (${sellCount} SELL signals). `;
        else summary += `Mixed signals suggest consolidation. `;
        if(signals["RSI (14)"]==="BUY") summary+= `RSI indicates oversold recovery potential. `;
        if(signals["Bollinger Bands"]==="BUY") summary+= `Price near lower band, possible bounce. `;
        if(signals["ADX"]==="TRENDING") summary+= `Strong trend detected. `;
        document.getElementById("aiSummaryText").innerText = summary;
        
    } catch(err) {
        if (err.name === 'AbortError') return;
        console.error(err);
        let errorMsg = err.message;
        if (errorMsg.includes("Rate limit")) errorMsg = "⏳ Rate limit exceeded. Please wait a moment.";
        else if (errorMsg.includes("unavailable")) errorMsg = "🔧 Market data server is busy. Please try again later.";
        else if (errorMsg.includes("Yahoo Finance error") || errorMsg.includes("Symbol not found")) 
            errorMsg = "❌ Invalid or delisted symbol. Try a different NIFTY 500 stock.";
        document.getElementById("aiSummaryText").innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${errorMsg}`;
        const containers = ["trendIndicators","momentumIndicators","volumeIndicators","volatilityIndicators"];
        containers.forEach(id => { 
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<div class="indicator-row">⚠️ Failed to load data</div>';
        });
    } finally {
        loading.classList.add("hidden");
        searchBtn.disabled = false;
        if (currentAbortController && currentAbortController.signal.aborted) currentAbortController = null;
    }
}

// ---------- REUSABLE SEARCH HANDLER ----------
function handleSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        let sym = document.getElementById("stockInput").value
            .trim()
            .replace(/\s+/g, "")
            .toUpperCase();
        if (!sym) return;
        if (!sym.endsWith(".NS")) sym += ".NS";
        analyzeStock(sym);
    }, 300);
}

// ---------- EVENT LISTENERS ----------
const searchBtn = document.getElementById("searchBtn");
const stockInput = document.getElementById("stockInput");

searchBtn.addEventListener("click", handleSearch);
stockInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        handleSearch();
    }
});

// Initialize: load symbols only, no auto-analysis
loadNiftySymbols();

// Responsive placeholder message
const placeholderContainer = document.getElementById("chartContainer");
if (placeholderContainer) {
    placeholderContainer.style.height = `${isMobileView() ? 320 : 430}px`;
    placeholderContainer.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #8e9bb5; font-size: 0.9rem;"><i class="fas fa-chart-line" style="margin-right: 8px;"></i> Enter a symbol and click Analyze</div>';
}
