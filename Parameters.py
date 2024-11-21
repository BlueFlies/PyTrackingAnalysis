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
    TWOCHOICECOUNTER = 8
    PAIRWISEINTERACTIONCOUNTER = 9

class TrackingClass(Enum):
    TRACKING=1
    COUNTING=2

class TrackingTypeDetails:
    def __init__(self, tracking_type=TrackingType.TRACKER):
        self.tracking_type = tracking_type
        if(tracking_type==TrackingType.TRACKER or tracking_type==TrackingType.TWOCHOICETRACKER or tracking_type==TrackingType.XCHOICETRACKER or tracking_type==TrackingType.DDROPTRACKER or tracking_type==TrackingType.PAIRWISEINTERACTIONTRACKER or tracking_type==TrackingType.CENTROPHOBISMTRACKER):
            self.tracking_class = TrackingClass.TRACKING
        elif(tracking_type==TrackingType.COUNTER or tracking_type==TrackingType.TWOCHOICECOUNTER or tracking_type==TrackingType.PAIRWISEINTERACTIONCOUNTER):
            self.tracking_class = TrackingClass.COUNTING
        else:  
            raise ValueError(f"Invalid tracking type: {tracking_type}. Must be an instance of TrackingType enum.")
        
    def get_tracking_type(self):
        return self.tracking_type  
    def get_tracking_class(self):
        return self.tracking_class
            
class Parameters:
    def __init__(self, tracking_type=TrackingType.TRACKER,fps=0,mm_per_pixel=0.1, speed_window_seconds=1, micromove_speed_mm_sec = [0.2,2],walking_speed_mm_sec=2, sleep_threshold_min=5):
        self.fps = fps
        self.mm_per_pixel = mm_per_pixel        
        self.speed_window_seconds = speed_window_seconds
        self.micro_move_speed_mm_sec = micromove_speed_mm_sec
        self.walking_speed_mm_sec = walking_speed_mm_sec
        self.sleep_threshold_min = sleep_threshold_min
        self.tracking_details = TrackingTypeDetails(tracking_type)
        self.interaction_distance_mm = [8]
        
    def set_tracking_type(self, tracking_type):
        self.tracking_details = TrackingTypeDetails(tracking_type)
        
    def get_tracking_type(self):
        return self.tracking_details.get_tracking_type()

    def get_tracking_class(self):
        return self.tracking_details.get_tracking_class()

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

    def set(self, tracking_type=None, fps=None, mm_per_pixel=None, speed_window_seconds=None, micromove_speed_mm_sec=None, walking_speed_mm_sec=None, sleep_threshold_min=None,interaction_distances=None):
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
        if interaction_distances is not None:
            if(isinstance(interaction_distances, list)):
                self.interaction_distance_mm = interaction_distances
            else:
                raise ValueError(f"Invalid interaction_distances: {interaction_distances}. Must be a list of integers.")
    
    def print(self):
        print(self.__str__())

    def set_obscura_values(self,tracking_type):
        self.fps=0
        self.mm_per_pixel=0.131
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(tracking_type)

    def set_pairwise_interaction_values_small_arena(self, interaction_distances):
        self.fps=0
        self.mm_per_pixel=0.056
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(TrackingType.PAIRWISEINTERACTIONTRACKER)
        if(isinstance(interaction_distances, list)):
            self.interaction_distance_mm = interaction_distances
        else:
            raise ValueError(f"Invalid interaction_distances: {interaction_distances}. Must be a list of integers.")

    def set_pairwise_interactioncounter_values_small_arena(self, interaction_distances):
        self.fps=0
        self.mm_per_pixel=0.056
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(TrackingType.PAIRWISEINTERACTIONCOUNTER)
        if(isinstance(interaction_distances, list)):
            self.interaction_distance_mm = interaction_distances
        else:
            raise ValueError(f"Invalid interaction_distances: {interaction_distances}. Must be a list of integers.")

    def set_pairwise_interactioncounter_values_arena_max(self, interaction_distances):
        self.fps=0
        self.mm_per_pixel=0.145
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(TrackingType.PAIRWISEINTERACTIONCOUNTER)
        if(isinstance(interaction_distances, list)):
            self.interaction_distance_mm = interaction_distances
        else:
            raise ValueError(f"Invalid interaction_distances: {interaction_distances}. Must be a list of integers.")

    def __str__(self):
        return f"tracking_type: {self.tracking_details.get_tracking_type()}\nfps: {self.fps}\nmm_per_pixel: {self.mm_per_pixel}\nspeed_window_seconds: {self.speed_window_seconds}\nmicromove_speed_mm_sec: {self.micro_move_speed_mm_sec}\nwalking_speed_mm_sec: {self.walking_speed_mm_sec}\nsleep_threshold_min: {self.sleep_threshold_min}\ninteraction_distances: {self.interaction_distance_mm}"
   
    def set_pairwise_interaction_values_arena_max(self, interaction_distances):
        self.fps=0
        self.mm_per_pixel=0.145
        self.speed_window_seconds=1
        self.micro_move_speed_mm_sec = [0.2,2]
        self.walking_speed_mm_sec = 2
        self.sleep_threshold_min = 5
        self.set_tracking_type(TrackingType.PAIRWISEINTERACTIONTRACKER)
        if(isinstance(interaction_distances, list)):
            self.interaction_distance_mm = interaction_distances
        else:
            raise ValueError(f"Invalid interaction_distances: {interaction_distances}. Must be a list of integers.")

    def __str__(self):
        return f"tracking_type: {self.tracking_details.get_tracking_type()}\nfps: {self.fps}\nmm_per_pixel: {self.mm_per_pixel}\nspeed_window_seconds: {self.speed_window_seconds}\nmicromove_speed_mm_sec: {self.micro_move_speed_mm_sec}\nwalking_speed_mm_sec: {self.walking_speed_mm_sec}\nsleep_threshold_min: {self.sleep_threshold_min}\ninteraction_distances: {self.interaction_distance_mm}"
        
        
if __name__ == "__main__":
    p=Parameters()
    p.set_tracking_type(TrackingType.TWOCHOICECOUNTER)
    print(p.get_tracking_class())
    print(p.get_tracking_type())
    
    