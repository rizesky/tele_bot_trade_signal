# Leverage-Based TP/SL System Guide

## Overview

The trading bot features a comprehensive leverage-based TP/SL calculation system that automatically adjusts take profit and stop loss levels based on the maximum available leverage for each trading symbol.

## Key Features

### 🎯 **Dynamic Leverage Detection**
- **Fetches max leverage** from Binance API for each symbol
- **Caches results** to avoid repeated API calls
- **Fallback to MAX_LEVERAGE** config if API fails

### 📊 **Leverage-Based Calculations**
- **Higher leverage** = Tighter TP/SL (faster profit/loss)
- **Lower leverage** = Wider TP/SL (more room for movement)
- **Consistent risk per trade** regardless of leverage

### ⚙️ **Configurable Parameters**
- Base risk percentage (default: 2%)
- Base TP percentage (default: 1%)
- Min/Max SL and TP distances
- Enable/disable the system

## How It Works

### **The Math**
```
SL Distance = Base Risk % / Max Leverage
TP Distance = Base TP % / Max Leverage

Example with 2% base risk:
- 50x leverage → SL at 0.04% (very tight)
- 200x leverage → SL at 0.01% (extremely tight)
```

### **Risk Management**
- **Consistent risk per trade** regardless of leverage
- **Automatic adaptation** to Binance's max leverage per symbol
- **Min/Max constraints** to prevent extreme values

## Configuration

Add these to your `.env` file:

```env
# Leverage-based TP/SL configuration
LEVERAGE_BASED_TP_SL_ENABLED=1
LEVERAGE_BASE_RISK_PERCENT=2.0
LEVERAGE_BASE_TP_PERCENT=1.0
LEVERAGE_MIN_SL_DISTANCE=0.1
LEVERAGE_MAX_SL_DISTANCE=5.0
LEVERAGE_MIN_TP_DISTANCE=0.2
LEVERAGE_MAX_TP_DISTANCE=3.0
```

## Example Results

### **BTCUSDT with 50x leverage:**
- Entry: $50,000
- SL: $49,980 (0.04% away)
- TP1: $50,010 (0.02% away)
- TP2: $50,020 (0.04% away)
- TP3: $50,030 (0.06% away)
- TP4: $50,040 (0.08% away)

### **BTCUSDT with 200x leverage:**
- Entry: $50,000
- SL: $49,990 (0.01% away)
- TP1: $50,005 (0.01% away)
- TP2: $50,010 (0.02% away)
- TP3: $50,015 (0.03% away)
- TP4: $50,020 (0.04% away)

## Testing

Run the test script to see the system in action:

```bash
python test_leverage_system.py
```

## Integration

The system is automatically integrated into your existing trading bot:

1. **Strategy Executor** uses leverage-based calculation when enabled
2. **Risk Manager** fetches max leverage from Binance API
3. **Fallback system** uses default percentages if API fails
4. **Configuration** allows easy enable/disable

## Benefits

### ✅ **Professional Risk Management**
- **Consistent risk per trade** regardless of leverage
- **Automatic adaptation** to market conditions
- **Professional-grade** risk management

### ✅ **Better Performance**
- **Higher leverage** = Faster profit taking
- **Lower leverage** = More room for price movement
- **Optimized** for each symbol's characteristics

### ✅ **Easy Configuration**
- **Simple enable/disable** via config
- **Adjustable parameters** for different strategies
- **Backward compatible** with existing system

## System Requirements

The leverage-based system addresses the following requirements:

- **Gets max leverage** from Binance API for each symbol
- **Calculates TP/SL based on leverage** (tighter for higher leverage)
- **Uses max leverage** instead of current leverage
- **Professional risk management** system

The system operates with the following logic:
- **Higher leverage** = **Tighter TP/SL** = **Faster profit/loss**
- **Lower leverage** = **Wider TP/SL** = **More room for movement**
- **Consistent risk per trade** regardless of leverage used
