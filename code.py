# ghost//snail - device entry point (CircuitPython)
import time, usb_hid, hackypi
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode

display, splash = hackypi.setup()
level = hackypi.load_level()
hackypi.show_stage(level)

# Glow animation while host initializes HID (also looks great on boot)
hackypi.glow(duration=2.0, pulses=2)

kb  = Keyboard(usb_hid.devices)
lay = KeyboardLayoutUS(kb)

try:
    time.sleep(0.3)

    # Open terminal on Mac
    kb.send(Keycode.COMMAND, Keycode.SPACE)
    time.sleep(0.4)
    lay.write("terminal")
    kb.send(Keycode.RETURN)
    time.sleep(1.8)

    # Launch tamagotchi from CIRCUITPY drive
    lay.write("python3 /Volumes/CIRCUITPY/tamagotchi.py\n")
    kb.release_all()

    hackypi.overlay("awake!", 90, 120, hackypi.GREEN, 1)

except Exception as ex:
    kb.release_all()
    raise ex
