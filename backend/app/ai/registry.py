import os
import joblib
import logging

class ModelRegistry:
    MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
    
    @classmethod
    def load_model(cls, model_name: str, version: str = "latest"):
        """
        Loads a scikit-learn model from disk.
        Returns None if not found (fallback to heuristic).
        """
        try:
            # Create dir if not exists (for first run)
            if not os.path.exists(cls.MODEL_DIR):
                os.makedirs(cls.MODEL_DIR)
                
            filename = f"{model_name}.joblib"
            path = os.path.join(cls.MODEL_DIR, filename)
            
            if os.path.exists(path):
                return joblib.load(path)
            else:
                logging.warning(f"AI Model {model_name} not found at {path}. Using heuristic fallback.")
                return None
        except Exception as e:
            logging.error(f"Failed to load model {model_name}: {e}")
            return None

    @classmethod
    def save_model(cls, model, model_name: str):
        """
        Saves a trained model to disk.
        """
        if not os.path.exists(cls.MODEL_DIR):
            os.makedirs(cls.MODEL_DIR)
        
        path = os.path.join(cls.MODEL_DIR, f"{model_name}.joblib")
        joblib.dump(model, path)
        print(f"Model saved to {path}")
