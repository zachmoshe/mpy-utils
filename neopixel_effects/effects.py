import uasyncio as asyncio

from ulab import numpy as np


class Effect:
    """Abstract class. Defines an effect. 
    
    An effect has to calcualte its `state` (np.array of pixel RGB values) per point in time 
    from its starting time.

    An `Effect` class has to be initialized from both the EffectSpec (the arguments for the effect
    itself) and the device its being applied on (as its shape is required for some calculations).
    For a more convenient experience from the user side, we let the user create the Spec class only,
    and the controller will attach it to the right device using the `with_device(...)` method.
    """
    class Spec:
        """Abstract class. Every effect may have a Spec class with additional relevant fields.
        
        For example - If the effect moves a colored pixel across the device, it might need
        the RGB color of that pixel as an argument.
        """
        def __init__(self, effect_cls): 
            self.effect_cls = effect_cls

        def with_device(self, device):
            return self.effect_cls(spec=self, device=device)


    def __init__(self, spec, device):
        self.spec = spec
        self.device = device
        self._completion_event = asyncio.Event()

    @property
    def is_completed(self):
        return self._completion_event.is_set()

    def _set_completed(self):
        self._completion_event.set()

    def __call__(self, relative_time_secs) -> np.array: 
        """Abstract. Should return the state for this effect at a given point in time.

        IF the effect is finite (a pixel moving from one side to another), this method 
        should also call `self._set_completed()` if `relative_time_secs` indicates that.
        """

    async def await_completion(self):
        """Awaits (async) until the effect is declared as finished."""
        await self._completion_event.wait()

    def cancel(self):
        self._set_completed()


_DEFAULT_TOTAL_EFFECT_TIME = 1.0
_DEFAULT_RGB_COLOR = np.array([255, 255, 255])


class MovingEffect(Effect):
    """A parent class for all effects where a pattern is moving across the device.
    
    These all share the following required attributes: `total_effect_time` (can be None or np.inf for infinite effects), 
    `rgb_color` and `reversed`. Their logic is also similar and calculates the current position of the effect on the strip,
    calls an abstract method to do the actual calculation and deals with `reversed` if needed.
    """
    class Spec(Effect.Spec): 
        def __init__(self, effect_cls, 
            total_effect_time = _DEFAULT_TOTAL_EFFECT_TIME, 
            rgb_color = _DEFAULT_RGB_COLOR, 
            reversed = False,
            indefinite_pingpong = False):

            super().__init__(effect_cls)
            self.total_effect_time = total_effect_time
            self.rgb_color = np.array(rgb_color)
            self.reversed = reversed
            self.indefinite_pingpong = indefinite_pingpong

    def _calculate_state(self, current_pos, num_pixels, num_channels): ...

    def __call__(self, relative_time_secs):
        if (not self.spec.indefinite_pingpong) and (relative_time_secs > self.spec.total_effect_time):
            self._set_completed()
            return np.zeros(self.device.state_shape)

        num_pixels = self.device.state_shape[0]
        num_channels = self.device.state_shape[1]
        
        # If `pingpong` mode - the position goes back and forth from 0 to num_pixels (indefinitely).
        frac = relative_time_secs / self.spec.total_effect_time
        if self.spec.indefinite_pingpong:
            frac %= 2.  # back and forth
            current_pos = num_pixels * (frac - 2 * max(frac - 1, 0))
        else:
            current_pos = num_pixels * relative_time_secs / self.spec.total_effect_time
        current_pos = min(current_pos, num_pixels - 1)  # handling an end case of the last pixel
        current_state = self._calculate_state(current_pos, num_pixels, num_channels)

        if self.spec.reversed:
            current_state = current_state[::-1]
        return current_state


class SinglePixelMovingEffect(MovingEffect):
    """A single pixel that moves from one end to the other."""
    class Spec(MovingEffect.Spec):
        def __init__(self, **kwargs):
            super().__init__(SinglePixelMovingEffect, **kwargs)

    def _calculate_state(self, current_pos, num_pixels, num_channels):
        state = np.zeros((num_pixels, num_channels))
        state[int(current_pos)] = self.spec.rgb_color
        return state


class GaussianMovingEffect(MovingEffect):
    """A colored gaussian that moves from one end to another."""
    class Spec(MovingEffect.Spec):
        def __init__(self, sigma = 1.0, **kwargs):
            super().__init__(GaussianMovingEffect, **kwargs)
            self.sigma = sigma

    @staticmethod
    def _normed_gaussian(x, mu, sigma):
        return np.exp(-0.5 * ((x - mu) / sigma) ** 2)

    def _calculate_state(self, current_pos, num_pixels, num_channels):
        return np.concatenate(
            tuple(self.spec.rgb_color.reshape((1, num_channels)) * self._normed_gaussian(i, mu=current_pos, sigma=self.spec.sigma) for i in range(num_pixels)),
            axis=0
        )


class DecayMovingEffect(MovingEffect):
    """A colored pixel with a dimmed trail that moves from one end to another."""
    class Spec(MovingEffect.Spec):
        def __init__(self, decay_factor = 0.25, **kwargs):
            super().__init__(DecayMovingEffect, **kwargs)
            self.decay_factor = decay_factor

    def _calculate_state(self, current_pos, num_pixels, num_channels):
        exponent = current_pos - np.arange(num_pixels, dtype=np.float)
        exponent[exponent < 0] = np.inf
        return np.concatenate(
            tuple(self.spec.rgb_color.reshape((1, num_channels)) for _ in range(num_pixels))
        ) * (self.spec.decay_factor ** exponent).reshape((num_pixels, 1))


class SinusEffect(Effect):
    """An indefinite effect of a moving sinus wave."""
    class Spec(Effect.Spec):
        def __init__(self, base_color = (16, 16, 16), additional_color = (8, 8, 8), freq = 1.0, cycle_time = 1.0):
            super().__init__(SinusEffect)
            self.base_color = np.array(base_color)
            self.additional_color = np.array(additional_color)
            self.freq = freq
            self.cycle_time = cycle_time
    
    def __call__(self, relative_time_secs):
        num_pixels, num_channels = self.device.state_shape

        rel_cycle = 2 * np.pi * (relative_time_secs / self.spec.cycle_time) % 1.0
        sin_values = 0.5 + 0.5 * np.sin(np.linspace(rel_cycle, rel_cycle + 2 * np.pi * self.spec.freq, num_pixels))
        base_color = np.concatenate(
            tuple(self.spec.base_color.reshape((1, num_channels)) for _ in range(num_pixels))
        )
        additional_color = np.concatenate(
            tuple(self.spec.additional_color.reshape((1, num_channels)) for _ in range(num_pixels))
        )
        state = base_color + sin_values.reshape((num_pixels, 1)) * additional_color
        return state
