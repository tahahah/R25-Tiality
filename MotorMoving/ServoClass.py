try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    # Running on non-Pi system (like Windows) - create mock GPIO
    print("Warning: RPi.GPIO not available. Using mock GPIO for development.")
    GPIO_AVAILABLE = False
    
    class MockGPIO:
        BCM = 11
        OUT = 0
        HIGH = 1
        LOW = 0
        
        @staticmethod
        def setmode(mode):
            pass
            
        @staticmethod
        def setup(pin, mode):
            pass
            
        @staticmethod
        def output(pin, value):
            pass
            
        @staticmethod
        def cleanup(pin=None):
            pass
            
        @staticmethod
        def PWM(pin, freq):
            return MockPWM(pin, freq)
    
    class MockPWM:
        def __init__(self, pin, freq):
            self.pin = pin
            self.freq = freq
            
        def start(self, duty):
            pass
            
        def ChangeDutyCycle(self, duty):
            pass
            
        def stop(self):
            pass
    
    GPIO = MockGPIO()

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    # Running on non-Pi system (like Windows) - create mock pigpio
    print("Warning: pigpio not available. Using mock pigpio for development.")
    PIGPIO_AVAILABLE = False
    
    class MockPigpio:
        OUTPUT = 1
        
        def __init__(self):
            self.connected = True
            
        def set_mode(self, pin, mode):
            pass
            
        def set_PWM_frequency(self, pin, freq):
            pass
            
        def set_PWM_dutycycle(self, pin, duty):
            pass
            
        def set_PWM_range(self, pin, range_val):
            pass
            
        def stop(self):
            pass
            
        def write(self, pin, value):
            pass
    
    pigpio = type('pigpio', (), {
        'pi': lambda: MockPigpio(),
        'OUTPUT': 1
    })()

from time import sleep

class Servo:
    __servo_pwm_freq = 50
    __min_duty_cycle = 2.5    # 2.5% duty cycle for 0 degrees
    __max_duty_cycle = 12.5   # 12.5% duty cycle for 180 degrees
    min_angle = 0
    max_angle = 180
    current_angle = 0

    def __init__(self, pin, use_pigpio=False):
        self.use_pigpio = use_pigpio
        self.__initialise(pin)

    def update_settings(self, servo_pwm_freq, min_duty_cycle, max_duty_cycle, min_angle, max_angle, pin):
        self.__servo_pwm_freq = servo_pwm_freq
        self.__min_duty_cycle = min_duty_cycle
        self.__max_duty_cycle = max_duty_cycle
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.__initialise(pin)

    def move(self, angle):
        # round to 2 decimal places, so we have a chance of reducing unwanted servo adjustments
        angle = round(angle, 2)
        # do we need to move?
        if angle == self.current_angle:
            return
        self.current_angle = angle
        # calculate the new duty cycle and move the motor
        duty_cycle = self.__angle_to_duty_cycle(angle)
        
        if self.use_pigpio:
            self.__set_servo_position_pigpio(duty_cycle)
        else:
            self.__motor.ChangeDutyCycle(duty_cycle)
        
        sleep(0.1)  # Allow servo to reach position
    
    def stop(self):
        if self.use_pigpio:
            if hasattr(self, 'pi') and self.pi:
                self.pi.set_PWM_dutycycle(self.pin, 0)  # Stop PWM
        else:
            self.__motor.stop()
            GPIO.cleanup(self.pin)
    
    def get_current_angle(self):
        return self.current_angle

    def __angle_to_duty_cycle(self, angle):
        return self.__min_duty_cycle + (angle - self.min_angle) * self.__angle_conversion_factor

    def __set_servo_position_pigpio(self, duty_cycle):
        """Set servo position using pigpio PWM"""
        if PIGPIO_AVAILABLE and hasattr(self, 'pi') and self.pi:
            # Convert duty cycle percentage to pigpio range (0-255 for 8-bit, or use 1000 for 0.1% resolution)
            # Using 1000 range for better precision (0.1% resolution)
            pwm_value = int(duty_cycle * 10)  # Convert 2.5% to 25, 12.5% to 125
            self.pi.set_PWM_dutycycle(self.pin, pwm_value)

    def __initialise(self, pin):
        self.pin = pin
        self.current_angle = -0.001
        self.__angle_conversion_factor = (self.__max_duty_cycle - self.__min_duty_cycle) / (self.max_angle - self.min_angle)
        
        if self.use_pigpio:
            # Setup pigpio for Raspberry Pi
            if PIGPIO_AVAILABLE:
                try:
                    # Get or create global pigpio instance
                    if not hasattr(Servo, '_pi_instance'):
                        Servo._pi_instance = pigpio.pi()
                    self.pi = Servo._pi_instance
                    
                    # Check if connected
                    if not self.pi.connected:
                        print(f"Warning: pigpio daemon not running for pin {pin}")
                        self.pi = MockPigpio()
                        return
                    
                    # Set pin as output and configure PWM
                    self.pi.set_mode(pin, pigpio.OUTPUT)
                    self.pi.set_PWM_frequency(pin, self.__servo_pwm_freq)
                    self.pi.set_PWM_range(pin, 1000)  # 0.1% resolution
                    self.pi.set_PWM_dutycycle(pin, 0)  # Start with 0% duty cycle
                    
                except Exception as e:
                    print(f"Warning: Failed to initialize pigpio servo on pin {pin}: {e}")
                    # Create a mock pigpio object for development
                    self.pi = MockPigpio()
            else:
                # Use mock pigpio for development
                self.pi = MockPigpio()
        else:
            # Setup RPi.GPIO for Raspberry Pi
            if GPIO_AVAILABLE:
                try:
                    # GPIO should already be initialized globally
                    GPIO.setup(pin, GPIO.OUT)
                    self.__motor = GPIO.PWM(pin, self.__servo_pwm_freq)
                    self.__motor.start(0)  # Start PWM with 0% duty cycle
                except Exception as e:
                    print(f"Warning: Failed to initialize RPi.GPIO servo on pin {pin}: {e}")
                    # Create a mock PWM object for development
                    self.__motor = MockPWM(pin, self.__servo_pwm_freq)
            else:
                # Use mock PWM for development
                self.__motor = MockPWM(pin, self.__servo_pwm_freq)

    @classmethod
    def cleanup_all(cls):
        """Clean up all pigpio instances"""
        if PIGPIO_AVAILABLE and hasattr(cls, '_pi_instance'):
            cls._pi_instance.stop()
            delattr(cls, '_pi_instance')