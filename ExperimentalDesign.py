import numpy as np
import pandas as pd
import Tracker 
import TwoChoiceTracker
import Parameters
import glob
from natsort import natsorted
import Arena

class ExperimentalDesign:
    def __init__(self, exp_name, parameters):     
        self.experiment_name = exp_name   
        self.parameters = parameters    
        self.experimentdesign_file_name = self.experiment_name + '_Design.txt'        
        try:
            self.read_experimental_design_file(self.experimentdesign_file_name)            
            self.experimental_design = True
        except:            
            self.experimental_design = False             
        self.verify_experimental_design()         
        

    def read_experimental_design_file(self, file_name):
        tracking_regions = []
        counting_regions = []
        try:
            with open(file_name, 'r') as file:
                lines = file.readlines()                
            for l in lines:
                l = l.strip()         
                if len(l)==0 or l[0]=="#":
                    continue
                if "[" in l and "]" in l:
                    currentSection = l[l.index("[")+1:l.index("]")]                    
                else:
                    if(currentSection.lower()=="tracking regions"):
                        thesplit = l.split(",")                         
                        if(len(thesplit)==2):                            
                            tracking_regions.append(thesplit)                            
                    elif(currentSection.lower()=="counting regions"):
                        thesplit = l.split(",") 
                        if(len(thesplit)==2):
                            counting_regions.append(thesplit)
                    elif(currentSection.lower()=="run"):
                        raise ValueError("Run section not implemented yet.")
                    elif(currentSection.lower()=="fly"):
                        raise ValueError("Fly section not implemented yet.")

            self.tracking_regions = pd.DataFrame(tracking_regions, columns=['RegionName','Treatment'])
            self.counting_regions = pd.DataFrame(counting_regions, columns=['RegionName','Characteristic'])
        except:
            self.tracking_regions = None
            self.counting_regions = None

    def get_tracking_region(self, region_name):
        if(self.tracking_regions is None):
            return None
        return self.tracking_regions[self.tracking_regions['RegionName']==region_name]
    
    def get_counting_regions(self, region_names):
        if(self.counting_regions is None):
            return None                
        return self.counting_regions[self.counting_regions['RegionName'].isin(region_names)]         

    def verify_experimental_design(self):
        if(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):
            pass
        elif(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            if(self.experimental_design==False):                                
                raise ValueError("No experimental design file found for TwoChoiceTracker.")
            elif(self.counting_regions['Characteristic'].nunique()!=2):                                
                raise ValueError(f"Invalid design file for TwoChoiceTracker. Must have exactly two unique counting region characteristics.")
            pass
        else:
            pass
            
    def __str__(self):
        return f"Experimental Design for {self.experiment_name}:\nTracking Regions:\n{self.tracking_regions}\nCounting Regions:\n{self.counting_regions}"   


if __name__ == "__main__":
    p=Parameters.Parameters()
    ed = ExperimentalDesign("MaxIRSetup",p)
    print(ed.get_tracking_region("T_1"))