# from .anti_spoofing.anti_spoof_predict import AntiSpoofPredict
# import cv2

# predictor = AntiSpoofPredict(device_id=0)
# img = cv2.imread('data/data/IMG_9451.JPG')
# model_path = 'src/core/anti_spoofing/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth'
# result = predictor.predict(img, model_path)
# print(result)

# Save this as test_anti_spoof.py in your project root

# from src.core.anti_spoofing.anti_spoof_predict import AntiSpoofPredict
# import cv2

# # Path to your test image (adjust if needed)
# img_path = 'data/IMG_9451.JPG'
# img = cv2.imread(img_path)

# if img is None:
#     raise FileNotFoundError(f"Image not found at {img_path}")

# # Path to your model weights
# model_path = 'src/core/anti_spoofing/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth'

# # Initialize the predictor
# predictor = AntiSpoofPredict(device_id=0)

# # Run prediction
# result = predictor.predict(img, model_path)
# print("Prediction result:", result)

# import sys
# import os
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))
# from src.core.anti_spoofing.anti_spoof_predict import AntiSpoofPredict
import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/../../../..'))

from src.core.anti_spoofing.anti_spoof_predict import AntiSpoofPredict
import cv2

# Path to your test image (adjust if needed)
img_path = 'data/IMG_9451.JPG'
img = cv2.imread(img_path)

if img is None:
    raise FileNotFoundError(f"Image not found at {img_path}")

# Path to your model weights
model_path = 'src/core/anti_spoofing/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth'

# Initialize the predictor
predictor = AntiSpoofPredict(device_id=0)

# Run prediction
result = predictor.predict(img, model_path)
print("Prediction result:", result)