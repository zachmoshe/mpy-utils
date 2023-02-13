import time
import uasyncio as asyncio

from ulab import numpy as np


class NeoPixelEffectsController:
    """"Orchastrates effects on many devices.
    
    Initializes with all devices. Allows the user to add effect to a device. 
    Runs periodically and aggregates all active effects to a single update 
    per device.

    Users write async code that defines the effect sequence. For example:
    ```
    def effect_sequence():
        # controller has 2 strips (`strip1` and `strip2`)
        await asyncio.gather(
            ctl.devices["strip1"].add_effect(SinglePixelMovingEffect.Spec(rgb_color=(255, 0, 0), total_effect_time=1.)),
            ctl.devices["strip2"].add_effect(GaussianMovingEffect.Spec(rgb_color=(255, 0, 0), sigma=2., total_effect_time=2.)),
        )
        await ctl.devices["strip1"].add_effect(SinglePixelMovingEffect.Spec(rgb_color=(128, 128, 128), total_effect_time=.5, reversed=True)),
    ```
    """
    class ControllerDevice:
        def __init__(self, device):
            self.device = device
            self.active_effects = {}  # effect -> start_time (in time.ticks_us())

        def add_effect(self, effect_spec):
            effect = effect_spec.with_device(self.device)
            self.active_effects[effect] = time.ticks_us()
            return effect

        def update(self, current_ticks_us):
            s1 = time.ticks_us()

            num_effects = len(self.active_effects)

            state_matrix = np.zeros((num_effects,) + self.device.state_shape)        

            for i, (effect, effect_start_time) in enumerate(self.active_effects.items()):
                if not effect.is_completed:
                    relative_effect_time = time.ticks_diff(current_ticks_us, effect_start_time) / 1e6
                    effect_state_matrix = effect(relative_time_secs=relative_effect_time)

                    if effect_state_matrix is not None:  # effect is not finished
                        state_matrix[i] = effect(relative_time_secs=relative_effect_time)
                        continue 
                
                # If effect.is_completed or effect returned None
                del self.active_effects[effect]
                

            state_matrix = np.sum(state_matrix, axis=0)  # Sum all effects.
            state_matrix = np.clip(state_matrix, 0, 255)

            self.device.update_state(state_matrix)


    def __init__(self, devices, updates_freq_hz=50): 
        self.time_per_update_secs = 1. / updates_freq_hz
        self.devices = {
            device_name: self.ControllerDevice(device) 
            for device_name, device in devices.items()
        }
        self._asyncio_task = None

    def start(self):
        async def _start():
            while True:
                start_ticks_us = time.ticks_us()

                # update all devices
                for device_name, controller_device in self.devices.items():
                    controller_device.update(start_ticks_us)

                # sleep for the reminder of the cycle (if needed)
                cycle_time_secs = time.ticks_diff(time.ticks_us(), start_ticks_us) / 1e6  # duration is now in seconds
                sleep_time = max(0, self.time_per_update_secs - cycle_time_secs)
                await asyncio.sleep(sleep_time)
        
        self._asyncio_task = asyncio.create_task(_start())

    def stop(self):
        if self._asyncio_task is not None:
            self._asyncio_task.cancel()
            self._asyncio_task = None
