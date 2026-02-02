import pandas as pd
import numpy as np
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from app.ai.registry import ModelRegistry
from app.ai.features import FeatureEngineer
import os

def bootstrap_breakout_model():
    print("Bootstrapping Breakout Classifier...")
    
    # 1. Fetch some historical data for training (NIFTY 50)
    data = yf.download("^NSEI", period="2y", interval="1d", auto_adjust=True)
    if isinstance(data, tuple) or data.empty:
        print("Download failed or empty.")
        return

    # Handle MultiIndex columns (sometimes yf returns these even for single ticker)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
        
    data.columns = [c.lower() for c in data.columns]
    
    features_list = []
    labels = []
    
    # Simple sliding window to generate training samples
    # We define a "Genuine Breakout" as: 
    # Current Close > Prev 20 High AND Next 5 Close > Current Close (simplified)
    for i in range(50, len(data) - 5):
        df_slice = data.iloc[:i+1]
        feat = FeatureEngineer.calculate_features(df_slice)
        
        # Heuristic labeling for bootstrap:
        # If price stays above breakout level for 5 days, it was genuine.
        curr_close = data['close'].iloc[i]
        prev_20_high = data['high'].iloc[i-20:i].max()
        
        if curr_close > prev_20_high:
            # It's a breakout. Was it genuine?
            future_close = data['close'].iloc[i+1:i+6].mean()
            is_genuine = 1 if future_close > curr_close else 0
            
            features_list.append([feat['vol_ratio'], feat['atr_expansion'], feat['dist_from_ema']])
            labels.append(is_genuine)
            
    if not features_list:
        print("No breakout samples found in historical data. Creating synthetic samples.")
        # Synthetic fallback if no breakouts found in NIFTY 2y (unlikely but safe)
        X = np.array([[2.0, 1.5, 2.0], [0.5, 0.5, 0.1], [3.0, 2.0, 5.0], [0.8, 0.9, -1.0]])
        y = np.array([1, 0, 1, 0])
    else:
        X = np.array(features_list)
        y = np.array(labels)

    # 2. Train Model
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # 3. Save to Registry
    ModelRegistry.save_model(model, "breakout_rf")
    print(f"Successfully bootstrapped model with {len(X)} samples.")

if __name__ == "__main__":
    bootstrap_breakout_model()
