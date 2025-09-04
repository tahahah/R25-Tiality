#!/usr/bin/env python3
"""
Simple test script for gimbal control
Run this directly on the Raspberry Pi to test the gimbal
"""
from gimbalcode import GimbalController
import time

def test_gimbal():
    print("🎯 Testing Gimbal Controller")
    print("Pins: X=18, Y=27")
    print("=" * 30)
    
    try:
        # Initialize gimbal
        gimbal = GimbalController(x_pin=18, y_pin=27)
        print("✅ Gimbal initialized successfully")
        
        # Get initial position
        pos = gimbal.get_position()
        print(f"📍 Initial position: X={pos['x']}°, Y={pos['y']}°")
        
        # Test movements
        print("\n🔄 Testing movements...")
        
        # Test X-axis (left/right)
        print("➡️ Moving right 20°...")
        gimbal.x_right(20)
        time.sleep(1)
        
        print("⬅️ Moving left 15°...")
        gimbal.x_left(15)
        time.sleep(1)
        
        # Test Y-axis (up/down)
        print("⬆️ Moving up 15°...")
        gimbal.y_up(15)
        time.sleep(1)
        
        print("⬇️ Moving down 10°...")
        gimbal.y_down(10)
        time.sleep(1)
        
        # Test specific angles
        print("🎯 Setting X to 45°...")
        gimbal.set_x_angle(45)
        time.sleep(1)
        
        print("🎯 Setting Y to 60°...")
        gimbal.set_y_angle(60)
        time.sleep(1)
        
        # Get final position
        pos = gimbal.get_position()
        print(f"📍 Final position: X={pos['x']}°, Y={pos['y']}°")
        
        # Center gimbal
        print("🎯 Centering gimbal...")
        gimbal.center_gimbal()
        time.sleep(1)
        
        pos = gimbal.get_position()
        print(f"📍 Centered position: X={pos['x']}°, Y={pos['y']}°")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        try:
            gimbal.cleanup()
            print("🧹 Gimbal cleaned up")
        except:
            pass

if __name__ == "__main__":
    test_gimbal()
