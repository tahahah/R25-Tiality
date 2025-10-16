# 3-Axis Gimbal Controller

- Designed for SG90 servo motors (must check this will work with the 360 degree servo)

## Pin Configuration

- **X-axis servo**: GPIO pin 18 (left/right movement)
- **Y-axis servo**: GPIO pin 27 (up/down movement)  
- **Crane servo**: GPIO pin 22 (crane up/down movement)

To use the GIMBAL there are 10 functions to use:

### X-Axis Movement Functions

#### `x_left(degrees=10)`   
- **Purpose**: Moves the gimbal left (negative X direction)
- **Parameters**: 
  - `degrees` (int): Number of degrees to move left (default: 10)
- **Example**: `gimbal.x_left(15)` - moves 15 degrees left

#### `x_right(degrees=10)`
- **Purpose**: Moves the gimbal right (positive X direction)
- **Parameters**: 
  - `degrees` (int): Number of degrees to move right (default: 10)
- **Range**: 0-180 degrees (automatically constrained)
- **Example**: `gimbal.x_right(20)` - moves 20 degrees right

### Y-Axis Movement Functions

#### `y_up(degrees=10)`
- **Purpose**: Moves the gimbal up (positive Y direction)
- **Parameters**: 
  - `degrees` (int): Number of degrees to move up (default: 10)
- **Range**: 0-180 degrees (automatically constrained)
- **Example**: `gimbal.y_up(25)` - moves 25 degrees up

#### `y_down(degrees=10)`
- **Purpose**: Moves the gimbal down (negative Y direction)
- **Parameters**: 
  - `degrees` (int): Number of degrees to move down (default: 10)
- **Range**: 0-180 degrees (automatically constrained)
- **Example**: `gimbal.y_down(12)` - moves 12 degrees down

### Crane Movement Functions

#### `c_up(degrees=10)`
- **Purpose**: Moves the crane up (positive direction)
- **Parameters**: 
  - `degrees` (int): Number of degrees to move up (default: 10)
- **Range**: 0-180 degrees (automatically constrained)
- **Example**: `gimbal.c_up(15)` - moves crane up 15 degrees

#### `c_down(degrees=10)`
- **Purpose**: Moves the crane down (negative direction)
- **Parameters**: 
  - `degrees` (int): Number of degrees to move down (default: 10)
- **Range**: 0-180 degrees (automatically constrained)
- **Example**: `gimbal.c_down(10)` - moves crane down 10 degrees

### Position Setting Functions

#### `set_x_angle(angle)`
- **Purpose**: Sets the X-axis to a specific angle
- **Parameters**: 
  - `angle` (int): Target angle for X-axis (0-180 degrees)
- **Example**: `gimbal.set_x_angle(45)` - sets X-axis to 45 degrees

#### `set_y_angle(angle)`
- **Purpose**: Sets the Y-axis to a specific angle
- **Parameters**: 
  - `angle` (int): Target angle for Y-axis (0-180 degrees)
- **Example**: `gimbal.set_y_angle(135)` - sets Y-axis to 135 degrees

#### `set_c_angle(angle)`
- **Purpose**: Sets the Crane to a specific angle
- **Parameters**: 
  - `angle` (int): Target angle for Crane (0-180 degrees)
- **Example**: `gimbal.set_c_angle(90)` - sets Crane to 90 degrees

### Utility Functions

#### `get_position()`
- **Purpose**: Returns the current position of all three axes
- **Returns**: Dictionary with 'x', 'y', and 'c' keys containing current angles
- **Example**: 
  ```python
  position = gimbal.get_position()
  print(f"X: {position['x']}°, Y: {position['y']}°, C: {position['c']}°")
  ```

#### `center_gimbal()`
- **Purpose**: Centers all three axes to 90 degrees (neutral position)
- **Example**: `gimbal.center_gimbal()`

#### `cleanup()`
- **Purpose**: Stops all servos and cleans up GPIO resources
- **Example**: `gimbal.cleanup()`

## Usage Example

```python
from gimbalcode import GimbalController

# Initialize gimbal
gimbal = GimbalController(x_pin=18, y_pin=27, c_pin=22)

# Move gimbal around
gimbal.x_right(30)    # Move right 30 degrees
gimbal.y_up(20)       # Move up 20 degrees
gimbal.c_up(15)       # Move crane up 15 degrees
gimbal.x_left(15)     # Move left 15 degrees

# Set specific positions
gimbal.set_x_angle(45)   # Set X to 45 degrees
gimbal.set_y_angle(60)   # Set Y to 60 degrees
gimbal.set_c_angle(90)   # Set Crane to 90 degrees

# Get current position
pos = gimbal.get_position()
print(f"Current position: X={pos['x']}°, Y={pos['y']}°, C={pos['c']}°")

# Center and cleanup
gimbal.center_gimbal()
gimbal.cleanup()
```

## Dependencies

- `ServoClass.py` - Custom servo control class
- `time` - Python standard library for sleep function

## Notes

- All movement functions automatically constrain angles to the 0-180 degree range
- The gimbal automatically centers all axes when initialized
- Always call `cleanup()` when done to properly release GPIO resources
- Servo movement is relative to current position for movement functions
- Position setting functions move directly to the specified angle
