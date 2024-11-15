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
        self.tracking_regions = None
        # Counting regions is a dictionary with keys as the treatments and values as all the different regions in the datafile that correspond to each.
        self.counting_regions = None
        try:            
            self.read_experimental_design_file(self.experimentdesign_file_name)                      
            self.experimental_design = True
        except:            
            self.experimental_design = False             
        self.verify_experimental_design()                 
        

    def read_experimental_design_file(self, file_name):
        tracking_regions = []
        counting_regions = {}
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
                        thesplit = [x.strip() for x in l.split(",")]                                        
                        if(len(thesplit)==4):    
                            thesplit[2] = int(thesplit[2])
                            if(thesplit[2]!=-1 and thesplit[2]!=1):
                                thesplit[2] = 1
                            thesplit[3] = int(thesplit[3])
                            if(thesplit[3]!=-1 and thesplit[3]!=1):                                                           
                                thesplit[3] = 1                        
                            tracking_regions.append(thesplit)                                                    
                        elif(len(thesplit)==2):                            
                            tracking_regions.append([thesplit[0],thesplit[1],1,1])
                    elif(currentSection.lower()=="counting regions"):
                        thesplit = l.split(":")                                                                          
                        if(len(thesplit)==2):   
                            key = thesplit[0].strip()
                            values = [x.strip() for x in thesplit[1].split(",")]                         
                            counting_regions[key] = values
                        else:
                            raise ValueError("Invalid counting region format.")
                    elif(currentSection.lower()=="run"):
                        raise ValueError("Run section not implemented yet.")
                    elif(currentSection.lower()=="fly"):
                        raise ValueError("Fly section not implemented yet.")

            self.tracking_regions = pd.DataFrame(tracking_regions, columns=['RegionName','Treatment',"XLocationMultiplier","YLocationMultiplier"])                          
            self.counting_regions=counting_regions            
        except:            
            self.tracking_regions = None
            self.counting_regions = None

    def get_tracking_region(self, region_name):
        if(self.tracking_regions is None):
            return None
        return self.tracking_regions[self.tracking_regions['RegionName']==region_name]
    
    def get_counting_characteristic(self, region_name):
        if(self.counting_regions is None):
            return None                
        else:
            for key,value in self.counting_regions.items():
                if region_name in value:
                    return key
        return None

    def verify_experimental_design(self):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):
            pass
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            if(self.experimental_design==False):                                
                raise ValueError("No experimental design file found for TwoChoiceTracker.")
            elif(len(self.counting_regions.keys())!=2):                                
                raise ValueError(f"Invalid design file for TwoChoiceTracker. Must have exactly two unique counting region characteristics.")
            pass
        else:
            pass
            
    def __str__(self):
        return f"Experimental Design for {self.experiment_name}:\nTracking Regions:\n{self.tracking_regions}\nCounting Regions:\n{self.counting_regions}"   


if __name__ == "__main__":
    p=Parameters.Parameters()
    ed = ExperimentalDesign("./Data/MaxIRSetup",p)
    print(ed.tracking_regions)
    #print(ed.get_tracking_region("T_1"))