from enum import Enum
import pandas as pd

class TrackingType(Enum):
    TRACKER = 1
    TWOCHOICETRACKER = 2
    XCHOICETRACKER = 3
    DDROPTRACKER = 4
    PAIRWISEINTERACTIONTRACKER = 5
    CENTROPHOBISMTRACKER = 6
    COUNTER = 7
    TWOCHOICECOUNTER = 7
    PAIRWISEINTERACTIONCOUNTER = 8


class Parameters:
    def __init__(self, tracking_type=TrackingType.TRACKER,fps=0,mm_per_pixel=0.1, speed_window_seconds=1, micromove_speed_mm_sec = [0.2,2],walking_speed_mm_sec=2, sleep_threshold_min=5):
        self.fps = fps
        self.mm_per_pixel = mm_per_pixel        
        self.speed_window_seconds = speed_window_seconds
        self.micro_move_speed_mm_sec = micromove_speed_mm_sec
        self.walking_speed_mm_sec = walking_speed_mm_sec
        self.sleep_threshold_min = sleep_threshold_min
        self.tracking_type = tracking_type
        
    def set_tracking_type(self, tracking_type):
        if not isinstance(tracking_type, TrackingType):
            raise ValueError(f"Invalid tracking type: {tracking_type}. Must be an instance of TrackingType enum.")
        self.tracking_type = tracking_type

    def set_small_arena_values(self,tracking_type):
        self.fps=0
        self.mm_per_pixel=0.056
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(tracking_type)


    def set_arena_max_values(self,tracking_type):
        self.fps=0
        self.mm_per_pixel=0.145
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(tracking_type)

    def set_movie_values(self,tracking_type, fps, mm_per_pixel):
        self.fps=fps
        self.mm_per_pixel=mm_per_pixel
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(tracking_type)

    def set(self, tracking_type=None, fps=None, mm_per_pixel=None, speed_window_seconds=None, micromove_speed_mm_sec=None, walking_speed_mm_sec=None, sleep_threshold_min=None):
        if tracking_type is not None:
            self.set_tracking_type(tracking_type)
        if fps is not None:
            self.fps = fps
        if mm_per_pixel is not None:
            self.mm_per_pixel = mm_per_pixel        
        if speed_window_seconds is not None:
            self.speed_window_seconds = speed_window_seconds
        if micromove_speed_mm_sec is not None:
            self.micro_move_speed_mm_sec = micromove_speed_mm_sec
        if walking_speed_mm_sec is not None:
            self.walking_speed_mm_sec = walking_speed_mm_sec
        if sleep_threshold_min is not None:
            self.sleep_threshold_min = sleep_threshold_min
    
    def print(self):
        print(self.__str__())

    def set_obscura_vales(self,tracking_type):
        self.fps=0
        self.mm_per_pixel=0.131
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(tracking_type)

    def __str__(self):
        return f"tracking_type: {self.tracking_type}\nfps: {self.fps}\nmm_per_pixel: {self.mm_per_pixel}\nspeed_window_seconds: {self.speed_window_seconds}\nmicromove_speed_mm_sec: {self.micro_move_speed_mm_sec}\nwalking_speed_mm_sec: {self.walking_speed_mm_sec}\nsleep_threshold_min: {self.sleep_threshold_min}"
        