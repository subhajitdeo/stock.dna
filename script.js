// script.js - Complete Technical Analysis Engine (No Backend, GitHub Pages Ready)

// ---------- GLOBALS ----------
let chart = null;
let currentData = null;      // store {time, open, high, low, close, volume}
let currentSymbol = "RELIANCE.NS";

// NIFTY 500 sample symbols (major + .NS suffix for NSE)
const niftySymbols = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "HINDUNILVR.NS", "AXISBANK.NS",
    "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "WIPRO.NS", "NTPC.NS",
    "ONGC.NS", "POWERGRID.NS", "M&M.NS", "ULTRACEMCO.NS", "NESTLEIND.NS", "ASIANPAINT.NS",
    "HCLTECH.NS", "BAJAJFINSV.NS", "ADANIPORTS.NS", "ADANIENT.NS", "DMART.NS", "TECHM.NS"
];

// Helper: populate datalist
function populateAutocomplete() {
    const datalist = document.getElementById("niftySuggestions");
    datalist.innerHTML = "";
    niftySymbols.forEach(sym => {
        const opt = document.createElement("option");
        opt.value = sym;
        datalist.appendChild(opt);
    });
}

// ---------- FETCH STOCK DATA (6 months daily, via Yahoo + CORS proxy) ----------
async function fetchStockData(symbol) {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(endDate.getMonth() - 6);
    const period1 = Math.floor(startDate.getTime() / 1000);
    const period2 = Math.floor(endDate.getTime() / 1000);
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?period1=${period1}&period2=${period2}&interval=1d`;
    // Using allorigins CORS proxy (free & reliable)
    const proxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`;
    const response = await fetch(proxyUrl);
    if (!response.ok) throw new Error("Network error");
    const json = await response.json();
    if (!json.chart || !json.chart.result || json.chart.result.length === 0) throw new Error("Symbol not found");
    const result = json.chart.result[0];
    const timestamps = result.timestamp;
    const quotes = result.indicators.quote[0];
    const adjclose = result.indicators.adjclose?.[0]?.adjclose || quotes.close;
    const data = [];
    for (let i = 0; i < timestamps.length; i++) {
        if (quotes.open[i] && quotes.high[i] && quotes.low[i] && quotes.close[i] && quotes.volume[i]) {
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
    if (data.length < 30) throw new Error("Insufficient data");
    return data;
}

// ---------- INDICATOR SIGNAL HELPERS (Latest value only) ----------
function getRSISignal(rsi) { if (rsi > 70) return "SELL"; if (rsi < 30) return "BUY"; return "NEUTRAL"; }
function getMacdSignal(macd, signal) { if (macd > signal) return "BUY"; if (macd < signal) return "SELL"; return "NEUTRAL"; }
function getEMASignal(price, ema) { return price > ema ? "BUY" : (price < ema ? "SELL" : "NEUTRAL"); }
function getBollingerSignal(close, upper, lower) { if (close > upper) return "SELL"; if (close < lower) return "BUY"; return "NEUTRAL"; }
function getStochRSISignal(stochRsi) { if (stochRsi > 80) return "SELL"; if (stochRsi < 20) return "BUY"; return "NEUTRAL"; }
function getCCISignal(cci) { if (cci > 100) return "SELL"; if (cci < -100) return "BUY"; return "NEUTRAL"; }
function getMomentumSignal(momentum) { return momentum > 0 ? "BUY" : (momentum < 0 ? "SELL" : "NEUTRAL"); }
function getWilliamsSignal(williams) { if (williams > -20) return "SELL"; if (williams < -80) return "BUY"; return "NEUTRAL"; }
function getMFISignal(mfi) { if (mfi > 80) return "SELL"; if (mfi < 20) return "BUY"; return "NEUTRAL"; }
function getADXSignal(adx) { return adx > 25 ? "STRONG TREND" : "NEUTRAL"; } // but for directional we treat as NEUTRAL, but we embed it.
function getSuperTrendSignal(superTrend, close) { return close > superTrend ? "BUY" : "SELL"; }

// manual SuperTrend calculation
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

// Ichimoku signal: latest price vs Senkou Span A
function getIchimokuSignal(price, senkouA) { return price > senkouA ? "BUY" : "SELL"; }

// OBV signal: compare OBV trend (simple compare last two)
function getOBVSignal(obvValues) { if(obvValues.length<2) return "NEUTRAL"; return obvValues[obvValues.length-1] > obvValues[obvValues.length-2] ? "BUY" : "SELL"; }
// CMF (Chaikin Money Flow) >0 bullish
function getCMFSignal(cmf) { return cmf > 0 ? "BUY" : (cmf < 0 ? "SELL" : "NEUTRAL"); }

// ---------- MAIN ANALYSIS ENGINE ----------
async function analyzeStock(symbol) {
    const loading = document.getElementById("loadingOverlay");
    loading.classList.remove("hidden");
    try {
        const data = await fetchStockData(symbol);
        currentData = data;
        document.getElementById("symbolTitle").innerText = symbol;
        drawChart(data);
        
        const closes = data.map(d => d.close);
        const highs = data.map(d => d.high);
        const lows = data.map(d => d.low);
        const volumes = data.map(d => d.volume);
        const latestClose = closes[closes.length-1];
        
        // Precomputations
        const ema20 = technicalindicators.EMA.calculate({period:20, values:closes});
        const ema50 = technicalindicators.EMA.calculate({period:50, values:closes});
        const ema100 = technicalindicators.EMA.calculate({period:100, values:closes});
        const ema200 = technicalindicators.EMA.calculate({period:200, values:closes});
        const sma20 = technicalindicators.SMA.calculate({period:20, values:closes});
        const sma50 = technicalindicators.SMA.calculate({period:50, values:closes});
        const sma200 = technicalindicators.SMA.calculate({period:200, values:closes});
        const rsi = technicalindicators.RSI.calculate({values:closes, period:14}).pop();
        const macdOutput = technicalindicators.MACD.calculate({values:closes, fastPeriod:12, slowPeriod:26, signalPeriod:9}).pop();
        const bb = technicalindicators.BollingerBands.calculate({period:20, values:closes, stdDev:2}).pop();
        const atr = technicalindicators.ATR.calculate({high:highs, low:lows, close:closes, period:14}).pop();
        const adx = technicalindicators.ADX.calculate({high:highs, low:lows, close:closes, period:14}).pop();
        // Stochastic RSI
        const stochRSI = technicalindicators.StochasticRSI.calculate({values:closes, rsiPeriod:14, stochasticPeriod:14, kPeriod:3, dPeriod:3}).pop();
        const cci = technicalindicators.CCI.calculate({high:highs, low:lows, close:closes, period:20}).pop();
        const roc = technicalindicators.ROC.calculate({values:closes, period:12}).pop();
        const momentum = technicalindicators.Momentum.calculate({values:closes, period:10}).pop();
        // VWAP (approx daily)
        let vwapSum = 0, volSum = 0;
        for(let i=0;i<data.length;i++) { vwapSum += (data[i].high+data[i].low+data[i].close)/3 * data[i].volume; volSum += data[i].volume; }
        const vwap = vwapSum/volSum;
        const obv = technicalindicators.OBV.calculate({close:closes, volume:volumes}).pop();
        const obvValues = technicalindicators.OBV.calculate({close:closes, volume:volumes});
        const mfi = technicalindicators.MFI.calculate({high:highs, low:lows, close:closes, volume:volumes, period:14}).pop();
        const williamsR = technicalindicators.WilliamsR.calculate({high:highs, low:lows, close:closes, period:14}).pop();
        // CMF (20 period)
        let mfm = [], mfv = [];
        for(let i=0;i<data.length;i++) { let m = ((data[i].close - data[i].low) - (data[i].high - data[i].close)) / (data[i].high - data[i].low); mfm.push(m); mfv.push(m * data[i].volume); }
        let cmf = mfv.slice(-20).reduce((a,b)=>a+b,0) / volumes.slice(-20).reduce((a,b)=>a+b,0);
        const superTrendVals = computeSuperTrend(highs, lows, closes, 10, 3);
        const superTrendSignal = superTrendVals ? getSuperTrendSignal(superTrendVals[superTrendVals.length-1], latestClose) : "NEUTRAL";
        // Ichimoku: simplified Senkou Span A (26 periods)
        const conversion = technicalindicators.IchimokuCloud.calculate({high:highs, low:lows, conversionPeriod:9, basePeriod:26, spanPeriod:52, displacement:26});
        const ichiSignal = conversion.length ? getIchimokuSignal(latestClose, conversion[conversion.length-1].senkouSpanA) : "NEUTRAL";
        const psar = technicalindicators.PSAR.calculate({high:highs, low:lows, step:0.02, maxFactor:0.2}).pop();
        const psarSignal = psar !== undefined ? (latestClose > psar ? "BUY" : "SELL") : "NEUTRAL";
        
        // Assemble signals dictionary
        const signals = {
            "EMA 20": getEMASignal(latestClose, ema20.pop()), "EMA 50": getEMASignal(latestClose, ema50.pop()),
            "EMA 100": getEMASignal(latestClose, ema100.pop()), "EMA 200": getEMASignal(latestClose, ema200.pop()),
            "SMA 20": getEMASignal(latestClose, sma20.pop()), "SMA 50": getEMASignal(latestClose, sma50.pop()),
            "SMA 200": getEMASignal(latestClose, sma200.pop()), "RSI (14)": getRSISignal(rsi),
            "MACD": getMacdSignal(macdOutput.MACD, macdOutput.signal), "Bollinger Bands": getBollingerSignal(latestClose, bb.upper, bb.lower),
            "ATR": (atr ? "VOLATILE" : "NEUTRAL"), "ADX": adx>25 ? "TRENDING" : "NEUTRAL",
            "Stochastic RSI": getStochRSISignal(stochRSI ? stochRSI.stochRSI : 50), "CCI": getCCISignal(cci),
            "ROC": roc>0 ? "BUY" : (roc<0 ? "SELL" : "NEUTRAL"), "Momentum": getMomentumSignal(momentum),
            "VWAP": latestClose > vwap ? "BUY" : "SELL", "OBV": getOBVSignal(obvValues),
            "MFI": getMFISignal(mfi), "Williams %R": getWilliamsSignal(williamsR), "CMF": getCMFSignal(cmf),
            "SuperTrend": superTrendSignal, "Ichimoku": ichiSignal, "Parabolic SAR": psarSignal
        };
        
        // Categorize
        const trendInds = ["EMA 20","EMA 50","EMA 100","EMA 200","SMA 20","SMA 50","SMA 200","Ichimoku","Parabolic SAR","SuperTrend"];
        const momentumInds = ["RSI (14)","MACD","Stochastic RSI","CCI","ROC","Momentum","Williams %R"];
        const volumeInds = ["VWAP","OBV","MFI","CMF"];
        const volatilityInds = ["Bollinger Bands","ATR","ADX"];
        
        function renderCategory(containerId, indicatorsList) {
            const container = document.getElementById(containerId);
            container.innerHTML = "";
            for(let ind of indicatorsList) {
                let sig = signals[ind] || "NEUTRAL";
                let sigClass = sig.toLowerCase().replace(" ", "-");
                container.innerHTML += `<div class="indicator-row"><span class="indicator-name">${ind}</span><span class="signal-badge ${sigClass}">${sig}</span></div>`;
            }
        }
        renderCategory("trendIndicators", trendInds);
        renderCategory("momentumIndicators", momentumInds);
        renderCategory("volumeIndicators", volumeInds);
        renderCategory("volatilityIndicators", volatilityInds);
        
        // Overall stats
        let buyCount=0, sellCount=0, neutralCount=0;
        const allSignals = Object.values(signals);
        allSignals.forEach(s => { if(s==="BUY"||s==="STRONG BUY") buyCount++; else if(s==="SELL"||s==="STRONG SELL") sellCount++; else neutralCount++; });
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
        
        // AI Summary
        let summary = `Based on ${trendInds.length+ momentumInds.length+ volumeInds.length+ volatilityInds.length} indicators, the overall bias is ${finalRec}. `;
        if(buyCount>sellCount) summary += `Majority of signals (${buyCount} BUY vs ${sellCount} SELL) show bullish momentum. `;
        else if(sellCount>buyCount) summary += `Selling pressure dominates (${sellCount} SELL signals). `;
        else summary += `Mixed signals suggest consolidation. `;
        if(signals["RSI (14)"]==="BUY") summary+= `RSI indicates oversold recovery potential. `;
        if(signals["Bollinger Bands"]==="BUY") summary+= `Price near lower band, possible bounce. `;
        if(signals["ADX"]==="TRENDING") summary+= `Strong trend detected. `;
        document.getElementById("aiSummaryText").innerText = summary;
        
    } catch(err) {
        document.getElementById("aiSummaryText").innerText = `Error: ${err.message}. Try another symbol (e.g., TCS.NS)`;
        console.error(err);
    } finally {
        loading.classList.add("hidden");
    }
}

// Draw Lightweight Chart (price only)
function drawChart(data) {
    if(chart) document.getElementById("chartContainer").innerHTML = "";
    chart = LightweightCharts.createChart(document.getElementById("chartContainer"), {
        layout: { background: { color: '#0a1020' }, textColor: '#cbd5e6' },
        grid: { vertLines: { color: '#1e2a3a' }, horzLines: { color: '#1e2a3a' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#2d3a5e' },
        timeScale: { borderColor: '#2d3a5e', timeVisible: true },
        width: document.getElementById("chartContainer").clientWidth,
        height: 430
    });
    const candleSeries = chart.addCandlestickSeries({ upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350' });
    const formatted = data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close }));
    candleSeries.setData(formatted);
    chart.timeScale().fitContent();
    window.addEventListener('resize', () => { chart.applyOptions({ width: document.getElementById("chartContainer").clientWidth }); });
}

// Event listeners & initial load
document.getElementById("searchBtn").addEventListener("click", () => {
    let sym = document.getElementById("stockInput").value.trim().toUpperCase();
    if(!sym.includes(".NS")) sym += ".NS";
    if(!niftySymbols.includes(sym)) sym = sym; // allow custom
    currentSymbol = sym;
    analyzeStock(currentSymbol);
});
document.getElementById("stockInput").addEventListener("keypress", (e) => { if(e.key === "Enter") document.getElementById("searchBtn").click(); });
populateAutocomplete();
analyzeStock("RELIANCE.NS");
