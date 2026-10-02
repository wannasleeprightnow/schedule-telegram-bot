from datetime import time


PAIR_TIMES: dict[int, tuple[time, time]] = {
    1: (time(9, 0), time(10, 30)),
    2: (time(10, 55), time(12, 25)),
    3: (time(13, 0), time(14, 30)),
    4: (time(15, 0), time(16, 30)),
    5: (time(16, 55), time(18, 25)),
}
