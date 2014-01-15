from cv2 import cv
from pyscreenshot import grab

cv.SaveImage('camera.png', cv.QueryFrame(cv.CaptureFromCAM(0)))

grab(backend="pyqt").save("screen.png")
