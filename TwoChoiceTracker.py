import pandas as pd
import numpy as np
import Tracker
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class TwoChoiceTracker(Tracker.Tracker):
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        super().__init__(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)
