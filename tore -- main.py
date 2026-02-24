[1mdiff --git a/main.py b/main.py[m
[1mindex 23d690f..8dd995c 100644[m
[1m--- a/main.py[m
[1m+++ b/main.py[m
[36m@@ -92,7 +92,7 @@[m [mdef detect_levels_for_df(df: pd.DataFrame, tf: str):[m
     return supports, resistances[m
 [m
 @app.get("/api/v1/dashboard")[m
[31m-async def get_dashboard(symbol: str = "RELIANCE", tf: str = "1D"):[m
[32m+[m[32masync def get_dashboard(symbol: str = "RELIANCE", tf: str = "1D", strategy: str = "SR"):[m[41m[m
     try:[m
         # 0. Normalize Symbol[m
         norm_symbol = MarketDataService.normalize_symbol(symbol)[m
[36m@@ -107,7 +107,35 @@[m [masync def get_dashboard(symbol: str = "RELIANCE", tf: str = "1D"):[m
         # 2. Extract Levels (Primary)[m
         supports, resistances = detect_levels_for_df(df, tf)[m
         [m
[31m-        # 3. Extract MTF Levels[m
[32m+[m[32m        # 3. Get Sector State for guards[m[41m[m
[32m+[m[32m        from app.services.sector_service import SectorService[m[41m[m
[32m+[m[32m        from app.services.constituent_service import ConstituentService[m[41m[m
[32m+[m[41m        [m
[32m+[m[32m        sector_name = ConstituentService.get_sector_for_ticker(norm_symbol)[m[41m[m
[32m+[m[32m        sector_state = "NEUTRAL"[m[41m[m
[32m+[m[32m        if sector_name:[m[41m[m
[32m+[m[32m            rotation_data, _ = SectorService.get_rotation_data(timeframe=tf)[m[41m[m
[32m+[m[32m            if sector_name in rotation_data:[m[41m[m
[32m+[m[32m                sector_state = rotation_data[sector_name]['metrics']['state'][m[41m[m
[32m+[m[41m        [m
[32m+[m[32m        # 4. Strategy Dispatcher[m[41m[m
[32m+[m[32m        strategy_result = {}[m[41m[m
[32m+[m[32m        if strategy == "SR":[m[41m[m
[32m+[m[32m            strategy_result = SREngine.runSRStrategy(df, sector_state, supports, resistances)[m[41m[m
[32m+[m[32m        elif strategy == "SWING":[m[41m[m
[32m+[m[32m            # Get 1D for structure/trend if needed, or use current DF[m[41m[m
[32m+[m[32m            htf = "1D" if tf != "1D" else "1W"[m[41m[m
[32m+[m[32m            hdf, _ = MarketDataService.get_ohlcv(norm_symbol, htf)[m[41m[m
[32m+[m[32m            htf_trend = InsightEngine.get_structure_bias(hdf)[m[41m[m
[32m+[m[32m            strategy_result = SwingEngine.runSwingStrategy(df, sector_state, htf_trend, supports)[m[41m[m
[32m+[m[32m        elif strategy == "DEMAND_SUPPLY":[m[41m[m
[32m+[m[32m            # Re-fetch zones or use existing? detect_levels_for_df already does this.[m[41m[m
[32m+[m[32m            sh, sl = SwingEngine.get_swings(df)[m[41m[m
[32m+[m[32m            atr = ZoneEngine.calculate_atr(df).iloc[-1][m[41m[m
[32m+[m[32m            zones = ZoneEngine.cluster_swings(sh + sl, atr)[m[41m[m
[32m+[m[32m            strategy_result = ZoneEngine.runDemandSupplyStrategy(df, sector_state, zones)[m[41m[m
[32m+[m[41m            [m
[32m+[m[32m        # 5. Extract MTF Levels[m[41m[m
         higher_tfs = [][m
         if tf == "5m": higher_tfs = ["15m", "1H", "1D"][m
         elif tf == "15m": higher_tfs = ["1H", "2H", "1D"][m
[36m@@ -128,11 +156,8 @@[m [masync def get_dashboard(symbol: str = "RELIANCE", tf: str = "1D"):[m
             except Exception as e:[m
                 print(f"MTF error for {htf}: {e}")[m
                 [m
[31m-        # 4. Get Insights[m
[31m-        # Get Global AI Insights[m
[32m+[m[32m        # 6. Get Insights[m[41m[m
         ai_analysis = ai_engine.get_insights(df)[m
[31m-        [m
[31m-        # Get Fundamentals[m
         fundamentals = FundamentalService.get_fundamentals(norm_symbol)[m
 [m
         insights = {[m
[36m@@ -141,46 +166,49 @@[m [masync def get_dashboard(symbol: str = "RELIANCE", tf: str = "1D"):[m
             "ema_bias": InsightEngine.get_ema_bias(df),[m
             "hammer": InsightEngine.detect_hammer(df),[m
             "engulfing": InsightEngine.detect_engulfing(df),[m
[31m-            "upside_pct": float(round(((resistances[0]['price'] - cmp) / cmp * 100), 2)) if resistances else 0.0[m
[32m+[m[32m            "upside_pct": float(round(((resistances[0]['price'] - cmp) / cmp * 100), 2)) if resistances else 0.0,[m[41m[m
[32m+[m[32m            "adx": round(InsightEngine.get_adx(df), 2),[m[41m[m
[32m+[m[32m            "structure": InsightEngine.get_structure_bias(df)[m[41m[m
         }[m
         [m
[31m-        # 5. Format OHLCV for Chart[m
[31m-        ohlcv = [][m
[31m-        for i in range(len(df)):[m
[31m-            ohlcv.append({[m
[31m-                "time": int(df.index[i].timestamp()),[m
[31m-                "open": float(round(df['open'].iloc[i], 2)),[m
[31m-                "high": float(round(df['high'].iloc[i], 2)),[m
[31m-                "low": float(round(df['low'].iloc[i], 2)),[m
[31m-                "close": float(round(df['close'].iloc[i], 2))[m
[31m-            })[m
[32m+[m[32m        # 7. Format OHLCV for Chart[m[41m[m
[32m+[m[32m        ohlcv = [{[m[41m[m
[32m+[m[32m            "time": int(df.index[i].timestamp()),[m[41m[m
[32m+[m[32m            "open": float(round(df['open'].iloc[i], 2)),[m[41m[m
[32m+[m[32m            "high": float(round(df['high'].iloc[i], 2)),[m[41m[m
[32m+[m[32m            "low": float(round(df['low'].iloc[i], 2)),[m[41m[m
[32m+[m[32m            "close": float(round(df['close'].iloc[i], 2))[m[41m[m
[32m+[m[32m        } for i in range(len(df))][m[41m[m
 [m
[31m-        # 6. Response Structure[m
[32m+[m[32m        # 8. Response Structure[m[41m[m
         return {[m
             "meta": {[m
                 "symbol": norm_symbol,[m
                 "tf": tf,[m
[32m+[m[32m                "strategy": strategy,[m[41m[m
                 "cmp": float(round(cmp, 2)),[m
[31m-                "data_version": "v1.3.0"[m
[32m+[m[32m                "data_version": "v1.4.0"[m[41m[m
             },[m
             "summary": {[m
                 "nearest_support": float(round(supports[0]['price'], 2)) if supports else None,[m
                 "nearest_resistance": float(round(resistances[0]['price'], 2)) if resistances else None,[m
                 "market_regime": ai_analysis.get('regime', {}).get('market_regime', 'UNKNOWN'),[m
                 "priority": ai_analysis.get('priority', {}).get('level', 'LOW'),[m
[31m-                "stop_loss": float(round(supports[0]['price'] * 0.99, 2)) if supports else float(round(cmp * 0.98, 2)),[m
[31m-                "risk_reward": f"1:{round((resistances[0]['price'] - cmp)/(cmp - supports[0]['price']), 1)}" if supports and resistances and (cmp - supports[0]['price']) > 0 else "1:2.0"[m
[32m+[m[32m                "stop_loss": strategy_result.get('stopLoss', cmp * 0.98),[m[41m[m
[32m+[m[32m                "risk_reward": f"1:{strategy_result.get('riskReward', 2.0)}",[m[41m[m
[32m+[m[32m                "trade_signal": strategy_result.get('entryStatus', 'HOLD'),[m[41m[m
[32m+[m[32m                "trade_signal_reason": f"{strategy} Bias: {strategy_result.get('bias', 'NEUTRAL')}. Sector: {sector_state}.",[m[41m[m
[32m+[m[32m                "confidence": strategy_result.get('confidence', 0)[m[41m[m
             },[m
[32m+[m[32m            "strategy": strategy_result,[m[41m[m
             "levels": {[m
[31m-                "primary": {[m
[31m-                    "supports": supports,[m
[31m-                    "resistances": resistances[m
[31m-                },[m
[32m+[m[32m                "primary": {"supports": supports, "resistances": resistances},[m[41m[m
                 "mtf": mtf_levels[m
             },[m
             "insights": insights,[m
             "ai_analysis": ai_analysis,[m
             "fundamentals": fundamentals,[m
[32m+[m[32m            "sector_info": {"name": sector_name, "state": sector_state},[m[41m[m
             "ohlcv": ohlcv[m
         }[m
     except Exception as e:[m
