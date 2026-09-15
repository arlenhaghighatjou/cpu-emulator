import os

from cpuemulator.arch import FLAG_I
from cpuemulator.bus import Bus
from cpuemulator.cpu import CPU
from cpuemulator.devices import InterruptController, Keyboard, Rng, Serial, Timer
from cpuemulator.display import Display
from cpuemulator.image import Image


class Machine:
    def __init__(self, seed: int | None = None) -> None:
        if seed is None:
            seed = int.from_bytes(os.urandom(2), "little")
        self.bus = Bus()
        self.pic = InterruptController()
        self.keyboard = Keyboard(self.pic)
        self.timer = Timer(self.pic)
        self.rng = Rng(seed)
        self.serial = Serial(self.pic)
        self.display = Display(self.bus.ram)
        for device in (self.keyboard, self.timer, self.display, self.pic, self.rng, self.serial):
            self.bus.attach(device)
        self.cpu = CPU(self.bus, self.pic)
        self.image = Image()

    def load(self, image: Image) -> None:
        self.bus.reset()
        for address, data in image.segments:
            self.bus.load(address, data)
        self.cpu.reset(image.entry)
        self.image = image

    def reset(self) -> None:
        self.load(self.image)

    @property
    def idle(self) -> bool:
        cpu = self.cpu
        if not cpu.waiting:
            return False
        return not (cpu.flags & FLAG_I and self.pic.pending & self.pic.mask)

    def step(self) -> int:
        cost = self.cpu.step()
        self.timer.tick(cost)
        return cost

    def run(self, budget: int) -> int:
        cpu = self.cpu
        timer = self.timer
        used = 0
        while used < budget and not cpu.halted:
            if self.idle:
                skip = budget - used
                if timer.ctrl & 1:
                    skip = min(skip, timer.count)
                cpu.cycles += skip
                timer.tick(skip)
                used += skip
                continue
            cost = cpu.step()
            timer.tick(cost)
            used += cost
        return used
