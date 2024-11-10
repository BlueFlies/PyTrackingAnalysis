import numpy as np
import pandas as pd
import Tracker 
import TwoChoiceTracker
import Parameters

class Arena:
    def __init__(self, exp_name, parameters):        
        self.parameters = parameters
        self.experiment_name = exp_name
        self.csv_file = exp_name + "_Data_1.csv"        
        self.get_experiment_file_info()
        self.get_experimental_design()
        self.create_trackers()
        

    def display_head(self, n=5):
        print(self.rawdata.head(n))
        print(self.rawdata.dtypes)


    def get_experiment_file_info(self):
        file_name = self.experiment_name + '.xlsx'
        sheet_name = "ROI"
        
        roi = pd.read_excel(file_name, sheet_name=sheet_name)
        self.tracking_regions =  roi[(roi['Type']=='Tracking')].reset_index(drop=True)
        self.counting_regions =  roi[(roi['Type']=='Counting')].reset_index(drop=True)
       

    def get_experimental_design(self):
        try:
            self.experimental_design = pd.read_csv("ExpDesign.csv",keep_default_na=False,na_values=['NaN'])
        except:
            self.experimental_design = None

    def create_trackers(self):
        rawdata = pd.read_csv(self.csv_file,keep_default_na=False,na_values=['NaN'])
        self.trackers = {}
        grouped_data = rawdata.groupby(['TrackingRegion','ObjectID'] )
        for (region,object_id), group in grouped_data:
            if(self.parameters.tracking_type=="Tracker"):
                tracker = Tracker.Tracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
            elif(self.parameters.tracking_type=="TwoChoiceTracker"):
                tracker = TwoChoiceTracker.TwoChoiceTracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
            self.trackers[f'{region}_{object_id}'] = tracker 
        self.trackerKeys = list(self.trackers.keys())

    def first_tracker(self):
        return self.trackers[self.trackerKeys[0]]

    def get_tracker(self, key):
        return self.trackers.get(key,None)

    def test(self):
        print(self.firstTracker().locations())


if __name__ == "__main__":
    p=Parameters.Parameters()
    p.set_small_arena_values("TwoChoiceTracker")
    arena = Arena('MaxIRSetup',p)
    print(arena.get_tracker("T_4_0"))
    #print(arena.firstTracker().tracking_region)
    #print(arena.firstTracker().counting_regions)
    #print(arena.firstTracker().PlotXY())
    #print(arena.firstTracker().PlotX())
    #print(arena.firstTracker().PlotY())
    #arena.firstTracker().summarize()
    #arena.test()
