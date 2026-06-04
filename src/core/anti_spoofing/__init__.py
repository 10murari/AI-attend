# src/core/anti-spoofing/__init__.py
import os
import cv2
from .anti_spoof_predict import AntiSpoofPredict

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'resources', 'anti_spoof_models')

def is_live_face(image_path, device_id=0):
    """
    Check if a face image is live (not spoofed).
    
    Args:
        image_path: Path to the face image
        device_id: GPU device ID (default: 0)
    
    Returns:
        True if live face, False if spoofed
    """
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Image not found at {image_path}")
    
    # Use the best available model
    model_file = os.path.join(MODEL_PATH, '2.7_80x80_MiniFASNetV2.pth')
    
    predictor = AntiSpoofPredict(device_id=device_id)
    result = predictor.predict(image, model_file)
    
    # result is a 2-element array: [spoof_prob, live_prob]
    # Return True if live probability > spoof probability
    return result[0][1] > result[0][0]