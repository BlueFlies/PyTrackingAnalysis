import pandas as pd
import numpy as np

class Parameters:
    def __init__(self, tracking_type="Tracker",fps=0,mm_per_pixel=0.1, speed_window_seconds=1, micromove_speed_mm_sec = [0.2,2],walking_speed_mm_sec=2, sleep_threshold_min=5):
        self.fps = fps
        self.mm_per_pixel = mm_per_pixel        
        self.speed_window_seconds = speed_window_seconds
        self.micro_move_speed_mm_sec = micromove_speed_mm_sec
        self.walking_speed_mm_sec = walking_speed_mm_sec
        self.sleep_threshold_min = sleep_threshold_min
        self.tracking_type = tracking_type
        

    def set_small_arena_values(self,tracking_type):
        self.fps=0
        self.mm_per_pixel=0.056
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5

    def set_movie_values(self,tracking_type, fps, mm_per_pixel):
        self.fps=fps
        self.mm_per_pixel=mm_per_pixel
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5

    def set_obscura_vales(self,tracking_type):
        self.fps=0
        self.mm_per_pixel=0.131
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        