import struct 
import uasyncio as asyncio

from machine import Pin, I2S
from ulab import numpy as np
import wave 


_DEFAULT_I2S_BUFFER_SIZE_BYTES = 16 * 1024
_DEFAULT_FILE_BUFFER_SIZE_BYTES = 4 * 1024


def _get_wav_file_attributes(filename: str):
    """Returns a tuple of (sample_rate, num_channels, bits_per_sample)."""
    with wave.open(filename) as wavf:
        sample_rate = wavf.getframerate()
        num_channels = wavf.getnchannels()
        sample_width = wavf.getsampwidth()
    return sample_rate, num_channels, sample_width * 8


class AudioMixer:
    class Channel:
        def __init__(self, file_buffer_size_bytes):
            self._buffer = bytearray(file_buffer_size_bytes)
            self.buffer_mv = memoryview(self._buffer)
            self.fh = None
            self.bytes_read = 0
            self.samples = np.frombuffer(self.buffer_mv, dtype=np.int16).reshape((1, file_buffer_size_bytes // 2))  # TBD: assuming 16 bits per sample here!!

        def clear(self):
            self.bytes_read = 0
            if self.is_active:
                self.fh.close()
                self.fh = None

        def reset(self):
            if self.is_active:
                self.fh.seek(44)  # Start of data section in WAV files

        def load(self, filename):
            self.clear()
            self.fh = open(filename, "rb")
            self.reset()

        @property
        def is_active(self):
            return self.fh is not None

        def _read(self):
            if not self.is_active:
                return
            self.bytes_read = self.fh.readinto(self.buffer_mv)


    def __init__(self, sck_gpio: int, ws_gpio: int, sd_gpio: int,
        wav_num_channels = 2, wav_sample_rate = 44100, wav_sample_bits = 16,
        i2s_buffer_size_bytes = _DEFAULT_I2S_BUFFER_SIZE_BYTES,
        file_buffer_size_bytes = _DEFAULT_FILE_BUFFER_SIZE_BYTES,
        num_mixer_channels = 1):

        self.sck_gpio = sck_gpio
        self.ws_gpio = ws_gpio
        self.sd_gpio = sd_gpio

        self.num_channels = num_mixer_channels
        self.channels = [AudioMixer.Channel(file_buffer_size_bytes) for _ in range(num_mixer_channels)]

        self.i2s_out = I2S(0, sck=Pin(sck_gpio), ws=Pin(ws_gpio), sd=Pin(sd_gpio), mode=I2S.TX, 
            bits=wav_sample_bits, format=(I2S.STEREO if wav_num_channels==2 else I2S.MONO), rate=wav_sample_rate,
            ibuf=i2s_buffer_size_bytes)

    def __getitem__(self, item):
        if not isinstance(item, int):
            raise NotImplementedError("AudioMixer supports ints only as channel IDs")
        return self.channels[item]

    async def start(self):
        swriter = asyncio.StreamWriter(self.i2s_out)

        while True:
            # Read from all channels
            for channel in self.channels:
                channel._read()

            # Mix together

            # min_bytes_read = min(channel.bytes_read for channel in self.channels if channel.is_active)
            # min_num_samples = min_bytes_read // 2  # TBD: assuming 16 bits per sample.
            # channels_samples = np.concatenate(
            #     tuple(channel.samples[:, :min_num_samples] for channel in self.channels if channel.is_active),
            #     axis=0)
            
            # print(channels_samples.shape)
            # print(channels_samples[:, :5])
            # mixed_samples = np.sum(channels_samples, axis=0)
            # print(mixed_samples.shape)
            # print(mixed_samples[:5])

            # mixed_bytes_read = min_bytes_read
            # mixed_bytes = mixed_samples.tobytes()
            mixed_bytes = self.channels[0].buffer_mv[:self.channels[0].bytes_read]


            # Write to I2S
            # apply temporary workaround to eliminate heap allocation in uasyncio Stream class.
            # workaround can be removed after acceptance of PR:
            #    https://github.com/micropython/micropython/pull/7868
            # swriter.write(wav_samples_mv[:num_read])
            
            swriter.out_buf = mixed_bytes
            await swriter.drain()




# def play(bg_filename="sd/night.wav", animal_filename="sd/wolf.wav", bg_shift=0, animal_shift=0):
#     if animal_filename is not None:
#         with wave.open(animal_filename) as wavf:
#             assert num_channels == wavf.getnchannels()
#             assert sample_rate == wavf.getframerate()
#             assert sample_width == wavf.getsampwidth()
    
#     if sample_width == 1: return 
#     print(f"Playing {'MONO' if num_channels==1 else 'STEREO'} {sample_rate}Hz {sample_width*8}bits")

#     audio_out = I2S(0, sck=Pin(32), ws=Pin(33), sd=Pin(25), mode=I2S.TX, bits=sample_width*8, format=(I2S.STEREO if num_channels==2 else I2S.MONO), rate=sample_rate, ibuf=_BUFFER_SIZE_BYTES)

#     try:
#         f = open(bg_filename, "rb")
#         fanimal = open(animal_filename, "rb") if animal_filename is not None else None

#         f.seek(44)
#         if fanimal is not None:
#             fanimal.seek(44)

#         bg_samples = bytearray(_BUFFER_SIZE_BYTES)
#         bg_samples_mv = memoryview(bg_samples)
#         animal_samples = bytearray(_BUFFER_SIZE_BYTES)
#         animal_samples_mv = memoryview(animal_samples)

#         num_read_bg = f.readinto(bg_samples_mv)
#         num_read_animal = fanimal.readinto(animal_samples_mv)

#         num_read = min(num_read_bg, num_read_animal)

#         while num_read != 0:
#             # I2S.shift(buf=bg_samples_mv, bits=sample_width*8, shift=bg_shift)
#             # I2S.shift(buf=animal_samples_mv, bits=sample_width*8, shift=animal_shift)
#             num_samples = num_read // sample_width

#             struct_fmt = "<" + "i"*num_samples
#             bg_samples = np.array(struct.unpack(struct_fmt, bg_samples_mv[:num_read]))
#             animal_samples = np.array(struct.unpack(struct_fmt, animal_samples_mv[:num_read]))
#             samples = bg_samples + animal_samples
#             audio_out.write(struct.pack(struct_fmt, samples))
            
#             num_read_bg = f.readinto(bg_samples_mv)
#             num_read_animal = fanimal.readinto(animal_samples_mv)
    
#     finally:
#         f.close()
#         if fanimal is not None: 
#             fanimal.close()
#         audio_out.deinit()





                
