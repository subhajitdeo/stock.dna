def ichimoku(
    high: np.ndarray, low: np.ndarray, close: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Full Ichimoku components: Tenkan, Kijun, Senkou A, Senkou B, Chikou.
    All returned arrays same length as input.
    """
    n = len(high)
    tenkan = np.full(n, np.nan)
    kijun = np.full(n, np.nan)
    senkou_a = np.full(n, np.nan)
    senkou_b = np.full(n, np.nan)
    chikou = np.full(n, np.nan)

    if n < 52:
        return tenkan, kijun, senkou_a, senkou_b, chikou

    for i in range(9, n):
        tenkan[i] = (np.max(high[i - 9 : i + 1]) + np.min(low[i - 9 : i + 1])) / 2
    for i in range(26, n):
        kijun[i] = (np.max(high[i - 26 : i + 1]) + np.min(low[i - 26 : i + 1])) / 2

    # Senkou A = (Tenkan + Kijun) / 2 plotted 26 periods ahead
    for i in range(26, n - 26):
        if np.isfinite(tenkan[i]) and np.isfinite(kijun[i]):
            senkou_a[i + 26] = (tenkan[i] + kijun[i]) / 2

    # Senkou B = (highest high + lowest low)/2 over 52 periods, plotted 26 ahead
    for i in range(52, n - 26):
        senkou_b[i + 26] = (
            np.max(high[i - 52 : i + 1]) + np.min(low[i - 52 : i + 1])
        ) / 2

    # Chikou = close plotted 26 periods back
    if n > 26:
        chikou[26:] = close[:-26]          # ← now 'close' is defined
    return tenkan, kijun, senkou_a, senkou_b, chikou
