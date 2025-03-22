import cv2
import sys
import can
import struct
import time
from eye_utils import get_camera, detect_eyes
from config import CAN_CONFIG, EYE_DETECTION, DISPLAY, ERROR_VALUES


def init_can_interface():
    """Initialize the CAN interface for communication"""
    try:
        # Initialize the CAN bus interface using config values
        bus = can.interface.Bus(
            bustype=CAN_CONFIG['bustype'],
            channel=CAN_CONFIG['channel'],
            bitrate=CAN_CONFIG['bitrate']
        )
        print("CAN interface initialized successfully")
        return bus
    except Exception as e:
        print(f"Error initializing CAN interface: {e}")
        print("Please ensure the canable device is connected and properly configured")
        sys.exit(1)


def send_eye_coordinates(can_bus, x, y):
    """Send eye midpoint coordinates via CAN with ID 0x100
    
    Coordinates are sent as int32 values (4 bytes each)
    """
    try:
        # Convert coordinates to integers if they're not already
        x_int = int(x)
        y_int = int(y)
        
        # Pack the x and y coordinates using the format from config
        data = struct.pack(CAN_CONFIG['data_format'], x_int, y_int)
        
        # Create and send the CAN message
        message = can.Message(
            arbitration_id=CAN_CONFIG['data_id'],
            data=data,
            is_extended_id=False
        )
        can_bus.send(message)
        print(f"Sent eye coordinates: x={x_int}, y={y_int}")
        return True
    except Exception as e:
        print(f"Error sending CAN message: {e}")
        return False


def process_eye_detection(face_cascade, eye_cascade):
    """Handle the eye detection process after receiving a trigger"""
    # Initialize camera
    camera = get_camera()
    if not camera.isOpened():
        print("Error: Could not open camera.")
        return None
    
    # Try to detect eyes for a short period
    max_attempts = EYE_DETECTION['max_detection_attempts']
    attempt = 0
    eye_midpoint = None
    
    while attempt < max_attempts and eye_midpoint is None:
        # Capture frame-by-frame
        ret, frame = camera.read()
        if not ret:
            print("Error: Failed to grab frame")
            break
        
        frame = cv2.flip(frame, 1)
        
        # Process the frame to detect and mark eyes
        processed_frame, eye_midpoint = detect_eyes(frame, face_cascade, eye_cascade)
        
        # Display the resulting frame
        cv2.imshow(DISPLAY['window_name'], processed_frame)
        cv2.waitKey(1)  # Update the display
        
        attempt += 1
        time.sleep(EYE_DETECTION['attempt_delay'])  # Delay between attempts
    
    # Release the camera and close windows
    camera.release()
    cv2.destroyAllWindows()
    
    return eye_midpoint


def main():
    # Initialize CAN interface
    can_bus = init_can_interface()
    
    # Load pre-trained classifiers for face and eye detection
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye_tree_eyeglasses.xml')
    
    # Check if the cascades were loaded successfully
    if face_cascade.empty() or eye_cascade.empty():
        print("Error: Could not load cascade classifiers")
        sys.exit(1)

    print(f"Waiting for CAN trigger (ID 0x{CAN_CONFIG['trigger_id']:X})...")
    
    while True:
        # Wait for a CAN message with trigger ID
        message = can_bus.recv()
        
        if message is not None and message.arbitration_id == CAN_CONFIG['trigger_id']:
            print("Received trigger message. Starting eye detection...")
            
            # Process eye detection
            eye_midpoint = process_eye_detection(face_cascade, eye_cascade)
            
            # Send eye coordinates if detected
            if eye_midpoint is not None:
                x, y = eye_midpoint
                send_eye_coordinates(can_bus, x, y)
            else:
                print("No eyes detected within timeout period")
                # Send a default or error value
                error_x, error_y = ERROR_VALUES['no_eyes_detected']
                send_eye_coordinates(can_bus, error_x, error_y)
            
            print(f"Waiting for next CAN trigger (ID 0x{CAN_CONFIG['trigger_id']:X})...")


if __name__ == "__main__":
    main()
