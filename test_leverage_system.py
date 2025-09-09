#!/usr/bin/env python3
"""
Test script for the leverage-based TP/SL system.

This script demonstrates how the new leverage-based system calculates
TP/SL levels based on the maximum available leverage for each symbol.
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from risk_manager import RiskManager
from binance_future_client import BinanceFuturesClient
import config

def test_leverage_calculation():
    """Test the leverage-based TP/SL calculation system."""
    
    print("🧪 Testing Leverage-Based TP/SL System")
    print("=" * 50)
    
    # Initialize the system (you'll need valid API keys for this to work)
    try:
        if not config.BINANCE_API_KEY or not config.BINANCE_API_SECRET:
            print("❌ Binance API keys not found. Please set BINANCE_API_KEY and BINANCE_API_SECRET in your .env file")
            return
        
        binance_client = BinanceFuturesClient(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
        risk_manager = RiskManager(binance_client)
        
        # Test symbols
        test_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        test_price = 50000.0  # Example BTC price
        
        print(f"Testing with entry price: ${test_price:,.2f}")
        print()
        
        for symbol in test_symbols:
            print(f"📊 {symbol}:")
            
            # Get max leverage
            max_leverage = risk_manager.get_max_leverage_for_symbol(symbol)
            print(f"   Max Leverage: {max_leverage}x")
            
            # Test BUY signal
            tp_list, sl, risk_info = risk_manager.calculate_leverage_based_tp_sl(
                symbol, test_price, "BUY"
            )
            
            print(f"   BUY Signal:")
            print(f"   ├─ Entry: ${test_price:,.2f}")
            print(f"   ├─ SL: ${sl:,.2f} ({risk_info['sl_distance_percent']:.2f}%)")
            print(f"   ├─ TP1: ${tp_list[0]:,.2f} ({risk_info['tp_distance_percent']:.2f}%)")
            print(f"   ├─ TP2: ${tp_list[1]:,.2f} ({risk_info['tp_distance_percent']*2:.2f}%)")
            print(f"   ├─ TP3: ${tp_list[2]:,.2f} ({risk_info['tp_distance_percent']*3:.2f}%)")
            print(f"   └─ TP4: ${tp_list[3]:,.2f} ({risk_info['tp_distance_percent']*4:.2f}%)")
            print(f"   Risk-Reward Ratio: {risk_info['risk_reward_ratio']:.2f}")
            print(f"   Risk per Trade: {risk_info['risk_per_trade_percent']:.2f}%")
            print()
            
    except Exception as e:
        print(f"❌ Error testing leverage system: {e}")
        print("This is expected if you don't have valid Binance API keys")

def test_configuration():
    """Test the configuration values."""
    print("⚙️  Configuration Test")
    print("=" * 30)
    print(f"Leverage-based TP/SL enabled: {config.LEVERAGE_BASED_TP_SL_ENABLED}")
    print(f"Base risk percent: {config.LEVERAGE_BASE_RISK_PERCENT}%")
    print(f"Base TP percent: {config.LEVERAGE_BASE_TP_PERCENT}%")
    print(f"Min SL distance: {config.LEVERAGE_MIN_SL_DISTANCE}%")
    print(f"Max SL distance: {config.LEVERAGE_MAX_SL_DISTANCE}%")
    print(f"Min TP distance: {config.LEVERAGE_MIN_TP_DISTANCE}%")
    print(f"Max TP distance: {config.LEVERAGE_MAX_TP_DISTANCE}%")
    print()

def demonstrate_leverage_math():
    """Demonstrate the leverage math with examples."""
    print("🧮 Leverage Math Examples")
    print("=" * 30)
    
    examples = [
        (50, "50x leverage"),
        (100, "100x leverage"),
        (200, "200x leverage"),
        (500, "500x leverage")
    ]
    
    base_risk = config.LEVERAGE_BASE_RISK_PERCENT
    base_tp = config.LEVERAGE_BASE_TP_PERCENT
    
    for leverage, description in examples:
        sl_distance = base_risk / leverage
        tp_distance = base_tp / leverage
        
        # Apply min/max constraints
        sl_distance = max(config.LEVERAGE_MIN_SL_DISTANCE, 
                         min(sl_distance, config.LEVERAGE_MAX_SL_DISTANCE))
        tp_distance = max(config.LEVERAGE_MIN_TP_DISTANCE, 
                         min(tp_distance, config.LEVERAGE_MAX_TP_DISTANCE))
        
        print(f"{description}:")
        print(f"  SL Distance: {sl_distance:.3f}%")
        print(f"  TP Distance: {tp_distance:.3f}%")
        print(f"  Risk per Trade: {sl_distance * leverage:.2f}%")
        print()

if __name__ == "__main__":
    print("🚀 Leverage-Based TP/SL System Test")
    print("=" * 50)
    print()
    
    test_configuration()
    demonstrate_leverage_math()
    test_leverage_calculation()
    
    print("✅ Test completed!")
 
