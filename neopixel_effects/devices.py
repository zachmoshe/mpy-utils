from machine import Pin
import neopixel

from ulab import numpy as np


# TODO(zach): Add support for 3/4 channels.
_NUM_CHANNELS = 3


class NeoPixelDevice:
    """Abstract class. Defines a NeoPixel Device.
    
    A `device` can be a NeoPixel strip for example. There can be more than one in a given application 
    and the controller schedules effects on all of them together.
    """
    def update_state(self, state: np.array): 
        """Updates the pixels given a `state` (np.array with RGB values per pixel)."""
    
    @property
    def state_shape(self) -> np.array: ...

    def _validate_state_shape(self, given_state):
        if given_state.shape != self.state_shape:
            raise ValueError(f"Given state ({given_state.shape}) was not compatible with device's expected shape ({self.state_shape}).")


class NeoPixelStrip(NeoPixelDevice):
    """A single NeoPixel strip."""
    def __init__(self, gpio_pin, num_pixels, num_channels = _NUM_CHANNELS, intensity_factor = 0.25):
        self.gpio_pin = Pin(gpio_pin, Pin.OUT)
        self.num_pixels = num_pixels
        self.num_channels = num_channels
        self.intensity_factor = intensity_factor
        self.neopixel = neopixel.NeoPixel(self.gpio_pin, self.num_pixels)
        self._state_shape = (self.num_pixels, self.num_channels)

    @property
    def state_shape(self):
        return self._state_shape

    def update_state(self, state: np.array):
        self._validate_state_shape(state)
        # Bulk-writing in a more efficient way..
        state = state * self.intensity_factor
        self.neopixel.buf = bytes(int(x) for x in state.flatten())
        self.neopixel.write()
