# Desert Order Bot

A Python project exploring computer vision and desktop automation for the game *Desert Order*.

## Features

- **Unit builder:** Uses an image classifier to recognize game states, click when the build queue is available, and pause when a captcha appears.
- **Attack detection:** Monitors the game minimap for attack indicators and sends alerts with attached screenshots and details to a set Discord channel. 

## Technical work

The project combines image classification and computer vision with screen capture, event detection, and automated mouse input. It uses Python tools including OpenCV, TensorFlow/Keras, and PyAutoGUI. This project was done fairly quickly across 2-3 weeks so rough outlines that comrpise about 70% of the code were AI generated (much more than that of my rocket projects). Designed to run in a Windows environment. I designed a licensing system it was not used as the tool was not marketed, only shared with some friends for free. 
