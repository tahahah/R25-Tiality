import RPi.GPIO as GPIO
from time import sleep

class Servo:
    __servo_pwm_freq = 50
    __min_duty_cycle = 2.5    # 2.5% duty cycle for 0 degrees
    __max_duty_cycle = 12.5   # 12.5% duty cycle for 180 degrees
    min_angle = 0
    max_angle = 180
    current_angle = 0.001

    def __init__(self, pin):
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
        self.__motor.ChangeDutyCycle(duty_cycle)
        sleep(0.1)  # Allow servo to reach position
    
    def stop(self):
        self.__motor.stop()
        GPIO.cleanup(self.pin)
    
    def get_current_angle(self):
        return self.current_angle

    def __angle_to_duty_cycle(self, angle):
        return self.__min_duty_cycle + (angle - self.min_angle) * self.__angle_conversion_factor

    def __initialise(self, pin):
        self.pin = pin
        self.current_angle = -0.001
        self.__angle_conversion_factor = (self.__max_duty_cycle - self.__min_duty_cycle) / (self.max_angle - self.min_angle)
        
        # Setup GPIO for Raspberry Pi - FIX THIS
        GPIO.setmode(GPIO.BCM)  # ✅ Use BCM numbering (GPIO 18, 27)
        GPIO.setup(pin, GPIO.OUT)
        self.__motor = GPIO.PWM(pin, self.__servo_pwm_freq)
        self.__motor.start(0)  # Start with 0 duty cycle